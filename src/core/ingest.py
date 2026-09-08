"""Turn a caught monitor event into the rows the rest of the product reads.

This is the other half of the interrupt path. Parallel's Monitor API catches
an event within minutes of it happening, and until now that event landed in
`monitor_events` and stopped there: it appeared on /watch as a paragraph of
prose and nothing else. A raised price target caught at 11:04 did not become a
target row, did not move the consensus, did not reach the metrics export and
fired no alert. The product could see the news and could not act on it.

What the monitor returns is prose with citations, not a record. Classifying it
by keyword would be guessing, so the event text is handed back to Parallel's
Task API against the same schemas the scheduled run uses, and the extraction
carries the same basis. The event is the input rather than the open web, which
is why `lite` is enough here: the finding is already made, this is only reading
it into shape.

The scheduled run stays exactly as it was. This does not replace it, it fills
the gap between two of them.
"""
from __future__ import annotations

from typing import Any, Callable

from . import evidence, filings, targets
from .parallel_api import NoCredit, ParallelError, run_task

# The event text is short and the facts in it are already established, so the
# cheapest processor is the right one: this is a parse, not a research job.
PROCESSOR = "lite"

# What an event can turn into. Anything else is left as prose on /watch, which
# is a real outcome rather than a failure: an executive departure is worth
# reading and is not a row in any table the product keeps.
KINDS = ("target", "filing")

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "description": (
                "One of: target (an analyst price target or rating change), "
                "filing (an SEC filing, insider transaction or share offering), "
                "other (anything else, including earnings and executive changes)"
            ),
        },
        "reason": {"type": "string", "description": "One short line on why"},
    },
    "required": ["kind"],
}


def classify(event_text: str) -> str:
    """What kind of record this event could become, or "other".

    Asked of the model rather than matched on keywords: "Redburn raised its
    target" and "Redburn initiated coverage at $400" are the same kind of fact
    written two ways, and a keyword list gets the second one wrong.
    """
    if not (event_text or "").strip():
        return "other"
    try:
        content, _ = run_task(
            "Classify this market event. Use only the text given, do not "
            f"research it:\n\n{event_text[:2000]}",
            ROUTE_SCHEMA,
            processor=PROCESSOR,
            max_wait=180,
        )
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[ingest] classify failed: {exc}")
        return "other"
    kind = (content.get("kind") or "").strip().lower()
    return kind if kind in KINDS else "other"


def _extract(event_text: str, ticker: str, company: str, kind: str) -> tuple[list[dict], list[dict]]:
    """Read the event into rows using the schema for its kind."""
    schema = targets.SCHEMA if kind == "target" else filings.SCHEMA
    what = ("the analyst price target(s) and rating(s)" if kind == "target"
            else "the SEC filing(s), including insider name, role and transaction")
    try:
        content, basis = run_task(
            f"Extract {what} stated in this event about {company} ({ticker}). "
            f"Use only the text given; do not add anything not stated in it. "
            f"If the event states no such record, return an empty list.\n\n"
            f"{event_text[:4000]}",
            schema,
            processor=PROCESSOR,
            # A `lite` run against a short input still takes longer than two
            # minutes often enough to matter: the first live test of this path
            # timed out at 120s and silently produced no row, which is the
            # failure the whole module exists to prevent. The scheduled run
            # allows 300-360s for the same schemas.
            max_wait=300,
        )
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[ingest] {ticker} {kind} extract failed: {exc}")
        return [], []
    key = "targets" if kind == "target" else "filings"
    return (content.get(key) or []), (basis or [])


def from_event(
    event: dict,
    ticker: str,
    company_name: str,
    *,
    save_targets: Callable[[str, list[dict], str], int],
    save_filings: Callable[[str, list[dict], str], int],
) -> dict[str, Any]:
    """Promote one event into stored rows. Returns what it did.

    The save functions are passed in rather than imported: this module is the
    logic, and the caller owns which backend it writes to. That is also what
    makes it testable without a database.

    Never raises. An event that cannot be read is still an event, and it stays
    on /watch as prose; losing the webhook's whole response over one bad parse
    would be a worse outcome than a missing row.
    """
    text = (event.get("text") or "").strip()
    result: dict[str, Any] = {"kind": "other", "targets": 0, "filings": 0}
    if not text:
        return result

    kind = classify(text)
    result["kind"] = kind
    if kind not in KINDS:
        return result

    rows, basis = _extract(text, ticker, company_name, kind)
    if not rows:
        return result

    # The event's own citations are the provenance: these rows were read out of
    # a monitor finding, and a reader hovering the "?" should land on the page
    # the monitor actually caught, not on an empty card.
    cites = event.get("citations") or []
    fallback_url = cites[0]["url"] if cites else ""
    facts = evidence.normalize(basis)
    confidence = evidence.overall_confidence(facts) if facts else "medium"

    if kind == "target":
        clean = targets._clean(rows, ticker)
        field = "target_price"
    else:
        clean = filings._clean(rows, ticker)
        field = "transaction"

    # A monitor event often states a change without restating its date ("raised
    # its target to $210 from $185"). Undated, a target cannot take part in
    # revision detection, which compares a firm's rows in date order, so the
    # event's own date stands in: it is when the change was caught, which for a
    # continuous watch is within an hour of when it happened.
    caught_on = (event.get("event_date") or "")[:10]
    date_field = "date" if kind == "target" else "filed_date"

    cite = evidence.first_excerpt(facts, field) if facts else None
    for row in clean:
        if not row.get(date_field) and caught_on:
            row[date_field] = caught_on
        row["confidence"] = confidence
        # Prefer the extraction's own citation; fall back to the event's, so a
        # promoted row is never less auditable than the prose it came from.
        row["evidence"] = cite or (
            {"url": fallback_url, "excerpt": cites[0].get("excerpt", "")}
            if cites else None
        )
        if not row.get("source_url") and fallback_url:
            row["source_url"] = fallback_url

    if not clean:
        return result

    # The run id records where these rows came from, so a row promoted by the
    # interrupt path is distinguishable from one found by a scheduled sweep.
    run_id = f"monitor:{event.get('event_id') or event.get('event_group_id') or 'event'}"
    if kind == "target":
        result["targets"] = save_targets(ticker, clean, run_id)
    else:
        result["filings"] = save_filings(ticker, clean, run_id)
    return result
