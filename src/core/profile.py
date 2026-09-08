"""What a company actually is, along the axes a comparison can be drawn on.

Peer search used to ask one question: who competes with this company in its
main line of business. That is a single, very narrow axis, and it fails in a
way the reader never sees. Asked for peers of Ondas (US, defense, counter-UAS)
it drops a pure-defense name that does not build drones, and it drops a drone
manufacturer selling to agriculture, and it drops both for reasons that never
reach the screen. The answer looks like "there are no more comparables", which
is false.

So the company is profiled first, into axes that can be relaxed one at a time:

- **sector** ("defense"), the industry it sells into
- **product** ("counter-UAS systems"), what it actually builds
- **country**, which is recorded but is deliberately *never* an axis of its
  own. "Also American" is not a resemblance, and a facet built on it would
  return a directory of the US market rather than a set of comparables.

The profile comes from Parallel's Responses API rather than a stored field:
what a company does changes (Ondas was industrial networking before it was
counter-UAS), and a hardcoded sector table would quietly rot. It is cached per
ticker for the process lifetime because three facet searches ask for the same
profile at the same moment.
"""
from __future__ import annotations

import json
import re

from .parallel_api import NoCredit
from .responses import ask

# Asking for prose and parsing it back out is how a classifier becomes a
# guessing game. The model is asked for one JSON object and nothing else.
_PROMPT = """Profile the company {name} ({ticker}).

Answer with ONLY a JSON object, no prose and no markdown fence, with exactly
these keys:

{{"country": "country of headquarters, e.g. United States",
  "sector": "the broad industry it sells into, 1-3 words, lowercase, e.g. defense, biotechnology, semiconductors",
  "product": "the specific product or service category it builds, 1-4 words, lowercase, e.g. drones, counter-UAS systems, GLP-1 drugs",
  "what_it_does": "one short factual sentence"}}

`sector` and `product` must be different levels of description: `sector` is the
market, `product` is the thing sold into it. Do not repeat the company name in
either."""

# Responses answers with bare JSON in practice, but a fenced block is the
# classic failure mode of every model asked for JSON, and it costs three lines
# to survive it rather than losing the whole profile to a stray backtick.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")

_cache: dict[str, dict] = {}


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def of(ticker: str, company_name: str) -> dict:
    """The axes for one company. Returns {} when it could not be profiled.

    An empty profile is not an error the caller must handle: the peer search
    falls back to its single-axis behaviour, which is what it did before this
    module existed.
    """
    key = ticker.upper()
    if key in _cache:
        return _cache[key]

    try:
        answer = ask(_PROMPT.format(name=company_name, ticker=key), timeout=120)
    except NoCredit:
        # The one place NoCredit is swallowed rather than raised. Everywhere
        # else an empty account must be seen, because it turns a real answer
        # into a blank one. Here the profile is an enrichment with a documented
        # fallback: without it the peer search runs on its single axis, which
        # is what it did before this module existed. Letting 402 through was
        # taking down the whole peer search over an optional extra, and the
        # Responses product can be out of credit while Search and Task, which
        # do the actual finding, still work.
        print(f"[profile] {key}: no Responses credit, using the single axis")
        return {}

    text = _FENCE.sub("", answer.get("text") or "").strip()
    if not text:
        return {}

    # The model occasionally wraps the object in a sentence. The outermost
    # braces are the object either way.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        raw = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}

    out = {
        "ticker": key,
        "company_name": company_name,
        "country": _clean(raw.get("country"), 60),
        "sector": _clean(raw.get("sector"), 60).lower(),
        "product": _clean(raw.get("product"), 60).lower(),
        "what_it_does": _clean(raw.get("what_it_does"), 200),
    }
    # Without both axes there is nothing to relax, and the facet searches would
    # be three copies of the same query. The caller treats that as no profile.
    if not out["sector"] or not out["product"]:
        return {}

    _cache[key] = out
    return out
