"""SQLite persistence.

The previous system kept nothing: every run was ephemeral. History is what
turns a report into a product, so every article, price snapshot and briefing
is stored. The schema is deliberately close to a columnar shape so it can move
to ClickHouse later without a rewrite.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# On Cloud Run the container filesystem is ephemeral and read-only outside
# /tmp, so the database path is configurable. A restart there loses history,
# which is acceptable for the demo deployment and is why persistent storage is
# on the backlog.
DB_PATH = Path(
    os.environ.get(
        "TICKERROOM_DB",
        str(Path(__file__).resolve().parents[2] / "data" / "tickerroom.db"),
    )
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    id           INTEGER PRIMARY KEY,
    user_id      TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    company_name TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS articles (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT NOT NULL,
    url        TEXT NOT NULL,
    title      TEXT,
    excerpt    TEXT,
    found_at   TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    UNIQUE(ticker, url)
);

CREATE TABLE IF NOT EXISTS questions (
    id         INTEGER PRIMARY KEY,
    user_id    TEXT NOT NULL,
    kind       TEXT NOT NULL,          -- 'ask' | 'discover'
    question   TEXT NOT NULL,
    ticker     TEXT NOT NULL DEFAULT '',
    answer     TEXT NOT NULL DEFAULT '',
    tools      TEXT NOT NULL DEFAULT '[]',
    n_results  INTEGER NOT NULL DEFAULT 0,
    asked_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id          INTEGER PRIMARY KEY,
    ticker      TEXT NOT NULL,
    spot        REAL,
    change_pct  REAL,
    ma20        REAL,
    ma50        REAL,
    low_52w     REAL,
    high_52w    REAL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS briefings (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT NOT NULL,
    body       TEXT NOT NULL,
    model      TEXT,
    n_articles INTEGER NOT NULL DEFAULT 0,
    -- The exact ordered source list the model was given. The [n] markers in
    -- body are 1-based indexes into this, so it must be stored verbatim.
    sources    TEXT NOT NULL DEFAULT '[]',
    run_id     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    n_tickers   INTEGER NOT NULL DEFAULT 0,
    trigger     TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS sentiment (
    id          INTEGER PRIMARY KEY,
    ticker      TEXT NOT NULL,
    score       INTEGER NOT NULL,
    label       TEXT NOT NULL,
    themes      TEXT NOT NULL DEFAULT '[]',
    summary     TEXT,
    n_threads   INTEGER NOT NULL DEFAULT 0,
    subreddits  TEXT NOT NULL DEFAULT '[]',
    window_days INTEGER NOT NULL DEFAULT 7,
    n_x         INTEGER NOT NULL DEFAULT 0,
    run_id      TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    id           INTEGER PRIMARY KEY,
    ticker       TEXT NOT NULL,
    firm         TEXT NOT NULL,
    analyst      TEXT,
    target_price REAL NOT NULL,
    rating       TEXT,
    date         TEXT,
    source_url   TEXT,
    -- Parallel's basis for the extraction: the sentence each field was read
    -- from, plus a confidence level. Stored so a row can be audited later.
    confidence   TEXT,
    evidence     TEXT NOT NULL DEFAULT '{}',
    run_id       TEXT NOT NULL,
    captured_at  TEXT NOT NULL,
    UNIQUE(ticker, firm, target_price, date)
);

CREATE TABLE IF NOT EXISTS filings (
    id           INTEGER PRIMARY KEY,
    ticker       TEXT NOT NULL,
    form_type    TEXT NOT NULL,
    form_meaning TEXT,
    filed_date   TEXT,
    insider_name TEXT,
    insider_role TEXT,
    txn_type     TEXT,
    shares       REAL,
    value_usd    REAL,
    headline     TEXT NOT NULL,
    source_url   TEXT,
    confidence   TEXT,
    evidence     TEXT NOT NULL DEFAULT '{}',
    run_id       TEXT NOT NULL,
    captured_at  TEXT NOT NULL,
    UNIQUE(ticker, form_type, filed_date, insider_name)
);

CREATE TABLE IF NOT EXISTS monitors (
    monitor_id   TEXT PRIMARY KEY,
    ticker       TEXT NOT NULL,
    company_name TEXT,
    frequency    TEXT,
    processor    TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL
);

-- Events pushed by Parallel when a watched ticker actually changes. Separate
-- from `articles` because these arrive between runs and are not tied to one.
CREATE TABLE IF NOT EXISTS monitor_events (
    event_id     TEXT PRIMARY KEY,
    monitor_id   TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    event_date   TEXT,
    text         TEXT NOT NULL,
    citations    TEXT NOT NULL DEFAULT '[]',
    seen         INTEGER NOT NULL DEFAULT 0,
    received_at  TEXT NOT NULL
);

-- Alerts Grafana has actually fired. The rules already existed and evaluated
-- correctly; what was missing is any record that one went off, so an alert was
-- visible only to whoever happened to be looking at Grafana at the time.
CREATE TABLE IF NOT EXISTS alerts (
    fingerprint  TEXT PRIMARY KEY,
    ticker       TEXT NOT NULL DEFAULT '',
    rule         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT '',
    severity     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'firing',
    summary      TEXT NOT NULL DEFAULT '',
    value        TEXT NOT NULL DEFAULT '',
    started_at   TEXT,
    received_at  TEXT NOT NULL
);

-- Coverage per ticker per day. This is the series Grafana reads to detect
-- news spikes and fire alerts.
CREATE VIEW IF NOT EXISTS coverage_daily AS
SELECT ticker, date(found_at) AS day, COUNT(*) AS articles
FROM articles GROUP BY ticker, date(found_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Columns added after the first schema shipped. CREATE TABLE IF NOT EXISTS does
# not alter an existing table, so new columns are applied explicitly.
MIGRATIONS = [
    ("briefings", "sources", "TEXT NOT NULL DEFAULT '[]'"),
    ("sentiment", "subreddits", "TEXT NOT NULL DEFAULT '[]'"),
    ("sentiment", "window_days", "INTEGER NOT NULL DEFAULT 7"),
    ("sentiment", "n_x", "INTEGER NOT NULL DEFAULT 0"),
    ("sentiment", "posts", "TEXT NOT NULL DEFAULT '[]'"),
    ("targets", "confidence", "TEXT"),
    ("targets", "evidence", "TEXT NOT NULL DEFAULT '{}'"),
    ("filings", "confidence", "TEXT"),
    ("filings", "evidence", "TEXT NOT NULL DEFAULT '{}'"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()


def connect() -> sqlite3.Connection:
    """A fresh connection. Never shared between threads.

    Tickers are researched concurrently, so several threads write here at once.
    Each gets its own connection (SQLite objects are not thread-safe), and two
    settings make that safe rather than merely likely to work:

    - `timeout` makes a writer wait for the lock instead of raising
      "database is locked" the moment another thread is mid-write.
    - WAL lets readers carry on while a write is in flight, which is what the
      web pages are doing while a run is going.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def add_to_watchlist(conn, user_id: str, ticker: str, company_name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO watchlist (user_id, ticker, company_name, created_at)"
        " VALUES (?, ?, ?, ?)",
        (user_id, ticker.upper(), company_name, _now()),
    )
    conn.commit()


def remove_from_watchlist(conn, user_id: str, ticker: str) -> None:
    """Stop watching a ticker.

    The stored history is deliberately left behind: it is what the ticker
    looked like while it was followed, and re-adding it later should not start
    from nothing. Only the watchlist row goes.
    """
    conn.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                 (user_id, ticker.upper()))
    conn.commit()


def get_watchlist(conn, user_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT ticker, company_name FROM watchlist WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()


def save_articles(conn, ticker: str, articles: list[dict], run_id: str) -> int:
    """Store articles, ignoring ones already seen. Returns how many are new."""
    new = 0
    for a in articles:
        excerpts = a.get("excerpts") or []
        cur = conn.execute(
            "INSERT OR IGNORE INTO articles (ticker, url, title, excerpt, found_at, run_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                ticker.upper(),
                a.get("url", ""),
                a.get("title", ""),
                " ".join(str(e) for e in excerpts)[:2000],
                _now(),
                run_id,
            ),
        )
        new += cur.rowcount
    conn.commit()
    return new


def save_quote(conn, quote: dict) -> None:
    conn.execute(
        "INSERT INTO quotes (ticker, spot, change_pct, ma20, ma50, low_52w, high_52w,"
        " captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            quote["ticker"], quote.get("spot"), quote.get("change_pct"),
            quote.get("ma20"), quote.get("ma50"), quote.get("low_52w"),
            quote.get("high_52w"), _now(),
        ),
    )
    conn.commit()


def save_briefing(
    conn, ticker: str, body: str, model: str, sources: list[dict], run_id: str
) -> None:
    """Store the briefing together with the source list its [n] markers cite."""
    slim = [
        {"url": a.get("url", ""), "title": a.get("title", ""),
         "excerpt": (a.get("excerpt") or " ".join(str(e) for e in (a.get("excerpts") or [])))[:400]}
        for a in sources
    ]
    conn.execute(
        "INSERT INTO briefings (ticker, body, model, n_articles, sources, run_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticker.upper(), body, model, len(slim), json.dumps(slim), run_id, _now()),
    )
    conn.commit()


def save_sentiment(conn, ticker: str, s: dict, run_id: str) -> None:
    """Store the reading and the posts it was read from.

    The posts are the citation. Without them the score is a number the page
    asserts and nobody can check, which is the one thing this product must
    never ship: every other figure on a ticker page links back to its source.
    """
    conn.execute(
        "INSERT INTO sentiment (ticker, score, label, themes, summary, n_threads,"
        " subreddits, window_days, n_x, posts, run_id, captured_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ticker.upper(), s.get("score", 0), s.get("label", "quiet"),
         json.dumps(s.get("themes", [])), s.get("summary", ""),
         s.get("n_threads", 0), json.dumps(s.get("subreddits", [])),
         s.get("window_days", 7), s.get("n_x", 0),
         json.dumps(s.get("posts", [])), run_id, _now()),
    )
    conn.commit()


def save_targets(conn, ticker: str, targets: list[dict], run_id: str) -> int:
    """Store analyst targets, ignoring ones already recorded."""
    new = 0
    for t in targets:
        cur = conn.execute(
            "INSERT OR IGNORE INTO targets (ticker, firm, analyst, target_price,"
            " rating, date, source_url, confidence, evidence, run_id, captured_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticker.upper(), t["firm"], t.get("analyst", ""), t["target_price"],
             t.get("rating", ""), t.get("date", ""), t.get("source_url", ""),
             t.get("confidence", ""), json.dumps(t.get("evidence") or {}),
             run_id, _now()),
        )
        new += cur.rowcount
        # A row that already existed is skipped by INSERT OR IGNORE, which would
        # leave it without the evidence this run collected. The figures are
        # unchanged; only the basis is filled in, and only where it is missing.
        if not cur.rowcount and t.get("confidence"):
            conn.execute(
                "UPDATE targets SET confidence = ?, evidence = ?"
                " WHERE ticker = ? AND firm = ? AND target_price = ? AND date = ?"
                " AND COALESCE(confidence, '') = ''",
                (t["confidence"], json.dumps(t.get("evidence") or {}),
                 ticker.upper(), t["firm"], t["target_price"], t.get("date", "")),
            )
    conn.commit()
    return new


def latest_targets(conn, ticker: str, limit: int = 30) -> list[dict]:
    """The most recent targets for a ticker, newest first.

    Ordered by date, not by price. Ordering by `target_price DESC` and then
    capping kept the *highest* targets rather than the newest, and a cut sorts
    low, so the row that mattered fell off the slice first: a firm revising
    $100 down to $50 kept only the $100, `find_revisions` saw no revision, and
    the page reported a stale target as the firm's live call.

    `captured_at` and `id` break ties, because two targets from the same firm
    on the same date are otherwise returned in an arbitrary order, and
    `find_revisions` reads that order as the direction of the revision: the
    same pair could be reported as a 60% cut or a 150% raise.
    """
    rows = conn.execute(
        "SELECT ticker, firm, analyst, target_price, rating, date, source_url,"
        " confidence, evidence, captured_at, id FROM targets"
        " WHERE ticker = ?"
        " ORDER BY date DESC, captured_at DESC, id DESC LIMIT ?",
        (ticker.upper(), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def save_filings(conn, ticker: str, filings: list[dict], run_id: str) -> int:
    """Store filings, ignoring ones already recorded. Returns how many are new."""
    new = 0
    for f in filings:
        cur = conn.execute(
            "INSERT OR IGNORE INTO filings (ticker, form_type, form_meaning,"
            " filed_date, insider_name, insider_role, txn_type, shares,"
            " value_usd, headline, source_url, confidence, evidence, run_id,"
            " captured_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticker.upper(), f["form_type"], f.get("form_meaning", ""),
             f.get("filed_date", ""), f.get("insider_name", ""),
             f.get("insider_role", ""), f.get("transaction", ""),
             f.get("shares"), f.get("value_usd"), f["headline"],
             f.get("source_url", ""), f.get("confidence", ""),
             json.dumps(f.get("evidence") or {}), run_id, _now()),
        )
        new += cur.rowcount
        if not cur.rowcount and f.get("confidence"):
            conn.execute(
                "UPDATE filings SET confidence = ?, evidence = ?"
                " WHERE ticker = ? AND form_type = ? AND filed_date = ?"
                " AND insider_name = ? AND COALESCE(confidence, '') = ''",
                (f["confidence"], json.dumps(f.get("evidence") or {}),
                 ticker.upper(), f["form_type"], f.get("filed_date", ""),
                 f.get("insider_name", "")),
            )
    conn.commit()
    return new


def latest_filings(conn, ticker: str, limit: int = 25) -> list[dict]:
    rows = conn.execute(
        "SELECT form_type, form_meaning, filed_date, insider_name, insider_role,"
        " txn_type AS 'transaction', shares, value_usd, headline, source_url,"
        " confidence, evidence, captured_at, id FROM filings"
        " WHERE ticker = ?"
        " ORDER BY filed_date DESC, captured_at DESC, id DESC LIMIT ?",
        (ticker.upper(), limit),
    ).fetchall()
    return [dict(r) for r in rows]


# How long an unfinished run is still believed to be running. A full pass over
# a watchlist was measured at 486s for two tickers, so this leaves generous
# headroom while still letting an abandoned run fall out of the header.
RUN_STALE_SECONDS = 1800


def start_run(conn, run_id: str, n_tickers: int, trigger: str = "manual") -> None:
    conn.execute(
        "INSERT OR REPLACE INTO runs (run_id, started_at, n_tickers, trigger)"
        " VALUES (?, ?, ?, ?)",
        (run_id, _now(), n_tickers, trigger),
    )
    conn.commit()


def finish_run(conn, run_id: str) -> None:
    conn.execute("UPDATE runs SET finished_at = ? WHERE run_id = ?", (_now(), run_id))
    conn.commit()


def set_run_error(conn, run_id: str, error: str) -> None:
    """Stamp why a run produced nothing, so a page can say so.

    The column is added on the fly because existing databases predate it and a
    missing column here must not stop a run being recorded.
    """
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN error TEXT")
    except Exception:  # noqa: BLE001 - already present is the common case
        pass
    conn.execute("UPDATE runs SET error = ? WHERE run_id = ?", (error, run_id))
    conn.commit()


def last_run(conn) -> dict | None:
    """The most recent *finished* run, plus whether one is in flight now.

    `running` is carried on the same row so every page can say "researching N
    tickers" without a second lookup. Without it the only signal a run had
    started was `finished_at` changing minutes later, so pressing the button
    looked like it had done nothing at all.
    """
    row = conn.execute(
        "SELECT * FROM runs WHERE finished_at IS NOT NULL ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()
    out = dict(row) if row else None

    # A run that died mid-pass never gets its `finished_at`, and the database
    # already holds one from August. Without a cutoff that row would pin the
    # header to "researching" forever, which is a worse lie than saying
    # nothing. A real pass takes minutes, so anything older is abandoned.
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=RUN_STALE_SECONDS)).isoformat()
    active = conn.execute(
        "SELECT run_id, started_at, n_tickers, trigger FROM runs"
        " WHERE finished_at IS NULL AND started_at > ?"
        " ORDER BY started_at DESC LIMIT 1",
        (cutoff,),
    ).fetchone()
    if active:
        out = out or {}
        out["running"] = dict(active)
    return out


# --- monitors ----------------------------------------------------------

def save_monitor(conn, m: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO monitors (monitor_id, ticker, company_name,"
        " frequency, processor, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (m["monitor_id"], m["ticker"].upper(), m.get("company_name", ""),
         m.get("frequency", ""), m.get("processor", ""),
         m.get("status", "active"), m.get("created_at") or _now()),
    )
    conn.commit()


def set_monitor_status(conn, monitor_id: str, status: str) -> None:
    conn.execute("UPDATE monitors SET status = ? WHERE monitor_id = ?",
                 (status, monitor_id))
    conn.commit()


def get_monitors(conn, active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM monitors"
    if active_only:
        sql += " WHERE status = 'active'"
    return [dict(r) for r in conn.execute(sql + " ORDER BY ticker")]


def monitor_for_ticker(conn, ticker: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM monitors WHERE ticker = ? AND status = 'active' LIMIT 1",
        (ticker.upper(),),
    ).fetchone()
    return dict(row) if row else None


def save_monitor_event(conn, monitor_id: str, ticker: str, e: dict) -> int:
    """Store one event. Returns 1 if it is new, 0 if already recorded.

    An event with no text is dropped. Monitor occasionally returns an entry
    with no `event_id`, no `event_date` and nothing to say; stored, it became a
    row with a timestamp and no sentence under it, which reads as a bug in the
    product. It also lands under the synthesised id `<monitor_id>:`, so the
    next empty one collides with it rather than accumulating.
    """
    if not (e.get("text") or "").strip():
        return 0
    cur = conn.execute(
        "INSERT OR IGNORE INTO monitor_events (event_id, monitor_id, ticker,"
        " event_date, text, citations, received_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (e.get("event_id") or f"{monitor_id}:{e.get('event_date', '')}",
         monitor_id, ticker.upper(), e.get("event_date", ""), e.get("text", ""),
         json.dumps(e.get("citations") or []), _now()),
    )
    conn.commit()
    return cur.rowcount


def replace_filings(conn, ticker: str, old_rows: list[dict], keeper: dict) -> int:
    """Delete duplicate filing rows and insert one merged row in their place.

    The table's UNIQUE key includes `insider_name`, so the duplicates are
    genuinely separate rows rather than a constraint that failed. Deleted by
    the same three fields that identified them.
    """
    deleted = 0
    for row in old_rows:
        cur = conn.execute(
            "DELETE FROM filings WHERE ticker = ? AND form_type = ?"
            " AND COALESCE(filed_date,'') = ? AND COALESCE(insider_name,'') = ?",
            (ticker.upper(), row.get("form_type", ""),
             row.get("filed_date", ""), row.get("insider_name", "")),
        )
        deleted += cur.rowcount
    save_filings(conn, ticker, [keeper], keeper.get("run_id", "dedupe"))
    conn.commit()
    return deleted


def save_question(conn, user_id: str, q: dict) -> int:
    """Record one question and what came back.

    A question costs twenty seconds and a paid API call, and until now it was
    thrown away the moment the tab closed: the same question asked twice was
    paid for twice, and nobody could see what they had already asked.
    """
    cur = conn.execute(
        "INSERT INTO questions (user_id, kind, question, ticker, answer,"
        " tools, n_results, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, q.get("kind", "ask"), q.get("question", ""),
         q.get("ticker", ""), q.get("answer", ""),
         json.dumps(q.get("tools") or []), int(q.get("n_results") or 0), _now()),
    )
    conn.commit()
    return cur.lastrowid or 0


def recent_questions(conn, user_id: str, kind: str = "", limit: int = 30) -> list[dict]:
    """Questions asked, newest first, optionally of one kind."""
    sql = "SELECT * FROM questions WHERE user_id = ?"
    args: list = [user_id]
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    sql += " ORDER BY asked_at DESC, id DESC LIMIT ?"
    args.append(limit)
    out = []
    for row in conn.execute(sql, args).fetchall():
        d = dict(row)
        try:
            d["tools"] = json.loads(d.get("tools") or "[]")
        except (ValueError, TypeError):
            d["tools"] = []
        out.append(d)
    return out


def find_question(conn, user_id: str, question: str,
                  kind: str = "ask") -> dict | None:
    """The most recent stored answer to exactly this question, if there is one.

    Matched on the text, lowercased and whitespace-collapsed, because the same
    question arriving from a history link is character-for-character the one
    that was asked. Anything looser would serve an answer to a different
    question, which is worse than making the reader wait.
    """
    key = " ".join((question or "").split()).lower()
    if not key:
        return None
    row = conn.execute(
        "SELECT * FROM questions WHERE user_id = ? AND kind = ?"
        " AND LOWER(TRIM(question)) = ? ORDER BY asked_at DESC, id DESC LIMIT 1",
        (user_id, kind, key),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["tools"] = json.loads(d.get("tools") or "[]")
    except (ValueError, TypeError):
        d["tools"] = []
    return d


def save_alert(conn, a: dict) -> int:
    """Record one fired alert. Returns 1 if new or changed, 0 if unchanged.

    Keyed on Grafana's own fingerprint, which is stable for a given rule and
    label set, so a repeat notification about the same still-firing condition
    updates the row rather than adding another. A resolve arrives with the same
    fingerprint and a different status, which is why status is written on
    conflict.
    """
    cur = conn.execute(
        "INSERT INTO alerts (fingerprint, ticker, rule, kind, severity, status,"
        " summary, value, started_at, received_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(fingerprint) DO UPDATE SET"
        "   status=excluded.status, value=excluded.value,"
        "   received_at=excluded.received_at"
        " WHERE alerts.status != excluded.status",
        (a["fingerprint"], a.get("ticker", ""), a.get("rule", ""),
         a.get("kind", ""), a.get("severity", ""), a.get("status", "firing"),
         a.get("summary", ""), a.get("value", ""), a.get("started_at", ""),
         _now()),
    )
    conn.commit()
    return cur.rowcount


def recent_alerts(conn, ticker: str = "", limit: int = 20) -> list[dict]:
    sql = "SELECT * FROM alerts"
    args: tuple = ()
    if ticker:
        sql += " WHERE ticker = ?"
        args = (ticker.upper(),)
    sql += " ORDER BY received_at DESC LIMIT ?"
    return [dict(r) for r in conn.execute(sql, args + (limit,)).fetchall()]


def recent_events(conn, ticker: str = "", limit: int = 20) -> list[dict]:
    sql = "SELECT * FROM monitor_events"
    args: tuple = ()
    if ticker:
        sql += " WHERE ticker = ?"
        args = (ticker.upper(),)
    sql += " ORDER BY COALESCE(NULLIF(event_date,''), received_at) DESC LIMIT ?"
    rows = conn.execute(sql, args + (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["citations"] = json.loads(d.get("citations") or "[]")
        out.append(d)
    return out
