"""Source policy for news research.

The first version returned mostly quote pages: /quotes/ONDS, /stocks/aapl-stock,
finviz quote screens. Those carry a live price and no reporting, so the model
had little to summarize and cited near-identical pages over and over.

Two fixes, both needed:
  1. Exclude the domains that are quote terminals rather than publishers.
  2. Drop URLs whose shape says "quote page" even on a domain we keep,
     since publishers like Yahoo and CNBC serve both.
"""
from __future__ import annotations

import re

# Domains that exist to show a live quote, not to report. Excluded outright.
# Plain hostnames only: the API rejects a domain carrying a path with a 422.
QUOTE_TERMINALS = [
    "stockevents.app", "tipranks.com", "quotemedia.com",
    "public.com", "finviz.com", "marketbeat.com", "gurufocus.com",
    "stockanalysis.com", "investing.com", "revolut.com", "google.com",
    "zacks.com", "markets.businessinsider.com", "chartmill.com",
    "wallstreetzen.com", "simplywall.st", "tradingview.com", "webull.com",
    "robinhood.com", "mexc.co", "barchart.com", "stocktwits.com",
]

# URL shapes that mean "quote page" on any domain.
_QUOTE_SHAPES = re.compile(
    r"(/quotes?/|/quote\.ashx|/market-activity/stocks/|/symbol/|"
    r"/stocks/[a-z]{1,5}(-stock)?/?$|/equities/[a-z-]+/?$|"
    r"/stocks/[a-z]{1,5}/(earnings|forecast|financials|statistics)/?$)",
    re.IGNORECASE,
)

# Reporting we actively want. Used to rank, never to restrict.
PREFERRED = [
    "reuters.com", "bloomberg.com", "cnbc.com", "wsj.com", "ft.com",
    "barrons.com", "seekingalpha.com", "benzinga.com", "marketwatch.com",
    "fool.com", "businesswire.com", "prnewswire.com", "globenewswire.com",
    "sec.gov", "stocktitan.net", "marketscreener.com", "axios.com",
]


# Titles that announce a quote screen no matter what the URL looks like.
_QUOTE_TITLES = re.compile(
    r"(stock (price|quote)|share price|\bquote\b.*\bstock\b|"
    r"price.*forecast.*analyst|stock, price, news, quotes)",
    re.IGNORECASE,
)


def is_quote_page(url: str, title: str = "") -> bool:
    """True if this is a live-quote screen rather than an article.

    Checked on the title as well as the URL: aggregators serve quote screens on
    article-shaped paths, and a briefing built on those has nothing to say.
    """
    if _QUOTE_SHAPES.search(url or ""):
        return True
    return bool(title and _QUOTE_TITLES.search(title))


def news_source_policy() -> dict:
    return {"exclude_domains": list(QUOTE_TERMINALS)}


def drop_quote_pages(results: list[dict]) -> list[dict]:
    return [r for r in results
            if not is_quote_page(r.get("url", ""), r.get("title", ""))]


def rank(results: list[dict]) -> list[dict]:
    """Preferred publishers first; order is otherwise preserved."""
    def key(r: dict) -> int:
        url = (r.get("url") or "").lower()
        return 0 if any(d in url for d in PREFERRED) else 1
    return sorted(results, key=key)
