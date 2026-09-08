"""Firestore persistence for the deployed service.

Cloud Run's filesystem is ephemeral, so a SQLite file there survives only until
the container restarts. Firestore keeps the history across restarts, scales to
zero, and stays inside the free tier at this volume.

Local development keeps using SQLite: it needs no network and no credentials.
The two are chosen at runtime by `storage.backend()`.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

# Same cutoff as the SQLite backend, imported rather than restated so the two
# cannot drift apart.
from ..core.storage import RUN_STALE_SECONDS

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "ticker-room")


@lru_cache(maxsize=1)
def _db():
    from google.cloud import firestore

    return firestore.Client(project=PROJECT)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_id(*parts: str) -> str:
    """A deterministic id, so re-storing the same thing overwrites rather than
    duplicating. Slashes are not allowed in Firestore document ids."""
    return "_".join(parts).replace("/", "|")[:1500]


# --- watchlist ---------------------------------------------------------

def remove_from_watchlist(user_id: str, ticker: str) -> None:
    """Stop watching a ticker; the stored history is left behind."""
    _db().collection("watchlist").document(_doc_id(user_id, ticker.upper())).delete()


def add_to_watchlist(user_id: str, ticker: str, company_name: str) -> None:
    _db().collection("watchlist").document(_doc_id(user_id, ticker.upper())).set(
        {"user_id": user_id, "ticker": ticker.upper(),
         "company_name": company_name, "created_at": _now()}
    )


def get_watchlist(user_id: str) -> list[dict]:
    docs = _db().collection("watchlist").where("user_id", "==", user_id).stream()
    return sorted((d.to_dict() for d in docs), key=lambda r: r["ticker"])


def distinct_tickers() -> list[dict]:
    """Every ticker any user follows, once each.

    A ticker is researched, not a subscription: the articles, filings and
    targets stored for ONDS are the same document whoever asked for them.
    Twenty users watching ONDS is one research pass, not twenty, so the
    scheduler walks this rather than looping over watchlists. Without it the
    Parallel bill grows with users times tickers instead of with tickers.
    """
    seen: dict[str, dict] = {}
    for doc in _db().collection("watchlist").stream():
        row = doc.to_dict() or {}
        ticker = (row.get("ticker") or "").upper()
        if ticker and ticker not in seen:
            seen[ticker] = {"ticker": ticker,
                            "company_name": row.get("company_name", "")}
    return sorted(seen.values(), key=lambda r: r["ticker"])


# --- articles ----------------------------------------------------------

def save_articles(ticker: str, articles: list[dict], run_id: str) -> int:
    db = _db()
    batch = db.batch()
    new = 0
    for a in articles:
        url = a.get("url", "")
        if not url:
            continue
        ref = db.collection("articles").document(_doc_id(ticker.upper(), url))
        if ref.get().exists:
            continue
        excerpts = a.get("excerpts") or []
        batch.set(ref, {
            "ticker": ticker.upper(), "url": url, "title": a.get("title", ""),
            "excerpt": " ".join(str(e) for e in excerpts)[:2000],
            "found_at": _now(), "day": datetime.now(timezone.utc).date().isoformat(),
            "run_id": run_id,
        })
        new += 1
    if new:
        batch.commit()
    return new


def recent_articles(ticker: str, limit: int = 12) -> list[dict]:
    from google.cloud import firestore

    docs = (_db().collection("articles").where("ticker", "==", ticker)
            .order_by("found_at", direction=firestore.Query.DESCENDING)
            .limit(limit).stream())
    return [d.to_dict() for d in docs]


def coverage_series(ticker: str, days: int = 30) -> list[dict]:
    """Articles per day, counted client-side: the volume is small and it avoids
    needing a composite index for an aggregation query."""
    docs = _db().collection("articles").where("ticker", "==", ticker).stream()
    counts: dict[str, int] = {}
    for d in docs:
        day = d.to_dict().get("day")
        if day:
            counts[day] = counts.get(day, 0) + 1
    ordered = sorted(counts.items())[-days:]
    return [{"day": k, "articles": v} for k, v in ordered]


# --- quotes, briefings, sentiment --------------------------------------

def save_quote(quote: dict) -> None:
    _db().collection("quotes").add({**quote, "captured_at": _now()})


def latest_quote(ticker: str) -> dict | None:
    from google.cloud import firestore

    docs = list(_db().collection("quotes").where("ticker", "==", ticker)
                .order_by("captured_at", direction=firestore.Query.DESCENDING)
                .limit(1).stream())
    if not docs:
        return None
    # Same derivation as the SQLite path: documents written before the field
    # existed do not carry it, and the page must not show a permanent dash.
    from ..core.history import with_derived

    return with_derived(docs[0].to_dict())


def save_briefing(ticker: str, body: str, model: str, sources: list[dict], run_id: str) -> None:
    slim = [{"url": a.get("url", ""), "title": a.get("title", ""),
             "excerpt": (a.get("excerpt") or " ".join(
                 str(e) for e in (a.get("excerpts") or [])))[:400]}
            for a in sources]
    _db().collection("briefings").add({
        "ticker": ticker.upper(), "body": body, "model": model,
        "n_articles": len(slim), "sources": slim,
        "run_id": run_id, "created_at": _now(),
    })


def latest_briefing(ticker: str) -> dict | None:
    from google.cloud import firestore

    docs = list(_db().collection("briefings").where("ticker", "==", ticker)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(1).stream())
    return docs[0].to_dict() if docs else None


def save_sentiment(ticker: str, s: dict, run_id: str) -> None:
    _db().collection("sentiment").add({
        "ticker": ticker.upper(), "score": s.get("score", 0),
        "label": s.get("label", "quiet"), "themes": s.get("themes", []),
        "summary": s.get("summary", ""), "n_threads": s.get("n_threads", 0),
        # Firestore rejects nested arrays, and subreddits arrives as a list of
        # (name, count) pairs. Stored as objects and read back as pairs.
        "subreddits": [{"name": n, "count": c} for n, c in s.get("subreddits", [])],
        "window_days": s.get("window_days", 7),
        "n_x": s.get("n_x", 0),
        # The posts the reading was based on, so the score can be checked.
        "posts": s.get("posts", []),
        "run_id": run_id, "captured_at": _now(),
    })


def latest_sentiment(ticker: str) -> dict | None:
    from google.cloud import firestore

    docs = list(_db().collection("sentiment").where("ticker", "==", ticker)
                .order_by("captured_at", direction=firestore.Query.DESCENDING)
                .limit(1).stream())
    if not docs:
        return None
    d = docs[0].to_dict()
    d["subreddits"] = [(x["name"], x["count"]) for x in d.get("subreddits", [])]
    d.setdefault("posts", [])
    return d


def save_targets(ticker: str, targets: list[dict], run_id: str) -> int:
    db = _db()
    batch = db.batch()
    for t in targets:
        ref = db.collection("targets").document(
            _doc_id(ticker.upper(), t["firm"], str(t["target_price"]), t.get("date", ""))
        )
        batch.set(ref, {**t, "ticker": ticker.upper(), "run_id": run_id,
                        "captured_at": _now()})
    batch.commit()
    return len(targets)


def latest_targets(ticker: str, limit: int = 30) -> list[dict]:
    """The most recent targets, newest first.

    The order_by matters as much as it does in SQLite: `.limit()` with no
    ordering takes an arbitrary server-side slice, so which targets a page
    showed could change between refreshes, and a firm's revision could fall
    out of the slice entirely. Sorted by date so the cap keeps the newest.
    """
    from google.cloud import firestore

    docs = (_db().collection("targets").where("ticker", "==", ticker.upper())
            .order_by("date", direction=firestore.Query.DESCENDING)
            .order_by("captured_at", direction=firestore.Query.DESCENDING)
            .limit(limit).stream())
    return [d.to_dict() for d in docs]


def save_filings(ticker: str, filings: list[dict], run_id: str) -> int:
    db = _db()
    batch = db.batch()
    for f in filings:
        ref = db.collection("filings").document(_doc_id(
            ticker.upper(), f["form_type"], f.get("filed_date", ""),
            f.get("insider_name", "")))
        batch.set(ref, {**f, "ticker": ticker.upper(), "run_id": run_id,
                        "captured_at": _now()})
    batch.commit()
    return len(filings)


def latest_filings(ticker: str, limit: int = 25) -> list[dict]:
    """The most recent filings, newest first. Ordered server-side so the cap
    keeps the newest rather than an arbitrary slice."""
    from google.cloud import firestore

    docs = (_db().collection("filings").where("ticker", "==", ticker.upper())
            .order_by("filed_date", direction=firestore.Query.DESCENDING)
            .order_by("captured_at", direction=firestore.Query.DESCENDING)
            .limit(limit).stream())
    return [d.to_dict() for d in docs]


def replace_filings(ticker: str, old_rows: list[dict], keeper: dict) -> int:
    """Delete a set of duplicate filing documents and write one merged row.

    The document id is derived from the raw insider name, which is why three
    spellings of one person became three documents. The merged row is written
    under the id its own (already normalised) name produces, and every original
    is deleted, including the one whose id may coincide with the new row's.
    Written before the deletes so a failure midway leaves the data present
    rather than missing.
    """
    db = _db()
    new_id = _doc_id(ticker.upper(), keeper["form_type"],
                     keeper.get("filed_date", ""), keeper.get("insider_name", ""))
    db.collection("filings").document(new_id).set(
        {**keeper, "ticker": ticker.upper()})

    batch = db.batch()
    deleted = 0
    for row in old_rows:
        doc_id = _doc_id(ticker.upper(), row.get("form_type", ""),
                         row.get("filed_date", ""), row.get("insider_name", ""))
        if doc_id == new_id:
            continue
        batch.delete(db.collection("filings").document(doc_id))
        deleted += 1
    batch.commit()
    return deleted


# --- runs --------------------------------------------------------------

def start_run(run_id: str, n_tickers: int, trigger: str = "manual") -> None:
    _db().collection("runs").document(run_id).set(
        {"run_id": run_id, "started_at": _now(), "n_tickers": n_tickers,
         "trigger": trigger, "finished_at": None}
    )


def finish_run(run_id: str) -> None:
    _db().collection("runs").document(run_id).update({"finished_at": _now()})


def set_run_error(run_id: str, error: str) -> None:
    """Stamp why a run produced nothing, so a page can say so."""
    _db().collection("runs").document(run_id).update({"error": error})


def last_run() -> dict | None:
    from google.cloud import firestore

    docs = [d.to_dict() for d in _db().collection("runs")
            .order_by("started_at", direction=firestore.Query.DESCENDING)
            .limit(5).stream()]

    out = next((r for r in docs if r.get("finished_at")), None)

    # Mirrors the SQLite backend: an unfinished recent run is reported as in
    # flight so the header can say so, and one older than the cutoff is
    # treated as abandoned rather than pinning the page to "researching".
    cutoff = (datetime.now(timezone.utc)
              - timedelta(seconds=RUN_STALE_SECONDS)).isoformat()
    active = next((r for r in docs
                   if not r.get("finished_at")
                   and str(r.get("started_at", "")) > cutoff), None)
    if active:
        out = out or {}
        out["running"] = active
    return out


# --- settings ----------------------------------------------------------

def all_settings(defaults: dict[str, str]) -> dict[str, str]:
    doc = _db().collection("config").document("settings").get()
    stored = doc.to_dict() if doc.exists else {}
    return {**defaults, **(stored or {})}


def set_many(values: dict[str, str]) -> None:
    _db().collection("config").document("settings").set(values, merge=True)


# --- monitors ----------------------------------------------------------

def save_monitor(m: dict) -> None:
    _db().collection("monitors").document(m["monitor_id"]).set({
        "monitor_id": m["monitor_id"], "ticker": m["ticker"].upper(),
        "company_name": m.get("company_name", ""),
        "frequency": m.get("frequency", ""), "processor": m.get("processor", ""),
        "status": m.get("status", "active"),
        "created_at": m.get("created_at") or _now(),
    })


def set_monitor_status(monitor_id: str, status: str) -> None:
    _db().collection("monitors").document(monitor_id).update({"status": status})


def get_monitors(active_only: bool = True) -> list[dict]:
    col = _db().collection("monitors")
    query = col.where("status", "==", "active") if active_only else col
    return sorted((d.to_dict() for d in query.stream()),
                  key=lambda m: m.get("ticker", ""))


def monitor_for_ticker(ticker: str) -> dict | None:
    docs = (_db().collection("monitors").where("ticker", "==", ticker.upper())
            .where("status", "==", "active").limit(1).stream())
    for d in docs:
        return d.to_dict()
    return None


def save_monitor_event(monitor_id: str, ticker: str, e: dict) -> int:
    """Store one event, returning 1 if it was new.

    Firestore `set` is an upsert with no "did it exist" answer, so existence is
    checked first: the count is what tells the caller whether to alert.

    An event with no text is dropped, matching the SQLite path: Monitor can
    return an entry with nothing to say, and stored it renders as a timestamp
    with no sentence under it.
    """
    if not (e.get("text") or "").strip():
        return 0
    event_id = e.get("event_id") or _doc_id(monitor_id, e.get("event_date", ""))
    ref = _db().collection("monitor_events").document(_doc_id(event_id))
    if ref.get().exists:
        return 0
    ref.set({
        "event_id": event_id, "monitor_id": monitor_id, "ticker": ticker.upper(),
        "event_date": e.get("event_date", ""), "text": e.get("text", ""),
        "citations": e.get("citations") or [], "seen": 0, "received_at": _now(),
    })
    return 1


def count_articles() -> int:
    """How many articles the corpus holds.

    Firestore has no cheap COUNT, so this uses an aggregation query where the
    client supports one and falls back to a bounded scan otherwise. The number
    is shown on the front page and nowhere decisions are made, so a fallback
    ceiling is acceptable where an unbounded scan would not be.
    """
    col = _db().collection("articles")
    try:
        return int(col.count().get()[0][0].value)
    except Exception:
        return sum(1 for _ in col.limit(5000).stream())


def save_question(user_id: str, q: dict) -> int:
    """Record one question and what came back. See storage.save_question."""
    _db().collection("questions").add({
        "user_id": user_id,
        "kind": q.get("kind", "ask"),
        "question": q.get("question", ""),
        "ticker": q.get("ticker", ""),
        "answer": q.get("answer", ""),
        "tools": list(q.get("tools") or []),
        "n_results": int(q.get("n_results") or 0),
        "asked_at": _now(),
    })
    return 1


def recent_questions(user_id: str, kind: str = "", limit: int = 30) -> list[dict]:
    """Questions asked, newest first.

    Ordered server-side, which needs a composite index per filter shape: a
    `.limit()` without `order_by` returns an arbitrary slice, not the newest.
    """
    from google.cloud import firestore

    query = _db().collection("questions").where("user_id", "==", user_id)
    if kind:
        query = query.where("kind", "==", kind)
    docs = query.order_by("asked_at", direction=firestore.Query.DESCENDING) \
                .limit(limit).stream()
    return [d.to_dict() for d in docs]


def find_question(user_id: str, question: str,
                  kind: str = "ask") -> dict | None:
    """The most recent stored answer to exactly this question. See storage."""
    key = " ".join((question or "").split()).lower()
    if not key:
        return None
    # Filtered in Python rather than with a third where(): Firestore has no
    # case-insensitive comparison, so an equality filter would miss a question
    # that differs only in capitalisation, and adding a normalised field would
    # need a third composite index for one lookup.
    for row in recent_questions(user_id, kind, 60):
        if " ".join((row.get("question") or "").split()).lower() == key:
            return row
    return None


def save_alert(a: dict) -> int:
    """Record a fired alert. 1 if new or the status changed, else 0.

    Mirrors the SQLite path: the fingerprint is the identity, and a repeat
    notification about a condition that is still firing is not news.
    """
    ref = _db().collection("alerts").document(_doc_id(a["fingerprint"]))
    snap = ref.get()
    if snap.exists and (snap.to_dict() or {}).get("status") == a.get("status"):
        return 0
    ref.set({
        "fingerprint": a["fingerprint"], "ticker": a.get("ticker", ""),
        "rule": a.get("rule", ""), "kind": a.get("kind", ""),
        "severity": a.get("severity", ""), "status": a.get("status", "firing"),
        "summary": a.get("summary", ""), "value": a.get("value", ""),
        "started_at": a.get("started_at", ""), "received_at": _now(),
    })
    return 1


try:  # pragma: no cover - import shape differs across client versions
    from google.api_core.exceptions import FailedPrecondition as _FailedPrecondition
except Exception:  # noqa: BLE001
    _FailedPrecondition = ()


def _sorted_fallback(query, limit: int, *fields: str) -> list[dict]:
    """Newest-first without the index, for the minutes one takes to build.

    Reads a wider slab than asked for and sorts it here. Still an arbitrary
    slab, so this is a stopgap and not the steady state: it exists so a page
    stays up while Firestore builds the index, not as the way these are read.
    """
    rows = [d.to_dict() for d in query.limit(max(limit * 5, 50)).stream()]
    rows.sort(key=lambda r: next((r.get(f) or "" for f in fields if r.get(f)), ""),
              reverse=True)
    return rows[:limit]


# Ordered server-side, for the reason spelled out on recent_questions: a
# `.limit()` with no `order_by` is an arbitrary slice the server picked, so
# sorting it afterwards sorts a random sample and calls it "newest". These two
# used to do exactly that, which meant the deployed service and a local SQLite
# run disagreed about which alerts were the latest.
def recent_alerts(ticker: str = "", limit: int = 20) -> list[dict]:
    from google.cloud import firestore

    col = _db().collection("alerts")
    query = col.where("ticker", "==", ticker.upper()) if ticker else col
    ordered = query.order_by("received_at", direction=firestore.Query.DESCENDING)
    try:
        return [d.to_dict() for d in ordered.limit(limit).stream()]
    except _FailedPrecondition:
        return _sorted_fallback(query, limit, "received_at")


def recent_events(ticker: str = "", limit: int = 20) -> list[dict]:
    from google.cloud import firestore

    col = _db().collection("monitor_events")
    query = col.where("ticker", "==", ticker.upper()) if ticker else col
    # Ordered by event_date, which is the field the reader sees. Rows missing
    # one sort last rather than being dropped.
    ordered = query.order_by("event_date", direction=firestore.Query.DESCENDING)
    try:
        return [d.to_dict() for d in ordered.limit(limit).stream()]
    except _FailedPrecondition:
        # The composite index is declared but still building, which takes
        # minutes. Falling back to an unordered read keeps the page up with
        # slightly stale ordering instead of answering 500: a section that is
        # briefly out of order is a smaller lie than a broken company page.
        return _sorted_fallback(query, limit, "event_date", "received_at")
