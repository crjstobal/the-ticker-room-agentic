"""Analyst price targets, extracted with Parallel's Task API.

Search returns pages; Task returns structured records. Asking for "the firm,
the analyst, the target and the date" gives back rows that can be charted and
compared against the live price, which is what makes a target useful: a $270
target on a $153 stock is a claim with a size, not just an opinion.

Every extraction carries Parallel's basis: the source sentence and confidence
behind each field, so a target can be checked rather than taken on faith.

Targets are reported as what analysts published. Nothing here is a forecast of
our own, and a target is not a recommendation.
"""
from __future__ import annotations

import re

from . import evidence
from .parallel_api import NoCredit, ParallelError, run_task

SCHEMA = {
    "type": "object",
    "properties": {
        "targets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "firm": {"type": "string", "description": "Research firm or fund"},
                    "analyst": {"type": "string", "description": "Analyst name if named"},
                    "target_price": {"type": "number", "description": "Price target in USD"},
                    "rating": {"type": "string", "description": "Buy, Hold, Sell or equivalent"},
                    "date": {"type": "string", "description": "Publication date, YYYY-MM-DD"},
                    "source_url": {"type": "string"},
                },
                "required": ["firm", "target_price"],
            },
        }
    },
    "required": ["targets"],
}


def fetch_targets(ticker: str, company_name: str, *, year: int = 2026) -> list[dict]:
    """Analyst price targets for a ticker. Returns [] rather than raising.

    Each row carries the run's evidence, so the page can show the sentence a
    target was read from and how confident the extraction was.
    """
    try:
        content, basis = run_task(
            f"Analyst price targets for {company_name} ({ticker}) stock published "
            f"in {year}: which firm, which analyst, what target price in USD, what "
            f"rating, and what date. Only targets from named research firms.",
            SCHEMA,
            max_wait=300,
        )
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[targets] {ticker}: {exc}")
        return []

    rows = _clean(content.get("targets") or [], ticker)
    facts = evidence.normalize(basis)
    if facts:
        confidence = evidence.overall_confidence(facts)
        cite = evidence.first_excerpt(facts, "target_price")
        for row in rows:
            row["confidence"] = confidence
            row["evidence"] = cite
    return rows


# A model asked for a date it cannot find answers in words rather than leaving
# the field empty. "Not stated" stored as a date sorts as a string, so it would
# rank above every real ISO date and win "most recent target" for its firm.
_NON_DATE = re.compile(
    r"^(n/?a|none|not\s|unknown|unspecified|undated|no\s)", re.IGNORECASE)


def _date(value) -> str:
    """An ISO date, or empty. Anything that is not a date is not a date."""
    text = str(value or "").strip()
    if not text or _NON_DATE.match(text):
        return ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return m.group(0) if m else ""


# Suffixes and share-class noise that ride along on a research firm's name.
# Aggregators write the same firm several ways, and each spelling was counted
# as a separate analyst: ONDS carried "Ladenburg Thalmann", "LADENBURG
# THALM/SH SH" and "Ladenburg Thalmann/SH SH" as three firms at $22.75, which
# pulled the consensus average toward one house with one opinion.
_FIRM_NOISE = re.compile(
    r"(/\s*sh\s*sh\b|\bsh\s+sh\b|\b(inc|corp|corporation|co|llc|llp|lp|ltd|plc|"
    r"sa|nv|ag|gmbh|group|holdings?|securities|capital|markets|research|"
    r"partners|associates|financial|advisors?|company|and|&)\b)",
    re.IGNORECASE,
)


def canonical_firm(name: str) -> str:
    """A comparison key for a research firm's name.

    Used only to decide whether two rows are the same house. The display name
    is whichever spelling arrived first, so the page still shows a real name
    rather than a stripped-down key.
    """
    text = re.sub(r"[.,]", " ", (name or "").lower())
    text = _FIRM_NOISE.sub(" ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _clean(targets: list[dict], ticker: str) -> list[dict]:
    """Drop rows without a usable price, de-duplicating by firm AND date.

    The same target appears on several aggregator pages, so exact repeats are
    collapsed. But a firm's *older* target must survive: a revision from $18 to
    $10 is only visible if both figures are kept, and that revision is the
    thing worth alerting on.
    """
    seen: dict[tuple, dict] = {}
    for t in targets:
        try:
            price = float(t.get("target_price"))
        except (TypeError, ValueError):
            continue
        if not (0 < price < 100_000):
            continue
        firm = (t.get("firm") or "").strip()
        if not firm:
            continue
        row = {
            "ticker": ticker.upper(),
            "firm": firm,
            "analyst": (t.get("analyst") or "").strip(),
            "target_price": round(price, 2),
            "rating": (t.get("rating") or "").strip(),
            "date": _date(t.get("date")),
            "source_url": (t.get("source_url") or "").strip(),
        }
        # Keyed on the canonical firm so "Ladenburg Thalmann" and
        # "LADENBURG THALM/SH SH" collapse into one row.
        key = (canonical_firm(firm), row["date"], row["target_price"])
        seen.setdefault(key, row)
    return sorted(seen.values(), key=lambda r: (-r["target_price"], r["firm"]))


def _recency(row: dict) -> tuple:
    """How recent a target is, with deterministic tie-breakers.

    The date alone is not an ordering: two targets from the same firm on the
    same day compare equal, and the winner then depends on the order the rows
    happened to arrive in. `find_revisions` reads that order as the *direction*
    of the change, so the same pair could be published as a 60% cut or a 150%
    raise between one refresh and the next. `captured_at` and the row id are
    monotonic, so they settle it the same way every time.
    """
    return (row.get("date", ""), row.get("captured_at", ""), row.get("id", 0))


def merge_firm_keys(keys: list[str]) -> dict[str, str]:
    """Map each canonical key to the group it belongs to.

    Aggregators also *truncate* names, so suffix stripping alone leaves
    "ladenburgthalm" and "ladenburgthalmann" apart. A key that is a prefix of
    a longer one is treated as the same house and both resolve to the longest
    spelling. The prefix must be substantial, so "lake" never swallows
    "lakestreet" on the strength of four letters.
    """
    MIN_PREFIX = 8
    out: dict[str, str] = {}
    for key in keys:
        group = key
        for other in keys:
            if (other != key and len(key) >= MIN_PREFIX
                    and other.startswith(key) and len(other) > len(group)):
                group = other
        out[key] = group
    # One more pass: a middle-length spelling may itself have been folded into
    # a longer one, so follow the chain to its end.
    for key in list(out):
        seen = {key}
        while out[key] != out.get(out[key], out[key]) and out[key] not in seen:
            seen.add(out[key])
            out[key] = out[out[key]]
    return out


def _grouped(targets: list[dict]) -> dict[str, str]:
    """Canonical key -> merged group key, for one set of targets."""
    return merge_firm_keys(sorted({canonical_firm(t["firm"]) for t in targets}))


def latest_per_firm(targets: list[dict]) -> list[dict]:
    """The current view: one row per firm, its most recent target."""
    groups = _grouped(targets)
    by_firm: dict[str, dict] = {}
    for t in targets:
        key = groups[canonical_firm(t["firm"])]
        prev = by_firm.get(key)
        if not prev or _recency(t) > _recency(prev):
            by_firm[key] = t
    return sorted(by_firm.values(), key=lambda r: -r["target_price"])


def find_revisions(targets: list[dict], *, min_pct: float = 10.0) -> list[dict]:
    """Firms that changed their target, newest change first.

    A revision is the signal: an analyst moving from $18 to $10 is a stronger
    statement than any single number, because the same person changed their
    mind with the company in full view.
    """
    groups = _grouped(targets)
    by_firm: dict[str, list[dict]] = {}
    for t in targets:
        if t.get("date"):
            by_firm.setdefault(groups[canonical_firm(t["firm"])], []).append(t)

    revisions = []
    for rows in by_firm.values():
        rows = sorted(rows, key=_recency)
        if len(rows) < 2:
            continue
        prev, curr = rows[-2], rows[-1]
        old, new = prev["target_price"], curr["target_price"]
        if not old:
            continue
        pct = (new - old) / old * 100
        if abs(pct) < min_pct:
            continue
        revisions.append({
            "ticker": curr.get("ticker", ""), "firm": curr["firm"],
            "analyst": curr.get("analyst", ""),
            "old_price": old, "new_price": new,
            "change_pct": round(pct, 1),
            "direction": "raised" if pct > 0 else "cut",
            "old_date": prev["date"], "date": curr["date"],
            "rating": curr.get("rating", ""),
            "source_url": curr.get("source_url", ""),
        })
    return sorted(revisions, key=lambda r: r["date"], reverse=True)


def summarize(targets: list[dict], spot: float | None) -> dict:
    """Consensus view: the spread of targets and where the price sits in it."""
    if not targets:
        return {"n": 0}
    targets = latest_per_firm(targets)
    prices = [t["target_price"] for t in targets]
    avg = sum(prices) / len(prices)
    out = {
        "n": len(targets),
        "low": min(prices),
        "high": max(prices),
        "average": round(avg, 2),
        "firms": len({t["firm"] for t in targets}),
    }
    if spot:
        out["spot"] = spot
        out["upside_pct"] = round((avg - spot) / spot * 100, 1)
        out["above_spot"] = sum(1 for p in prices if p > spot)
    return out
