"""Read-side queries over the stored history."""
from __future__ import annotations

import json

from . import storage


def latest_briefings(conn, user_id: str) -> list[dict]:
    """Most recent briefing per ticker on the user's watchlist."""
    rows = conn.execute(
        """
        SELECT w.ticker, w.company_name, b.body, b.created_at, b.n_articles, b.sources
        FROM watchlist w
        LEFT JOIN briefings b ON b.id = (
            SELECT id FROM briefings WHERE ticker = w.ticker
            ORDER BY created_at DESC LIMIT 1
        )
        WHERE w.user_id = ? ORDER BY w.ticker
        """,
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["sources"] = json.loads(d.get("sources") or "[]")
        except (TypeError, ValueError):
            d["sources"] = []
        out.append(d)
    return out


def last_run(conn) -> dict | None:
    from . import storage
    return storage.last_run(conn)


def latest_sentiment(conn, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM sentiment WHERE ticker = ? ORDER BY captured_at DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d.setdefault("n_x", 0)
    for field in ("themes", "subreddits", "posts"):
        try:
            d[field] = json.loads(d.get(field) or "[]")
        except (TypeError, ValueError):
            d[field] = []
    return d


def latest_quote(conn, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM quotes WHERE ticker = ? ORDER BY captured_at DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return with_derived(dict(row)) if row else None


def with_derived(q: dict) -> dict:
    """Add the figures the quotes table does not store.

    `fetch_quote` computes "off 52-week high" but the table has no column for
    it, so it was dropped on the way in and the page rendered a permanent "—"
    for a stat it had all the inputs for. It is a pure function of two stored
    columns, so it is derived on read rather than migrated in.
    """
    spot, high = q.get("spot"), q.get("high_52w")
    if q.get("pct_off_52w_high") is None and spot and high:
        q["pct_off_52w_high"] = round((spot - high) / high * 100, 2)
    return q


def recent_articles(conn, ticker: str, limit: int = 12) -> list[dict]:
    rows = conn.execute(
        "SELECT title, url, found_at FROM articles WHERE ticker = ?"
        " ORDER BY found_at DESC LIMIT ?",
        (ticker, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def coverage_series(conn, ticker: str, days: int = 30) -> list[dict]:
    """Articles per day. This is the series that surfaces news spikes."""
    rows = conn.execute(
        "SELECT day, articles FROM coverage_daily WHERE ticker = ?"
        " ORDER BY day DESC LIMIT ?",
        (ticker, days),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def all_tickers(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT DISTINCT ticker, company_name FROM watchlist ORDER BY ticker"
    ).fetchall()
    return [dict(r) for r in rows]
