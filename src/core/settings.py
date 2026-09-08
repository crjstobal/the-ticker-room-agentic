"""User-adjustable settings, stored in SQLite.

Alerting is off by default: a tool that pushes notifications should be
switched on deliberately, not by installing it.
"""
from __future__ import annotations

from . import storage

DEFAULTS = {
    "alerts_enabled": "0",
    "spike_multiplier": "2.0",   # today vs trailing baseline
    "spike_floor": "5",          # minimum articles before a spike counts
    "run_frequency": "4h",       # 15m | 1h | 4h | daily | weekly | manual
    "reddit_enabled": "1",
    "reddit_window_days": "7",
}


# The blocks a ticker page is made of, in the order they appear. The order is
# fixed in code rather than configurable: it encodes how often each block
# changes, which is not a matter of taste. Alerts is first because it is what
# moves between visits, and Sources last because it is the raw material every
# other block was built from.
#
# There was a Settings control for reordering these. It has been removed: the
# stored order fought the page's structure (a saved order could put the
# briefing below the filings and leave the top of the page looking empty), and
# no order but this one reflects what actually updates.
SECTIONS = [
    # The standing watch, what it caught and what it fired were three separate
    # sections asking one question: what has happened since you last looked.
    # Split across three headings you had to read all three to answer it, and
    # the first two were mostly furniture describing the third.
    # The briefing is rendered above the contents rail rather than inside the
    # column it indexes, but it keeps its entry here so the rail can still
    # link to it and `_sec_h2` can still find its label and explainer.
    ("briefing", "The briefing"),
    ("alerts", "Alerts"),
    ("filings", "SEC filings"),
    ("targets", "Analyst price targets"),
    # Sentiment and coverage were two sections asking the same question from
    # two sides: what people are saying, and how much is being written. They
    # read as one story and are now one block. The reading was never Reddit
    # only either: X has been in it since the sentiment module was written.
    ("social", "Social & coverage"),
    ("sources", "Sources"),
]

SECTION_KEYS = [k for k, _ in SECTIONS]


def section_order(cfg: dict[str, str] | None = None) -> list[str]:
    """The order of the blocks on a ticker page.

    Fixed, and no longer read from settings. The argument is kept so existing
    callers do not have to change; it is ignored.
    """
    return list(SECTION_KEYS)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _ensure(conn) -> None:
    conn.executescript(SCHEMA)
    for k, v in DEFAULTS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()


def all_settings(conn) -> dict[str, str]:
    _ensure(conn)
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def set_many(conn, values: dict[str, str]) -> None:
    _ensure(conn)
    for k, v in values.items():
        if k in DEFAULTS:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, str(v)),
            )
    conn.commit()


def is_on(conn, key: str) -> bool:
    return all_settings(conn).get(key, "0") in ("1", "true", "on", "yes")
