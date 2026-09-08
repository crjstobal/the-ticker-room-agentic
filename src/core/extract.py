"""Clean page text for a URL, with Parallel's Extract API.

Search excerpts are whatever the index happened to capture, which is often
page furniture: nav bars, cookie banners, markdown link soup. The citation
previews worked around that by requiring prose and showing nothing when the
excerpt failed the test, so a reader hovering a citation frequently got an
empty box.

Extract goes back to the page and returns LLM-ready content, so a preview can
show a real sentence instead of nothing. It is a repair path, not a default:
it costs a call per URL, so only citations that failed the prose test are sent.
"""
from __future__ import annotations

import re

from .parallel_api import NoCredit, ParallelError, request

EXTRACT_PATH = "/v1/extract"

# The API takes a list. Passing `url` (singular) is a 422 naming the missing
# `urls` field, which is easy to misread as an auth problem. The request body
# accepts only `urls` and `objective`: any other key is rejected outright, and
# `excerpts` in particular is a *response* field, not a request one.
MAX_URLS_PER_CALL = 10

# Extract returns markdown, so headings and list bullets arrive as syntax. A
# preview is one line of prose, so the markup is stripped rather than shown.
# Stripping happens before whitespace is collapsed, because once newlines are
# gone a heading marker is no longer at the start of a line.
_MD_LINE = re.compile(r"^[#>\-\*\+\s]+", re.MULTILINE)
# Some pages come back with their meta block as leading "title:"/"description:"
# lines. That is metadata about the page, not a sentence from it.
# `\A` as well as `^`: an excerpt often begins mid-document, so the first key
# is not at the start of a line.
_FRONTMATTER = re.compile(
    r"(?:^|\A)\s*(?:title|description|url|source|author|date|keywords)\s*:\s*",
    re.IGNORECASE | re.MULTILINE)
_MD_INLINE = re.compile(r"\*\*|__|`|\[([^\]]*)\]\([^)]*\)")


def fetch(urls: list[str], *, objective: str = "", max_chars: int = 1200) -> dict[str, str]:
    """Map each URL to a readable excerpt. Missing keys mean nothing usable.

    Returns {} rather than raising: a preview is a nicety, and no part of a
    briefing should fail because a hover card could not be improved.
    """
    clean = [u for u in dict.fromkeys(urls) if u.startswith("http")][:MAX_URLS_PER_CALL]
    if not clean:
        return {}

    body: dict = {"urls": clean}
    if objective:
        # With an objective the API returns the parts of the page relevant to
        # it, which for a citation is the passage the claim came from.
        body["objective"] = objective

    try:
        payload = request(EXTRACT_PATH, body, timeout=90)
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[extract] {exc}")
        return {}

    out: dict[str, str] = {}
    for r in payload.get("results") or []:
        url = (r.get("url") or "").strip()
        text = _best_text(r, max_chars)
        if url and text:
            out[url] = text
    return out


def _best_text(result: dict, max_chars: int) -> str:
    """The most quotable text in one result: excerpts first, then full content."""
    parts: list[str] = []
    for e in result.get("excerpts") or []:
        parts.append(e if isinstance(e, str) else str(e.get("text", "")))
    if not parts:
        content = result.get("content") or result.get("full_content") or ""
        parts = [content if isinstance(content, str) else str(content)]

    raw = "\n".join(p for p in parts if p)
    # Markup first: a metadata line arrives as "# title: ...", so the key is
    # only at the start of its line once the heading marker is gone.
    text = _MD_LINE.sub("", raw)
    text = _FRONTMATTER.sub("", text)
    text = _MD_INLINE.sub(r"\1", text)
    # Drop the "..." Parallel inserts between non-adjacent passages, which
    # reads as a truncation bug in a preview card.
    text = " ".join(text.split()).replace(" ... ", " ")
    return text[:max_chars]
