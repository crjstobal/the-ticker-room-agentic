"""Continuous watching with Parallel's Monitor API.

The scheduled run is a pull: twice each weekday it re-searches everything,
whether or not anything happened. That is why the backlog says a spike "cannot
be seen before the run that finds the articles" — the floor on how fast the
product can react is the cadence of its own polling.

Monitor inverts it. A watch is declared once per ticker, Parallel keeps looking,
and a webhook arrives when something actually changes. Between events there is
no traffic and no cost, and an event lands in minutes rather than at the next
scheduled sweep.

The two are complementary and both are kept: the run is the periodic full
picture, the monitor is the interrupt.
"""
from __future__ import annotations

import os

from .parallel_api import ParallelError, get, request

# How often Parallel re-checks. The API accepts 1h, 1d and 1w; a ticker's news
# does not move meaningfully faster than hourly, and 1h is the floor anyway.
DEFAULT_FREQUENCY = "1h"

# `lite` is the cheap continuous processor and the right default for a watch
# that runs forever across a whole watchlist. `base` is deeper and reserved for
# a caller that asks.
DEFAULT_PROCESSOR = "lite"


def _webhook_url() -> str:
    """Where Parallel should deliver events.

    Empty locally: the API rejects a webhook it cannot reach, and a monitor
    without one still records events for polling.
    """
    base = os.environ.get("TICKERROOM_PUBLIC_URL", "").rstrip("/")
    return f"{base}/hooks/parallel" if base.startswith("https://") else ""


def watch_query(ticker: str, company_name: str) -> str:
    """What to watch for one ticker.

    Deliberately narrower than the research objective: a monitor should fire on
    discrete events a reader would want to know about today, not on the general
    drift of coverage that the scheduled run already summarizes.
    """
    return (
        f"Material news about {company_name} ({ticker}) stock: new contracts or "
        f"customer wins, SEC filings including insider transactions and share "
        f"offerings, analyst rating or price target changes, earnings results, "
        f"executive changes, and legal or regulatory action."
    )


def create(ticker: str, company_name: str, *, frequency: str = DEFAULT_FREQUENCY,
           processor: str = DEFAULT_PROCESSOR) -> dict:
    """Start watching one ticker. Returns the monitor record."""
    body = {
        "type": "event_stream",
        "frequency": frequency,
        "processor": processor,
        "settings": {"query": watch_query(ticker, company_name)},
        # Carried back on every event, so a webhook payload identifies its
        # ticker without a lookup table on our side.
        "metadata": {"ticker": ticker.upper(), "company_name": company_name},
    }
    hook = _webhook_url()
    if hook:
        body["webhook"] = {"url": hook, "event_types": ["monitor.event.detected"]}
    return request("/v1/monitors", body, timeout=60)


def cancel(monitor_id: str) -> dict:
    """Stop a monitor. Cancelling is a POST; DELETE is not accepted."""
    return request(f"/v1/monitors/{monitor_id}/cancel", {}, timeout=30)


def status(monitor_id: str) -> dict:
    return get(f"/v1/monitors/{monitor_id}")


def list_all() -> list[dict]:
    payload = get("/v1/monitors")
    return payload.get("data") or payload.get("monitors") or []


def events(monitor_id: str, *, event_group_id: str = "") -> list[dict]:
    """Events this monitor has recorded, newest first where dated."""
    path = f"/v1/monitors/{monitor_id}/events"
    if event_group_id:
        path += f"?event_group_id={event_group_id}"
    payload = get(path, timeout=60)
    raw = payload.get("events") or payload.get("data") or []
    return sorted(
        (_event(e) for e in raw if isinstance(e, dict) and not _is_error(e)),
        key=lambda e: e.get("event_date") or "",
        reverse=True,
    )


def _is_error(e: dict) -> bool:
    """Whether a raw monitor entry is Parallel reporting a failed run.

    Monitor does not fail the HTTP call when it cannot run: it records an entry
    with `event_type: "error"` in the events list. Flattened by `_event` that
    became an event with no date and no text, which `save_monitor_event` then
    dropped as empty, so 19 consecutive hourly failures looked exactly like 19
    quiet hours. That is the same silent-402 trap the run path already guards
    against, arriving through the body instead of the status code.
    """
    return (e.get("event_type") or "") == "error"


def error_events(monitor_id: str) -> list[dict]:
    """Failed runs this monitor recorded, newest first.

    Exposed so the page can say "the watch could not run" instead of showing
    the same empty box it shows on a genuinely quiet day.
    """
    payload = get(f"/v1/monitors/{monitor_id}/events", timeout=60)
    raw = payload.get("events") or payload.get("data") or []
    errs = [e for e in raw if isinstance(e, dict) and _is_error(e)]
    return sorted(errs, key=lambda e: e.get("timestamp") or "", reverse=True)


def _event(e: dict) -> dict:
    """Flatten one event into the shape the rest of the product stores.

    The text is in `output.content` and the sources in `output.basis`, the same
    citation shape the Task API returns.
    """
    output = e.get("output") or {}
    content = output.get("content")
    if isinstance(content, dict):
        content = content.get("text") or content.get("summary") or ""
    citations = []
    for entry in output.get("basis") or []:
        for c in entry.get("citations") or []:
            url = (c.get("url") or "").strip()
            if url and url not in [x["url"] for x in citations]:
                excerpts = [" ".join(str(x).split()) for x in (c.get("excerpts") or [])]
                citations.append({"url": url, "excerpt": excerpts[0] if excerpts else ""})
    return {
        "event_id": e.get("event_id", ""),
        "event_group_id": e.get("event_group_id", ""),
        "event_date": e.get("event_date", ""),
        "text": " ".join(str(content or "").split()),
        "citations": citations[:6],
    }
