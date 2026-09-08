"""Storage-agnostic access to the history.

Local development uses SQLite (no network, no credentials). The deployed
service uses Firestore, because Cloud Run's filesystem does not survive a
restart. Everything above this module is written against these functions and
does not know which backend is active.

Set TICKERROOM_BACKEND=firestore to force Firestore; it is chosen automatically
when running on Cloud Run (which sets K_SERVICE).
"""
from __future__ import annotations

import os

from . import storage


def use_firestore() -> bool:
    explicit = os.environ.get("TICKERROOM_BACKEND", "").lower()
    if explicit:
        return explicit == "firestore"
    return bool(os.environ.get("K_SERVICE"))  # set by Cloud Run


def backend_name() -> str:
    return "firestore" if use_firestore() else "sqlite"


# Firestore is imported lazily so local runs never need the dependency.
def _fs():
    from ..adapters import firestore_store

    return firestore_store


# --- watchlist ---------------------------------------------------------

def add_to_watchlist(user_id: str, ticker: str, company_name: str) -> None:
    if use_firestore():
        return _fs().add_to_watchlist(user_id, ticker, company_name)
    conn = storage.connect()
    try:
        storage.add_to_watchlist(conn, user_id, ticker, company_name)
    finally:
        conn.close()


def remove_from_watchlist(user_id: str, ticker: str) -> None:
    if use_firestore():
        return _fs().remove_from_watchlist(user_id, ticker)
    conn = storage.connect()
    try:
        storage.remove_from_watchlist(conn, user_id, ticker)
    finally:
        conn.close()


def get_watchlist(user_id: str) -> list[dict]:
    if use_firestore():
        return _fs().get_watchlist(user_id)
    conn = storage.connect()
    try:
        return [dict(r) for r in storage.get_watchlist(conn, user_id)]
    finally:
        conn.close()


# --- writes during a run ----------------------------------------------

def start_run(run_id: str, n_tickers: int, trigger: str = "manual") -> None:
    if use_firestore():
        return _fs().start_run(run_id, n_tickers, trigger)
    conn = storage.connect()
    try:
        storage.start_run(conn, run_id, n_tickers, trigger)
    finally:
        conn.close()


def set_run_error(run_id: str, error: str) -> None:
    """Record why a run came back empty, so the UI never has to guess."""
    if use_firestore():
        return _fs().set_run_error(run_id, error)
    conn = storage.connect()
    try:
        storage.set_run_error(conn, run_id, error)
    finally:
        conn.close()


def finish_run(run_id: str) -> None:
    if use_firestore():
        return _fs().finish_run(run_id)
    conn = storage.connect()
    try:
        storage.finish_run(conn, run_id)
    finally:
        conn.close()


def save_articles(ticker: str, articles: list[dict], run_id: str) -> int:
    if use_firestore():
        return _fs().save_articles(ticker, articles, run_id)
    conn = storage.connect()
    try:
        return storage.save_articles(conn, ticker, articles, run_id)
    finally:
        conn.close()


def save_quote(quote: dict) -> None:
    if use_firestore():
        return _fs().save_quote(quote)
    conn = storage.connect()
    try:
        storage.save_quote(conn, quote)
    finally:
        conn.close()


def save_briefing(ticker: str, body: str, model: str, sources: list[dict], run_id: str) -> None:
    if use_firestore():
        return _fs().save_briefing(ticker, body, model, sources, run_id)
    conn = storage.connect()
    try:
        storage.save_briefing(conn, ticker, body, model, sources, run_id)
    finally:
        conn.close()


def save_sentiment(ticker: str, s: dict, run_id: str) -> None:
    if use_firestore():
        return _fs().save_sentiment(ticker, s, run_id)
    conn = storage.connect()
    try:
        storage.save_sentiment(conn, ticker, s, run_id)
    finally:
        conn.close()


def save_targets(ticker: str, targets: list[dict], run_id: str) -> int:
    if not targets:
        return 0
    if use_firestore():
        return _fs().save_targets(ticker, targets, run_id)
    conn = storage.connect()
    try:
        return storage.save_targets(conn, ticker, targets, run_id)
    finally:
        conn.close()


def target_revisions(ticker: str, min_pct: float = 10.0) -> list[dict]:
    """Firms that changed their target for this ticker."""
    from . import targets as targets_mod

    return targets_mod.find_revisions(latest_targets(ticker, limit=200),
                                      min_pct=min_pct)


def latest_targets(ticker: str, limit: int = 30) -> list[dict]:
    if use_firestore():
        return _fs().latest_targets(ticker, limit)
    conn = storage.connect()
    try:
        return storage.latest_targets(conn, ticker, limit)
    finally:
        conn.close()


def save_filings(ticker: str, filings: list[dict], run_id: str) -> int:
    if not filings:
        return 0
    if use_firestore():
        return _fs().save_filings(ticker, filings, run_id)
    conn = storage.connect()
    try:
        return storage.save_filings(conn, ticker, filings, run_id)
    finally:
        conn.close()


def latest_filings(ticker: str, limit: int = 25) -> list[dict]:
    if use_firestore():
        return _fs().latest_filings(ticker, limit)
    conn = storage.connect()
    try:
        return storage.latest_filings(conn, ticker, limit)
    finally:
        conn.close()


# --- reads for the pages ----------------------------------------------

def latest_briefings(user_id: str) -> list[dict]:
    if use_firestore():
        fs = _fs()
        out = []
        for row in fs.get_watchlist(user_id):
            b = fs.latest_briefing(row["ticker"]) or {}
            out.append({
                "ticker": row["ticker"], "company_name": row["company_name"],
                "body": b.get("body"), "created_at": b.get("created_at"),
                "n_articles": b.get("n_articles", 0), "sources": b.get("sources", []),
            })
        return out
    from . import history

    conn = storage.connect()
    try:
        return history.latest_briefings(conn, user_id)
    finally:
        conn.close()


def latest_quote(ticker: str) -> dict | None:
    if use_firestore():
        return _fs().latest_quote(ticker)
    from . import history

    conn = storage.connect()
    try:
        return history.latest_quote(conn, ticker)
    finally:
        conn.close()


def latest_sentiment(ticker: str) -> dict | None:
    if use_firestore():
        return _fs().latest_sentiment(ticker)
    from . import history

    conn = storage.connect()
    try:
        return history.latest_sentiment(conn, ticker)
    finally:
        conn.close()


def recent_articles(ticker: str, limit: int = 12) -> list[dict]:
    if use_firestore():
        return _fs().recent_articles(ticker, limit)
    from . import history

    conn = storage.connect()
    try:
        return history.recent_articles(conn, ticker, limit)
    finally:
        conn.close()


def coverage_series(ticker: str, days: int = 30) -> list[dict]:
    if use_firestore():
        return _fs().coverage_series(ticker, days)
    from . import history

    conn = storage.connect()
    try:
        return history.coverage_series(conn, ticker, days)
    finally:
        conn.close()


def last_run() -> dict | None:
    if use_firestore():
        return _fs().last_run()
    conn = storage.connect()
    try:
        return storage.last_run(conn)
    finally:
        conn.close()


def all_tickers() -> list[dict]:
    """Every ticker followed by anybody, once each.

    Firestore used to read one hardcoded user's watchlist here, which made the
    answer wrong the moment a second user existed. Both backends now return the
    distinct set: SQLite with DISTINCT, Firestore by collapsing the collection.
    """
    if use_firestore():
        return _fs().distinct_tickers()
    from . import history

    conn = storage.connect()
    try:
        return history.all_tickers(conn)
    finally:
        conn.close()


# --- settings ----------------------------------------------------------

def all_settings() -> dict[str, str]:
    from . import settings as s

    if use_firestore():
        return _fs().all_settings(s.DEFAULTS)
    conn = storage.connect()
    try:
        return s.all_settings(conn)
    finally:
        conn.close()


def set_settings(values: dict[str, str]) -> None:
    from . import settings as s

    if use_firestore():
        return _fs().set_many({k: v for k, v in values.items() if k in s.DEFAULTS})
    conn = storage.connect()
    try:
        s.set_many(conn, values)
    finally:
        conn.close()


# --- monitors ----------------------------------------------------------
#
# Monitors are Parallel-side objects; what is stored locally is the mapping
# from a ticker to the watch that covers it, plus the events that arrived.

def save_monitor(m: dict) -> None:
    if use_firestore():
        return _fs().save_monitor(m)
    conn = storage.connect()
    try:
        storage.save_monitor(conn, m)
    finally:
        conn.close()


def set_monitor_status(monitor_id: str, status: str) -> None:
    if use_firestore():
        return _fs().set_monitor_status(monitor_id, status)
    conn = storage.connect()
    try:
        storage.set_monitor_status(conn, monitor_id, status)
    finally:
        conn.close()


def get_monitors(active_only: bool = True) -> list[dict]:
    if use_firestore():
        return _fs().get_monitors(active_only)
    conn = storage.connect()
    try:
        return storage.get_monitors(conn, active_only)
    finally:
        conn.close()


def monitor_for_ticker(ticker: str) -> dict | None:
    if use_firestore():
        return _fs().monitor_for_ticker(ticker)
    conn = storage.connect()
    try:
        return storage.monitor_for_ticker(conn, ticker)
    finally:
        conn.close()


def save_monitor_event(monitor_id: str, ticker: str, event: dict) -> int:
    if use_firestore():
        return _fs().save_monitor_event(monitor_id, ticker, event)
    conn = storage.connect()
    try:
        return storage.save_monitor_event(conn, monitor_id, ticker, event)
    finally:
        conn.close()


def recent_events(ticker: str = "", limit: int = 20) -> list[dict]:
    if use_firestore():
        return _fs().recent_events(ticker, limit)
    conn = storage.connect()
    try:
        return storage.recent_events(conn, ticker, limit)
    finally:
        conn.close()


def replace_filings(ticker: str, old_rows: list[dict], keeper: dict) -> int:
    """Collapse duplicate filing rows into one. Used by scripts/dedupe_filings.py."""
    if use_firestore():
        return _fs().replace_filings(ticker, old_rows, keeper)
    conn = storage.connect()
    try:
        return storage.replace_filings(conn, ticker, old_rows, keeper)
    finally:
        conn.close()


def corpus_stats() -> dict:
    """Counts for the front page, read from stored history.

    Every figure the landing page shows comes from here. Nothing is estimated
    and nothing is a constant in a template: a research tool that invents its
    own track record on its front page has undermined the only thing it sells.
    Any count that cannot be read comes back as 0 and is then omitted.
    """
    out = {"tickers": 0, "articles": 0, "events": 0, "targets": 0, "filings": 0}
    try:
        if use_firestore():
            fs = _fs()
            wl = fs.get_watchlist("javi")
            out["tickers"] = len(wl)
            out["events"] = len(fs.recent_events("", 200))
            for row in wl:
                out["targets"] += len(fs.latest_targets(row["ticker"], 200))
                out["filings"] += len(fs.latest_filings(row["ticker"], 200))
            out["articles"] = fs.count_articles() if hasattr(fs, "count_articles") else 0
            return out
        conn = storage.connect()
        try:
            for key, sql in (
                ("tickers", "SELECT COUNT(*) FROM watchlist"),
                ("articles", "SELECT COUNT(*) FROM articles"),
                ("events", "SELECT COUNT(*) FROM monitor_events"),
                ("targets", "SELECT COUNT(*) FROM targets"),
                ("filings", "SELECT COUNT(*) FROM filings"),
            ):
                out[key] = conn.execute(sql).fetchone()[0] or 0
        finally:
            conn.close()
    except Exception as exc:
        print(f"[repo] corpus_stats: {exc}")
    return out


# --- alerts ------------------------------------------------------------

def save_question(user_id: str, q: dict) -> int:
    """Record a question and its answer, so it can be found again."""
    if use_firestore():
        return _fs().save_question(user_id, q)
    conn = storage.connect()
    try:
        return storage.save_question(conn, user_id, q)
    finally:
        conn.close()


def recent_questions(user_id: str, kind: str = "", limit: int = 30) -> list[dict]:
    if use_firestore():
        return _fs().recent_questions(user_id, kind, limit)
    conn = storage.connect()
    try:
        return storage.recent_questions(conn, user_id, kind, limit)
    finally:
        conn.close()


def find_question(user_id: str, question: str,
                  kind: str = "ask") -> dict | None:
    """A stored answer to exactly this question, or None."""
    if use_firestore():
        return _fs().find_question(user_id, question, kind)
    conn = storage.connect()
    try:
        return storage.find_question(conn, user_id, question, kind)
    finally:
        conn.close()


def save_alert(alert: dict) -> int:
    """Record an alert Grafana fired. Returns 1 if it is news."""
    if use_firestore():
        return _fs().save_alert(alert)
    conn = storage.connect()
    try:
        return storage.save_alert(conn, alert)
    finally:
        conn.close()


def recent_alerts(ticker: str = "", limit: int = 20) -> list[dict]:
    if use_firestore():
        return _fs().recent_alerts(ticker, limit)
    conn = storage.connect()
    try:
        return storage.recent_alerts(conn, ticker, limit)
    finally:
        conn.close()


# --- citation previews -------------------------------------------------

def repair_previews(sources: list[dict], *, objective: str = "") -> list[dict]:
    """Fill in citation excerpts that are unusable, using Parallel's Extract API.

    Search excerpts are whatever the index captured, which is often nav bars and
    cookie banners. The preview card rejects those (correctly), and the result
    was a hover that showed nothing. Extract goes back to the page for a clean
    passage.

    Only the broken ones are sent, and only for a briefing being displayed, so
    the cost is a handful of URLs rather than every article ever stored.
    """
    from . import extract
    from ..web.citations import readable

    broken = [s.get("url", "") for s in sources
              if s.get("url") and not readable(s.get("excerpt") or "")]
    if not broken:
        return sources

    repaired = extract.fetch(broken, objective=objective)
    if not repaired:
        return sources

    out = []
    for src in sources:
        text = repaired.get(src.get("url", ""))
        out.append({**src, "excerpt": text} if text else src)
    return out
