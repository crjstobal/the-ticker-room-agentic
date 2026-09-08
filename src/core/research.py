"""Web research over the Parallel API.

Parallel replaces the previous Brave -> Tavily fallback ladder: it indexes the
small-cap and niche financial sources that were the reason two providers were
needed in the first place.

Search modes are chosen per job rather than globally. The three searches here
want different things: the news feeding the briefing wants quality, the social
sweeps want breadth and speed across many queries.
"""
from __future__ import annotations

import datetime
from typing import Any

from .parallel_api import NoCredit, ParallelError, request
from .relevance import filter_results
from .sources import drop_quote_pages, news_source_policy, rank
from .subreddits import (approx_year, candidate_subs, is_thread, keep_recent,
                         subreddit_of, weight_for)

SEARCH_PATH = "/v1beta/search"

# `one-shot` is built for exactly this shape of use: one request that has to
# answer a question on its own. Measured against the same query on the older
# `/v1/search`, it returns roughly three times the excerpt text in half the
# latency, and excerpt text is what the briefing is written from, so this is
# the single highest-leverage setting in the product.
#
# `agentic` returns deliberately terser excerpts for a model calling search in
# a loop, which is the opposite of what a briefing wants. `fast` is the cheap
# preset and the right one for the social sweeps, where the reading is a count
# over many posts and one thinner result changes nothing.
NEWS_MODE = "one-shot"
SOCIAL_MODE = "fast"
DEFAULT_MODE = NEWS_MODE

# `excerpts.max_chars_per_result` is a ceiling, not a target, and setting one
# costs text rather than buying it. Measured on the same query: `one-shot` with
# no cap averages ~3000 characters per result, and asking for 2500 returns
# ~1050. So news sets no cap at all and takes what the mode gives.
#
# The social sweeps do cap. There the reading is a count over many posts, a
# Reddit thread's excerpt is mostly other people's replies, and thirty
# uncapped threads is a large payload to buy a number that three sentences
# each would have produced just as well.
SOCIAL_CHARS = 900


def _search(body: dict[str, Any], label: str) -> list[dict]:
    """Run a search, returning [] on failure. Research never aborts a run."""
    try:
        return request(SEARCH_PATH, body).get("results", []) or []
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[research] {label}: {exc}")
        return []


def search_news(
    ticker: str,
    company_name: str,
    *,
    mode: str = NEWS_MODE,
    days: int = 7,
) -> list[dict]:
    """Search recent news for one company and drop anything not about it.

    The queries use the real company name rather than a generic keyword soup:
    a query like "stock news catalysts analyst rating" makes the engine ignore
    the ticker and return whatever is hot in the sector instead.
    """
    body = {
        "objective": (
            f"News articles published in the last 7 days reporting on {company_name} "
            f"({ticker}): contracts, filings, earnings, analyst moves and material "
            f"events. Reporting and press releases only, not live quote pages."
        ),
        # Several angles and an explicit cap. Without max_results the API
        # returns its small default: RDDT was getting 2 articles, so every
        # citation in the briefing pointed at the same piece.
        "search_queries": [
            f"{ticker} stock news",
            f"{company_name} announces",
            f"{company_name} {ticker} analyst reaction",
            f"{company_name} earnings results",
        ],
        "mode": mode,
        "max_results": 30,
        "fetch_policy": {"max_age_seconds": 3600},
        "source_policy": {
            **news_source_policy(),
            # Without this the index returns coverage from previous years,
            # which then gets summarized as if it were this week's news.
            #
            # It must be `after_date`. The API also documents
            # `freshness_start_date`, and that key is silently ignored:
            # measured against the same query it behaves exactly like a
            # misspelled key, returning results back to 2023. Verified by
            # sending a deliberately bogus key as a control and getting an
            # identical result set.
            "after_date": (
                datetime.date.today() - datetime.timedelta(days=days)
            ).isoformat(),
        },
    }
    # News is a secondary source: the report ships without it.
    results = drop_quote_pages(_search(body, f"news {ticker}"))
    kept = rank(filter_results(results, ticker, company_name))

    # A briefing built on one or two articles cites the same piece repeatedly.
    # If the tight window came back thin, widen it once rather than pretending
    # there is nothing to report.
    if len(kept) < 5:
        body["source_policy"].pop("after_date", None)
        wider = rank(filter_results(
            drop_quote_pages(_search(body, f"news {ticker} (widened)")),
            ticker, company_name))
        seen = {a.get("url") for a in kept}
        kept.extend(a for a in wider if a.get("url") not in seen)

    return kept


def search_reddit(
    ticker: str,
    company_name: str,
    *,
    mode: str = SOCIAL_MODE,
    days: int = 7,
) -> list[dict]:
    """Recent Reddit discussion, restricted to a time window.

    Two things matter here and neither is optional:

    - **Recency.** Without `after_date` the index happily returns threads from
      2024 and 2025, and scoring those as today's mood is worse than having no
      sentiment at all.
    - **Where.** A thesis in r/ValueInvesting and a one-liner in r/wallstreetbets
      are not the same evidence, so each thread carries a weight.

    Reached through Parallel rather than Reddit's own API: since the Responsible
    Builder Policy closed self-service registration in late 2025, a new OAuth
    client needs a manually reviewed ticket, and the free tier is non-commercial.
    """
    today = datetime.date.today()
    today_year = today.year + (today.timetuple().tm_yday / 365.0)
    subs = candidate_subs(ticker, company_name)

    # `after_date` is applied by the index against its own record of a page's
    # publication date, which for Reddit is often missing or wrong. Asking for a
    # narrow window therefore drops threads that ARE recent, and how badly varies
    # by ticker: a 7-day window returned 3 AAPL threads where an unfiltered
    # search returned 18. So the window is requested generously and recency is
    # enforced afterwards from the post id, which is reliable.
    since = (today - datetime.timedelta(days=max(days * 4, 60))).isoformat()

    body = {
        "objective": (
            f"Reddit discussion about {company_name} ({ticker}) stock. What retail "
            f"investors are saying: bullish or bearish views, the catalysts being "
            f"argued over, and how much attention the ticker is getting. "
            f"Prefer r/{', r/'.join(subs[:6])}."
        ),
        # Several angles, because one phrasing reaches one pocket of the index:
        # the ticker's own subreddit, the general finance subs, and the
        # bull/bear framing each surface different threads.
        "search_queries": [
            f"r/{ticker} {company_name} posts",
            f"{ticker} stock discussion this week",
            f"{company_name} {ticker} bullish bearish thesis",
            f"{company_name} stock talk retail investors",
        ],
        "mode": mode,
        "max_results": 30,
        "excerpts": {"max_chars_per_result": SOCIAL_CHARS},
        "source_policy": {"include_domains": ["reddit.com"], "after_date": since},
    }
    results = _search(body, f"reddit {ticker}")
    threads = [r for r in results if is_thread(r.get("url", ""))]
    threads = filter_results(threads, ticker, company_name)

    # Enforce recency from the post id, which is reliable where the index's own
    # publication dates are not.
    #
    # The tolerance is deliberately generous. The id heuristic is calibrated
    # against two known posts and is accurate to roughly a month, so cutting at
    # exactly `days` throws away threads that really are recent: a 7-day window
    # once reduced 10 genuine ONDS threads to 3. Discarding real discussion is
    # the worse error, since the whole point is to read what people are saying.
    ID_PRECISION_YEARS = 0.25  # the estimate is good to a few months, not weeks
    max_age = max(days / 365.0, 0.0) + ID_PRECISION_YEARS
    # keep_recent, not a plain filter: if the age estimate drifts it rejects
    # every thread at once, and "no discussion" reads as a quiet week rather
    # than a broken pipeline. It falls back to the newest instead.
    fresh = keep_recent(threads, today_year, max_age)
    window_used = days

    for t in fresh:
        url = t.get("url", "")
        t["subreddit"] = subreddit_of(url)
        t["weight"] = weight_for(url, ticker, company_name)
        t["approx_year"] = approx_year(url)
        t["window_days"] = window_used

    fresh.sort(key=lambda t: t.get("weight", 0), reverse=True)
    return fresh


def search_x(
    ticker: str,
    company_name: str,
    *,
    mode: str = SOCIAL_MODE,
) -> list[dict]:
    """Posts about a ticker on X.

    Reddit alone is thin for most tickers: five threads is an anecdote, not a
    reading. X carries the cashtag conversation ($ONDS) that Reddit does not,
    so the two together give the sentiment something to stand on.

    The post text arrives in the result title, since X renders the body behind
    a login wall that the index sees only partly.
    """
    body = {
        "objective": (
            f"What people are posting on X about {company_name} ({ticker}) stock: "
            f"opinions, analysis and reactions from investors and analysts"
        ),
        # More angles and a higher cap: the earlier version asked for 20 results
        # across 3 queries and kept 17, which is a ceiling, not a measurement.
        "search_queries": [
            f"${ticker} stock",
            f"{company_name} {ticker}",
            f"${ticker} analysis",
            f"${ticker} price target",
            f"${ticker} earnings reaction",
        ],
        "mode": mode,
        "max_results": 40,
        "excerpts": {"max_chars_per_result": SOCIAL_CHARS},
        "source_policy": {"include_domains": ["x.com", "twitter.com"]},
    }
    posts = []
    for r in _search(body, f"X {ticker}"):
        url = r.get("url", "")
        # Individual posts only: profile and search pages carry no opinion.
        if "/status/" not in url:
            continue
        title = r.get("title") or ""
        # "Author on X: \"the post text\"" — the text is what matters.
        text = title.split(" on X: ", 1)[-1].strip().strip('"')
        author = title.split(" on X: ", 1)[0].strip() if " on X: " in title else ""
        # A post with no readable text contributes nothing to a sentiment
        # reading, and counting it inflates the apparent sample size.
        if len(text) < 25 or text in ("X", "/ X"):
            continue
        posts.append({**r, "post_text": text, "author": author, "platform": "x"})

    return filter_results(posts, ticker, company_name)
