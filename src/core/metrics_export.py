"""Export metrics to a SQLite file for Grafana.

Grafana reads a plain SQLite file rather than talking to Firestore directly.
That keeps one dashboard working against both backends, and avoids depending on
a datasource plugin that ships no backend binary (the JSON API plugin registers
and validates but cannot serve queries, failing with `plugin.unavailable`).

The export is a projection for charting, not the source of truth.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import datetime

from . import repo
from . import filings as filings_mod
from . import targets as targets_mod

EXPORT_PATH = Path(os.environ.get("TICKERROOM_METRICS_DB", "data/metrics.db"))

SCHEMA = """
DROP TABLE IF EXISTS coverage;
DROP TABLE IF EXISTS sentiment_now;
DROP TABLE IF EXISTS quotes_now;
CREATE TABLE coverage (ticker TEXT, day TEXT, articles INTEGER);
CREATE TABLE sentiment_now (ticker TEXT, score INTEGER, label TEXT, n_threads INTEGER);
CREATE TABLE quotes_now (ticker TEXT, spot REAL, change_pct REAL);
DROP TABLE IF EXISTS targets_now;
CREATE TABLE targets_now (ticker TEXT, firm TEXT, target_price REAL, rating TEXT,
                          date TEXT, spot REAL, upside_pct REAL);
DROP TABLE IF EXISTS target_consensus;
CREATE TABLE target_consensus (ticker TEXT, spot REAL, avg_target REAL,
                               low_target REAL, high_target REAL, n_firms INTEGER,
                               upside_pct REAL);
DROP TABLE IF EXISTS filings_now;
CREATE TABLE filings_now (ticker TEXT, form_type TEXT, form_meaning TEXT,
                          filed_date TEXT, insider_name TEXT, insider_role TEXT,
                          txn_type TEXT, shares REAL, value_usd REAL,
                          headline TEXT, kind TEXT, ts INTEGER);
DROP TABLE IF EXISTS revisions;
CREATE TABLE revisions (ticker TEXT, firm TEXT, old_price REAL, new_price REAL,
                        change_pct REAL, direction TEXT, date TEXT, ts INTEGER);
"""


def export(user_id: str = "javi") -> dict[str, int]:
    """Project the history into the SQLite file Grafana reads.

    An empty user_id means every ticker anybody follows, which is what the
    scheduled sweep exports: the dashboard covers the whole service, not one
    subscriber's slice of it.
    """
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(EXPORT_PATH)
    conn.executescript(SCHEMA)
    counts = {"coverage": 0, "sentiment": 0, "quotes": 0, "targets": 0,
              "revisions": 0, "filings": 0}

    tickers = repo.all_tickers() if not user_id else repo.get_watchlist(user_id)
    for row in tickers:
        ticker = row["ticker"]
        for point in repo.coverage_series(ticker, days=60):
            conn.execute("INSERT INTO coverage VALUES (?,?,?)",
                         (ticker, point["day"], point["articles"]))
            counts["coverage"] += 1

        s = repo.latest_sentiment(ticker)
        if s:
            conn.execute("INSERT INTO sentiment_now VALUES (?,?,?,?)",
                         (ticker, s.get("score", 0), s.get("label", ""),
                          s.get("n_threads", 0)))
            counts["sentiment"] += 1

        q = repo.latest_quote(ticker)
        if q:
            conn.execute("INSERT INTO quotes_now VALUES (?,?,?)",
                         (ticker, q.get("spot"), q.get("change_pct")))
            counts["quotes"] += 1

        spot = (q or {}).get("spot")
        all_targets = repo.latest_targets(ticker, limit=200)
        current = targets_mod.latest_per_firm(all_targets)

        for t in current:
            price = t.get("target_price")
            upside = round((price - spot) / spot * 100, 1) if spot and price else None
            conn.execute("INSERT INTO targets_now VALUES (?,?,?,?,?,?,?)",
                         (ticker, t.get("firm", ""), price, t.get("rating", ""),
                          t.get("date", ""), spot, upside))
            counts["targets"] += 1

        summary = targets_mod.summarize(all_targets, spot)
        if summary.get("n"):
            conn.execute("INSERT INTO target_consensus VALUES (?,?,?,?,?,?,?)",
                         (ticker, spot, summary.get("average"), summary.get("low"),
                          summary.get("high"), summary.get("firms"),
                          summary.get("upside_pct")))

        # Revisions drive the alert: a firm changing its mind is the signal.
        for r in targets_mod.find_revisions(all_targets):
            ts = 0
            try:
                ts = int(datetime.datetime.strptime(r["date"], "%Y-%m-%d")
                         .replace(tzinfo=datetime.timezone.utc).timestamp())
            except (ValueError, KeyError):
                pass
            conn.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)",
                         (ticker, r["firm"], r["old_price"], r["new_price"],
                          r["change_pct"], r["direction"], r["date"], ts))
            counts["revisions"] += 1

        rows = repo.latest_filings(ticker, limit=50)
        flagged = {id(e): e for e in filings_mod.notable(rows)}
        kinds = {(e["form_type"], e.get("filed_date"), e.get("insider_name")): e["kind"]
                 for e in flagged.values()}
        for f in rows:
            key = (f["form_type"], f.get("filed_date"), f.get("insider_name"))
            ts = 0
            try:
                ts = int(datetime.datetime.strptime(f.get("filed_date", ""), "%Y-%m-%d")
                         .replace(tzinfo=datetime.timezone.utc).timestamp())
            except (ValueError, TypeError):
                pass
            conn.execute("INSERT INTO filings_now VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (ticker, f["form_type"], f.get("form_meaning", ""),
                          f.get("filed_date", ""), f.get("insider_name", ""),
                          f.get("insider_role", ""), f.get("transaction", ""),
                          f.get("shares"), f.get("value_usd"), f.get("headline", ""),
                          kinds.get(key, ""), ts))
            counts["filings"] += 1

    conn.commit()
    conn.close()
    return counts
