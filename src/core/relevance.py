"""Relevance filtering for search results.

A result only survives if it actually mentions the company. This is not
cosmetic: without it the model is handed articles about other companies and
presents them as fact.
"""
from __future__ import annotations

import re
from typing import Iterable

# Words that are not the company even when they look like it.
_TICKER_MIN_LEN = 2


def _patterns(ticker: str, company_name: str) -> list[re.Pattern[str]]:
    pats = []
    if ticker and len(ticker) >= _TICKER_MIN_LEN:
        # Word boundaries, never substring: "ONDS" must not match "seconds"
        # or "bonds", which is a real failure this guards against.
        pats.append(re.compile(rf"\b{re.escape(ticker)}\b", re.IGNORECASE))
    if company_name:
        core = re.sub(
            r"\b(inc|corp|corporation|holdings|ltd|llc|plc|co|group|sa|nv)\b\.?",
            "",
            company_name,
            flags=re.IGNORECASE,
        ).strip(" ,.")
        if core:
            pats.append(re.compile(rf"\b{re.escape(core)}\b", re.IGNORECASE))
    return pats


def mentions(text: str, ticker: str, company_name: str) -> bool:
    """True if the text really refers to this company."""
    if not text:
        return False
    return any(p.search(text) for p in _patterns(ticker, company_name))


def filter_results(
    results: Iterable[dict], ticker: str, company_name: str
) -> list[dict]:
    """Keep only results that mention the company by ticker or real name.

    Returning an empty list is a valid, honest answer: the report says
    "no news" rather than showing someone else's headlines.
    """
    kept = []
    for r in results:
        haystack = " ".join(
            str(r.get(f, "")) for f in ("title", "url", "excerpt", "content")
        )
        excerpts = r.get("excerpts") or []
        if excerpts:
            haystack += " " + " ".join(str(e) for e in excerpts)
        if mentions(haystack, ticker, company_name):
            kept.append(r)
    return kept
