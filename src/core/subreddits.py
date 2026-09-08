"""Which corners of Reddit to read, and how much to trust each one.

Not all discussion is equal. A thesis in r/ValueInvesting and a one-line YOLO in
r/wallstreetbets are both sentiment, but they are not the same evidence, so each
subreddit carries a weight used when aggregating a score.

Weights are about the kind of reasoning a sub rewards, not about being right.
"""
from __future__ import annotations

import re

# Broad finance subs worth reading for any ticker.
GENERAL = {
    "ValueInvesting": 1.4,
    "SecurityAnalysis": 1.4,
    "investing": 1.2,
    "stocks": 1.0,
    "StockMarket": 0.9,
    "options": 1.0,
    "Daytrading": 0.7,
    "swingtrading": 0.8,
    "pennystocks": 0.6,
    "wallstreetbets": 0.8,   # highest volume, lowest signal per post
    "wallstreetbetsELITE": 0.5,
    "stockstobuytoday": 0.4,
    "smallstreetbets": 0.5,
}

# Subs that exist for one company. Discovered per ticker, high weight: the
# people posting there follow the company closely.
TICKER_SUB_WEIGHT = 1.3

DEFAULT_WEIGHT = 0.6  # anything else that mentions the ticker

_SUB_RE = re.compile(r"reddit\.com/r/([A-Za-z0-9_]+)", re.IGNORECASE)


def subreddit_of(url: str) -> str | None:
    m = _SUB_RE.search(url or "")
    return m.group(1) if m else None


def candidate_subs(ticker: str, company_name: str) -> list[str]:
    """General finance subs plus the ones likely dedicated to this company."""
    company_slug = re.sub(r"[^A-Za-z0-9]", "", company_name or "")
    ticker_subs = [ticker.upper(), ticker.lower(), f"{ticker.lower()}stock",
                   f"{company_slug}", f"{company_slug}stock"]
    seen, out = set(), []
    for s in list(GENERAL) + ticker_subs:
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def weight_for(url: str, ticker: str, company_name: str) -> float:
    """How much this thread counts toward the aggregate score."""
    sub = subreddit_of(url)
    if not sub:
        return 0.0
    for name, w in GENERAL.items():
        if sub.lower() == name.lower():
            return w
    slug = re.sub(r"[^a-z0-9]", "", (company_name or "").lower())
    if sub.lower() in {ticker.lower(), f"{ticker.lower()}stock", slug, f"{slug}stock"}:
        return TICKER_SUB_WEIGHT
    return DEFAULT_WEIGHT


def is_thread(url: str) -> bool:
    """A real discussion, not a subreddit listing or search page."""
    return "/comments/" in (url or "") and "/search" not in (url or "")


# --- Post age -----------------------------------------------------------
# Reddit post IDs are base36 counters that only ever increase, so an id maps to
# an approximate date. This is a second line of defence: `after_date` on the
# search still lets the occasional old thread through, and scoring a 2022 post
# as today's mood is the failure this whole module exists to prevent.
_ID_RE = re.compile(r"/comments/([a-z0-9]+)", re.IGNORECASE)

# One calibration point and a rate, rather than two anchors.
#
# The previous version used a second anchor of (4_058_392_672, 2026.6). That id
# is `1v49fts`, and Reddit has issued nothing near it: real ids in 2026 are in
# the `1n`/`1o` range, around 3.6e9. The anchor therefore claimed today's posts
# should be ~430 million ids higher than they are, so every genuinely fresh
# thread was dated roughly a year into the past and `is_recent` rejected it.
# The measured effect was total: 0 of 7 real September-2026 ids survived, so
# `search_reddit` returned nothing on every run and the sentiment reading
# quietly fell back to X alone.
#
# `_ANCHOR` is a real post (`1elrqg1`, August 2024) and is kept.
#
# The rate is measured over 2024-2026, not over the whole 7-character era. The
# era began at `1000000` in mid-2023, which implies ~7.5e8 ids/year, but that
# was a faster period: applying it forward puts today at `247jnpy`, far past
# anything Reddit has issued. Ids observed in 2026 are in the `1n`/`1o` range,
# which pins the recent rate between 2.5e8 and 2.8e8 per year. The midpoint is
# used, so the estimate is good to a few months either way.
#
# Two-sided error matters here. Too high and old threads pass as fresh; too low
# and fresh threads are dated into the past and dropped, which is the failure
# that took the Reddit half of sentiment offline entirely. `keep_recent` below
# is what makes the second kind survivable.
_ANCHOR = (3_059_874_721, 2024.62)   # post id 1elrqg1, August 2024
_IDS_PER_YEAR = 262_000_000


def _b36(s: str) -> int:
    value = 0
    for ch in s.lower():
        value = value * 36 + int(ch, 36)
    return value


def approx_year(url: str) -> float | None:
    """Rough decimal year for a Reddit post, from its id. None if unparseable.

    Accurate to a few months at best. Use it to sort or to label, never as the
    sole reason to discard a thread.
    """
    m = _ID_RE.search(url or "")
    if not m:
        return None
    try:
        n = _b36(m.group(1))
    except ValueError:
        return None
    n0, y0 = _ANCHOR
    return y0 + (n - n0) / _IDS_PER_YEAR


def is_recent(url: str, today_year: float, max_age_years: float = 0.5) -> bool:
    """Keep a thread only if its id says it is recent enough.

    Unparseable ids are kept: a heuristic should not silently drop evidence.

    An id that dates to the *future* is also kept. The estimate drifts as
    Reddit's posting rate changes, and drift in that direction means the rate
    is running behind reality, not that the post is fake.
    """
    year = approx_year(url)
    if year is None or year > today_year:
        return True
    return year >= today_year - max_age_years


def keep_recent(urls_with_rows, today_year: float, max_age_years: float):
    """Filter threads by age, but never return nothing when there was something.

    The id heuristic is calibrated approximations all the way down, and when it
    drifts it does not degrade gracefully: it rejects the entire result set and
    the product reports "no discussion" for a ticker people are actively
    arguing about. That is indistinguishable from a genuine quiet week, which
    is what let a totally broken filter sit unnoticed.

    So the rule is: if the filter would discard *everything*, it is the filter
    that is wrong, not the evidence. Fall back to the newest threads by id and
    let the reading proceed.
    """
    rows = list(urls_with_rows)
    if not rows:
        return []
    fresh = [r for r in rows
             if is_recent(r.get("url", ""), today_year, max_age_years)]
    if fresh:
        return fresh
    print("[subreddits] id-age filter rejected all "
          f"{len(rows)} threads; falling back to the newest by id")
    ranked = sorted(rows, key=lambda r: approx_year(r.get("url", "")) or 0.0,
                    reverse=True)
    return ranked[:12]
