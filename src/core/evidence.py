"""Per-field evidence returned by Parallel's Task API alongside an answer.

Parallel does not just return an extracted value, it returns why it believes
it: the URL it read, the sentence it read there, its reasoning, and a
confidence level. A real response looks like this:

    {"field": "ceo",
     "citations": [{"url": "http://ondas.com/leadership",
                    "excerpts": ["Eric Brock is the Founder ... and CEO."]}],
     "reasoning": "Ondas's official leadership page identifies ...",
     "confidence": "high"}

This product once badged an insider *sale* as a purchase in green. Extracted
rows are inferences about the world, and showing them without the sentence
they came from asks the reader to trust an extraction they cannot check.

The basis is per-field for the whole task run, not per-row, so it is attached
to a result set rather than to individual records.
"""
from __future__ import annotations

import json

import re

# Ordered worst to best, so a set of fields can be reduced to its weakest link.
_RANK = {"low": 0, "medium": 1, "high": 2}

# Excerpts are frequently scraped table rows rather than sentences:
# "Date |Brokerage |Analyst |Action |Rating |Price Target | |8/18/2026 |[Roth".
# Quoting that as "the sentence this came from" is worse than quoting nothing,
# so an excerpt has to look like prose to be offered as evidence.
_PIPE_TABLE = re.compile(r"\|")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")

# Excerpts from a scraped page arrive as markdown, and an SEC filing index is
# the worst case: the hover card showed a reader
# `**Huffman Steve Ladd** 2\. Issuer Name **and** ...`, which is the evidence
# for a claim rendered as raw syntax. The emphasis markers and the backslashes
# a markdown converter puts in front of ordinary punctuation are both stripped,
# since a citation preview is one line of prose and never styled.
_MD_EMPHASIS = re.compile(r"\*\*|__|(?<!\w)[*_](?!\w)|`")
_MD_ESCAPE = re.compile(r"\\([.\-+*_#\[\]()!>`~|])")


def clean_excerpt(text: str) -> str:
    """One line of prose from a scraped excerpt, with the markup taken out."""
    out = _MD_LINK.sub(r"\1", str(text or ""))
    # Escapes first. Stripping emphasis first turns `\*` into a bare backslash
    # with nothing left for the escape rule to match, and the stray slash then
    # survives into the hover card.
    out = _MD_ESCAPE.sub(r"\1", out)
    out = _MD_EMPHASIS.sub("", out)
    return " ".join(out.split())


def _is_prose(text: str) -> bool:
    """Whether an excerpt reads as a sentence rather than a scraped row."""
    if len(text) < 30:
        return False
    # More than two pipes is a table, whatever else it contains.
    if len(_PIPE_TABLE.findall(text)) > 2:
        return False
    words = [w for w in text.split() if len(w) > 2]
    if len(words) < 6:
        return False
    # Mostly digits and separators is a data row, not a claim about the world.
    letters = sum(c.isalpha() for c in text)
    return letters >= len(text) * 0.5


def normalize(basis: list[dict] | None) -> list[dict]:
    """Keep the fields that carry usable evidence, in a flat shape."""
    out = []
    for entry in basis or []:
        if not isinstance(entry, dict):
            continue
        citations = []
        for c in entry.get("citations") or []:
            url = (c.get("url") or "").strip()
            if not url:
                continue
            excerpts = []
            for e in c.get("excerpts") or []:
                cleaned = clean_excerpt(e)
                if cleaned and _is_prose(cleaned):
                    excerpts.append(cleaned)
            citations.append({"url": url, "excerpts": excerpts[:3]})
        reasoning = " ".join(str(entry.get("reasoning") or "").split())
        confidence = str(entry.get("confidence") or "").strip().lower()
        if not (citations or reasoning):
            continue
        out.append({
            "field": str(entry.get("field") or "").strip(),
            "citations": citations[:4],
            "reasoning": reasoning[:600],
            "confidence": confidence if confidence in _RANK else "",
        })
    return out


def overall_confidence(basis: list[dict]) -> str:
    """The weakest confidence across fields, which is what the set is worth.

    A row is only as trustworthy as its least certain field: high confidence
    on the firm name means nothing if the price is a guess.
    """
    levels = [b["confidence"] for b in basis if b.get("confidence") in _RANK]
    if not levels:
        return ""
    return min(levels, key=lambda c: _RANK[c])


def first_excerpt(basis: list[dict], field: str = "") -> dict | None:
    """One quotable citation: the sentence and where it came from.

    Prefers the named field, since that is what the reader is looking at.

    When a field's sources are all scraped tables, `normalize` drops the
    excerpts but keeps the reasoning, and that is still worth showing: "why the
    model believes this, and which page it read" beats an empty hover card.
    """
    ordered = sorted(basis, key=lambda b: b.get("field") != field) if field else basis
    fallback = None
    for entry in ordered:
        for c in entry.get("citations") or []:
            if c.get("excerpts"):
                return {"url": c["url"], "excerpt": c["excerpts"][0],
                        "confidence": entry.get("confidence", ""),
                        "reasoning": entry.get("reasoning", "")}
            if fallback is None and entry.get("reasoning"):
                fallback = {"url": c.get("url", ""), "excerpt": "",
                            "confidence": entry.get("confidence", ""),
                            "reasoning": entry["reasoning"]}
    return fallback


def dumps(basis: list[dict]) -> str:
    return json.dumps(basis, ensure_ascii=False)


def loads(raw) -> list[dict]:
    """Read stored evidence as a list, whatever shape it was written in.

    Two shapes are in circulation and both must survive a round trip: the full
    basis is a *list* of per-field entries, while a stored row keeps the single
    citation `first_excerpt` chose, which is a *dict*. Returning [] for the dict
    silently emptied every hover card on the page.
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw] if raw else []
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, dict):
        return [parsed] if parsed else []
    return parsed if isinstance(parsed, list) else []
