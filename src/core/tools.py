"""Tools the analyst agent can call.

These are plain functions over the stored history and the live web. The agent
decides which to call and in what order; the scheduled research pipeline stays
deterministic and is untouched by this.

Every reading carries its own age. A stored row has no timestamp the model can
see once it is turned into a number, so a quote captured a fortnight ago and
one captured this morning arrived looking identical, and the model reported the
old one as "currently trading at". `_age` puts the staleness in the payload,
next to the value it qualifies, so the answer can say how old the fact is.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import quotes, repo, research

# Beyond this a stored reading is described as stale and the agent is told to
# confirm it against the live web before quoting it as current. Roughly a
# trading day: a price older than that is not "now" by any useful reading.
STALE_AFTER_HOURS = 24


def _age(iso: str | None) -> dict:
    """How old a stored reading is, in words the model can quote.

    Returns the fields flat rather than a nested object: nested metadata gets
    summarised away, and the point is that the age travels with the value.
    """
    if not iso:
        return {"as_of": "unknown", "age": "unknown age", "is_stale": True}
    try:
        then = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return {"as_of": str(iso), "age": "unknown age", "is_stale": True}

    hours = (datetime.now(timezone.utc) - then).total_seconds() / 3600
    if hours < 1:
        age = "less than an hour ago"
    elif hours < 48:
        age = f"{round(hours)} hours ago"
    else:
        age = f"{round(hours / 24)} days ago"
    return {"as_of": then.date().isoformat(), "age": age,
            "is_stale": hours > STALE_AFTER_HOURS}


def get_price(ticker: str) -> dict:
    """Current price and technical context for a ticker.

    The stored quote is preferred, but a stale one is refreshed rather than
    returned: price is the single field where age matters most, and this is
    one cheap call.
    """
    ticker = ticker.upper()
    q = repo.latest_quote(ticker)
    age = _age((q or {}).get("captured_at"))
    if not q or age["is_stale"]:
        fresh = quotes.fetch_quote(ticker)
        if fresh:
            q = fresh
            # A freshly fetched quote may carry no timestamp of its own; it was
            # just fetched, so say so rather than calling it unknown and stale.
            age = (_age(fresh["captured_at"]) if fresh.get("captured_at")
                   else {"as_of": "just now", "age": "just now", "is_stale": False})
    if not q:
        return {"error": f"No price data for {ticker}."}
    return {
        "ticker": ticker, "spot": q.get("spot"),
        "change_pct": q.get("change_pct"), "ma20": q.get("ma20"),
        "ma50": q.get("ma50"), "low_52w": q.get("low_52w"),
        "high_52w": q.get("high_52w"), **age,
    }


def get_coverage_history(ticker: str) -> dict:
    """How many articles were found per day, to spot attention spikes."""
    ticker = ticker.upper()
    series = repo.coverage_series(ticker, days=60)
    if not series:
        return {"ticker": ticker, "days": [], "note": "No history stored yet."}
    counts = [d["articles"] for d in series]
    avg = sum(counts) / len(counts)
    # The last day with any coverage dates the series: a 60-day window whose
    # newest entry is a fortnight old describes a fortnight ago, not now.
    latest = max((d["day"] for d in series if d.get("articles")), default="")
    return {
        "ticker": ticker,
        "days": series,
        "average_per_day": round(avg, 2),
        "busiest_day": max(series, key=lambda d: d["articles"]),
        "most_recent_day_with_coverage": latest,
        **_age(latest),
    }


def get_stored_articles(ticker: str) -> dict:
    """Headlines already collected for a ticker, newest first."""
    ticker = ticker.upper()
    arts = repo.recent_articles(ticker, limit=15)
    newest = arts[0].get("found_at") if arts else None
    return {"ticker": ticker,
            "articles": [{"title": a.get("title"), "url": a.get("url"),
                          "found_at": a.get("found_at")} for a in arts],
            **_age(newest)}


def get_sentiment(ticker: str) -> dict:
    """The most recent Reddit sentiment reading, with its provenance."""
    ticker = ticker.upper()
    s = repo.latest_sentiment(ticker)
    if not s:
        return {"ticker": ticker, "note": "No sentiment reading stored."}
    return {
        "ticker": ticker, "score": s.get("score"), "label": s.get("label"),
        "themes": s.get("themes", []), "summary": s.get("summary"),
        "n_threads": s.get("n_threads"), "subreddits": s.get("subreddits", []),
        **_age(s.get("captured_at")),
    }


def search_web(ticker: str, company_name: str = "") -> dict:
    """Search the live web when the stored history does not answer the question."""
    ticker = ticker.upper()
    arts = research.search_news(ticker, company_name or ticker)
    return {"ticker": ticker, "as_of": "just now", "age": "live",
            "is_stale": False,
            "results": [{"title": a.get("title"), "url": a.get("url"),
                         "excerpt": " ".join(str(e) for e in (a.get("excerpts") or []))[:400]}
                        for a in arts[:8]]}


REGISTRY = {
    "get_price": get_price,
    "get_coverage_history": get_coverage_history,
    "get_stored_articles": get_stored_articles,
    "get_sentiment": get_sentiment,
    "search_web": search_web,
}
