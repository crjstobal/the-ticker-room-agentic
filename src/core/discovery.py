"""Finding tickers the user never thought to type, with Parallel's FindAll API.

Every other part of this product answers questions about a ticker you already
named. That is a ceiling: the app can only ever tell you about companies you
already knew to watch. FindAll removes it. Given a description of what you
care about, it generates candidate entities from the web, validates each one
against explicit conditions, and returns matches with the evidence behind them.

Two uses, and the difference matters:

- **Peers.** Given a ticker on the watchlist, find the companies it should be
  read against, so "up 12%" can be compared with how its comparables moved.
- **Themes.** Given a plain-language interest ("small caps winning defense
  drone contracts"), find companies that fit and are not on the watchlist yet.

Nothing here adds a ticker on its own. Discovery proposes, the user disposes:
an automatically expanding watchlist would be a research tool making portfolio
decisions for someone, which is exactly what this product refuses to do.
"""
from __future__ import annotations

import re
import time

from .parallel_api import NoCredit, ParallelError, get, request

INGEST_PATH = "/v1beta/findall/ingest"
RUNS_PATH = "/v1beta/findall/runs"

# FindAll is not billed like the rest of this product. Search and Task charge
# per call ($5 and $10 per thousand); FindAll charges a fixed price per query
# *plus* a price per match, so one click is a visible fraction of a prepaid
# balance rather than a rounding error:
#
#   generator   fixed    per match    8 matches    x3 facets
#   preview     $0.10      $0.00        $0.10        $0.30
#   base        $0.25      $0.03        $0.49        $1.47
#   core        $2.00      $0.15        $3.20        $9.72
#   pro        $10.00      $1.00       $18.00       $54.00
#
# A peer search is three runs, so `core` put a single click at roughly ten
# dollars and emptied a ten-dollar balance in one press. `base` is the same
# search six times cheaper, and the difference it makes is in how exotic the
# generated candidates are, not in whether the obvious comparables are found:
# a peer set a human is going to read and approve does not need the deep tier.
# `preview` is cheaper still but returns no per-match evidence, which is the
# part this page actually shows.
DEFAULT_GENERATOR = "base"
POLL_SECONDS = 10
# A `core` run over a wide objective validates candidates one at a time and
# regularly takes four to six minutes. Cutting it short is not a neutral
# timeout: the snapshot at three minutes routinely holds candidates that are
# generated but not yet judged, which read as "no matches found".
MAX_WAIT_SECONDS = 600

# The API rejects anything under 5 with a 422 that names the bound. Asking for
# a few more than will be shown costs nothing and leaves room for the ones
# dropped for having no US ticker.
MIN_MATCH_LIMIT = 5

# What every match must return alongside the decision. Without the ticker a
# result is a company name, not something this product can watch.
#
# Enrichment is a *separate call* against a started run, not a field in the
# create body: passing `enrichments` there is silently ignored, which looks
# exactly like the model declining to fill the fields in.
ENRICHMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {
            "type": "string",
            "description": "Stock ticker symbol on its primary US exchange, "
                           "uppercase, no exchange prefix. Empty if the company "
                           "is not publicly listed in the US.",
        },
        "exchange": {
            "type": "string",
            "description": "Exchange it trades on, e.g. NASDAQ or NYSE",
        },
        "what_it_does": {
            "type": "string",
            "description": "One short sentence on what the business actually does",
        },
    },
    "required": ["ticker", "exchange", "what_it_does"],
    "additionalProperties": False,
}

# `lite` keeps the per-match cost down: these three fields are on the company's
# own profile, not a research question.
ENRICHMENT_PROCESSOR = "lite"

_TICKER = re.compile(r"^[A-Z]{1,5}$")

# "Common stock listed on NASDAQ under ticker AVAV", and the parenthesised form
# "AeroVironment, Inc. (AVAV)".
_TICKER_IN_TEXT = re.compile(
    r"(?:ticker|symbol)[^A-Z]{0,12}([A-Z]{1,5})\b|\(([A-Z]{2,5})\)")


def _ticker_from_text(candidate: dict) -> str:
    """Recover a symbol from the prose of the match conditions."""
    for value in (candidate.get("output") or {}).values():
        if not isinstance(value, dict):
            continue
        m = _TICKER_IN_TEXT.search(str(value.get("value") or ""))
        if m:
            return (m.group(1) or m.group(2) or "").upper()
    return ""


def plan(objective: str) -> dict:
    """Turn a plain-language objective into the conditions FindAll will test.

    Exposed on its own because it is fast and cheap where a full run is neither:
    the user gets to see and correct what the agent understood before committing
    to a search that takes minutes.
    """
    payload = request(INGEST_PATH, {"objective": objective}, timeout=60)
    return {
        "objective": payload.get("objective", objective),
        "entity_type": payload.get("entity_type", "companies"),
        "match_conditions": payload.get("match_conditions") or [],
        "generator": payload.get("generator") or DEFAULT_GENERATOR,
    }


def peers_objective(ticker: str, company_name: str) -> str:
    return (
        f"Publicly traded companies on a US exchange that compete with "
        f"{company_name} ({ticker}) in its main line of business and would be "
        f"read alongside it when following the sector. Exclude {company_name} itself."
    )


def peers_conditions(ticker: str, company_name: str) -> list[dict]:
    """The conditions a peer must meet, written rather than inferred.

    `plan()` is used for open-ended themes, but for peers its generated
    conditions are too literal to be useful: asked for "comparable size" it
    produced a market-cap-within-50% screen that rejected AeroVironment as a
    peer of Ondas purely on size, while both build counter-UAS systems. A
    comparable a reader wants to see is one in the same business, not one in
    the same market-cap decile.
    """
    return [
        {"name": "us_listed_check",
         "description": "Company must have common stock listed and trading on a "
                        "US exchange (NASDAQ, NYSE or NYSE American) under its "
                        "own ticker symbol."},
        {"name": "same_business_check",
         "description": f"Company must compete with {company_name} ({ticker}) in "
                        f"its main line of business, selling products or services "
                        f"that address the same customers and use cases."},
        {"name": "not_the_company_itself_check",
         "description": f"Company must not be {company_name} ({ticker}), nor a "
                        f"subsidiary, parent or holding vehicle of it."},
    ]


# --- facets -------------------------------------------------------------
#
# One peer question has one answer and hides all the near-misses. Three
# questions, each relaxing a different axis of the profile, is what turns
# "no more comparables" into a map the reader can actually read:
#
#   exact   sector AND product, same country      the closest reads
#   product product only, any country, any use    the technology, elsewhere
#   sector  sector only, any country              the market, other products
#
# Country is a constraint on `exact` alone and is never a facet of its own:
# companies whose only resemblance is being American are not comparables, they
# are a stock exchange listing.
FACETS = ("exact", "product", "sector")

FACET_LABELS = {
    "exact": "Closest match",
    "product": "Same product, wider field",
    "sector": "Same sector, other products",
}


def facet_caption(facet: str, profile: dict) -> str:
    """The one line under a facet heading, in the profile's own words."""
    sector = profile.get("sector") or "the sector"
    product = profile.get("product") or "the product"
    country = profile.get("country") or "the same country"
    if facet == "exact":
        return f"{sector} \u00b7 {product} \u00b7 {country}"
    if facet == "product":
        return f"{product} \u00b7 any country, including outside {sector}"
    return f"{sector} \u00b7 any country, beyond {product}"


def facet_objective(facet: str, profile: dict) -> str:
    ticker = profile.get("ticker", "")
    name = profile.get("company_name", ticker)
    sector, product = profile.get("sector", ""), profile.get("product", "")
    country = profile.get("country", "")
    if facet == "exact":
        return (f"Publicly traded companies on a US exchange, headquartered in "
                f"{country}, that operate in the {sector} sector and build "
                f"{product}, in the way {name} ({ticker}) does. "
                f"Exclude {name} itself.")
    if facet == "product":
        return (f"Publicly traded companies on a US exchange that build "
                f"{product}, in any country and for any end market, including "
                f"customers outside {sector}. Exclude {name} ({ticker}).")
    return (f"Publicly traded companies on a US exchange that operate in the "
            f"{sector} sector, in any country, selling products other than "
            f"{product}. Exclude {name} ({ticker}).")


def facet_conditions(facet: str, profile: dict) -> list[dict]:
    """What each facet actually tests.

    Deliberately written rather than generated by `plan()`. Asked to infer
    conditions for a peer search, the planner produced a market-cap screen
    that rejected AeroVironment as a peer of Ondas on size alone, while both
    build counter-UAS systems.
    """
    ticker = profile.get("ticker", "")
    name = profile.get("company_name", ticker)
    sector, product = profile.get("sector", ""), profile.get("product", "")
    country = profile.get("country", "")

    listed = {"name": "us_listed_check",
              "description": "Company must have common stock listed and trading "
                             "on a US exchange (NASDAQ, NYSE or NYSE American) "
                             "under its own ticker symbol."}
    not_itself = {"name": "not_the_company_itself_check",
                  "description": f"Company must not be {name} ({ticker}), nor a "
                                 f"subsidiary, parent or holding vehicle of it."}

    if facet == "exact":
        return [listed,
                {"name": "sector_check",
                 "description": f"Company must operate in the {sector} sector."},
                {"name": "product_check",
                 "description": f"Company must design, manufacture or sell "
                                f"{product} as a material part of its business."},
                {"name": "country_check",
                 "description": f"Company must be headquartered in {country}."},
                not_itself]
    if facet == "product":
        return [listed,
                {"name": "product_check",
                 "description": f"Company must design, manufacture or sell "
                                f"{product} as a material part of its business. "
                                f"The end market does not matter: customers "
                                f"outside {sector} count."},
                not_itself]
    return [listed,
            {"name": "sector_check",
             "description": f"Company must operate in the {sector} sector, "
                            f"selling to that market as a material part of its "
                            f"business."},
            {"name": "different_product_check",
             "description": f"Company's main product must be something other "
                            f"than {product}."},
            not_itself]


def start_facet(facet: str, profile: dict, *, match_limit: int = 8,
                exclude: list[dict] | None = None) -> str:
    """Begin one facet of a peer search, returning its id."""
    return start(
        facet_objective(facet, profile),
        conditions=facet_conditions(facet, profile),
        entity_type="public_companies",
        match_limit=match_limit,
        exclude=exclude,
    )


def peers(ticker: str, company_name: str, *, exclude: set[str] | None = None,
          match_limit: int = 8) -> list[dict]:
    """Comparable companies for a ticker already on the watchlist. Blocking."""
    return find(
        peers_objective(ticker, company_name),
        conditions=peers_conditions(ticker, company_name),
        entity_type="public_companies",
        exclude=(exclude or set()) | {ticker.upper()},
        match_limit=match_limit,
    )


def start_peers(ticker: str, company_name: str, *,
                match_limit: int = 8, exclude: list[dict] | None = None) -> str:
    """Begin a peer search, returning its id."""
    return start(
        peers_objective(ticker, company_name),
        conditions=peers_conditions(ticker, company_name),
        entity_type="public_companies",
        match_limit=match_limit,
        exclude=exclude,
    )


def exclude_list(watchlist: list[dict]) -> list[dict]:
    """The watchlist in the shape FindAll's `exclude_list` expects.

    Both keys are required: a bare `{"name": ...}` is a 422 naming the missing
    `url`, which is easy to misread as a malformed body rather than a missing
    field. Nothing here has a company URL stored, so the entry is keyed to the
    company's SEC filing index, which is stable, real, and unambiguous for a
    listed company in a way a guessed homepage would not be.

    The name is the company name rather than the ticker: a run looking for
    drone manufacturers surfaces "Ondas Holdings", not "ONDS".
    """
    out = []
    for row in watchlist or []:
        name = (row.get("company_name") or "").strip()
        ticker = (row.get("ticker") or "").strip().upper()
        if not name:
            continue
        out.append({
            "name": name,
            "url": (row.get("url") or "").strip() or
                   f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                   f"&ticker={ticker}&type=10-K",
        })
    return out


def start(
    objective: str,
    *,
    match_limit: int = 10,
    generator: str = DEFAULT_GENERATOR,
    conditions: list[dict] | None = None,
    entity_type: str = "",
    exclude: list[dict] | None = None,
) -> str:
    """Begin a discovery and return its id, without waiting for it to finish.

    Starting and collecting are separate because a run takes minutes: a page
    that blocked on one would hold an HTTP request open long past any sensible
    timeout. The page starts a run, then polls for the result.
    """
    spec = ({"match_conditions": conditions, "entity_type": entity_type or "companies"}
            if conditions else plan(objective))
    body = {
        "objective": objective,
        "entity_type": spec.get("entity_type") or "companies",
        "match_conditions": spec.get("match_conditions") or [],
        "generator": generator,
        "match_limit": max(match_limit, MIN_MATCH_LIMIT),
    }
    # Names already on the watchlist are excluded by the API rather than
    # filtered out of the result afterwards. `match_limit` caps how many
    # candidates get evaluated, and every condition on a candidate we were
    # always going to discard is budget spent to learn nothing: a watchlist of
    # eight could previously consume most of a ten-candidate run before the
    # first genuinely new company was reached.
    if exclude:
        body["exclude_list"] = exclude
    run = request(RUNS_PATH, body, timeout=60)
    findall_id = run.get("findall_id")
    if not findall_id:
        raise ParallelError(f"no findall_id in response: {str(run)[:200]}")

    # Ask for the ticker and a one-liner on every match. Requested after the run
    # exists, and not fatal: a suggestion with no ticker is still dropped later,
    # but the run itself is worth keeping.
    try:
        request(f"{RUNS_PATH}/{findall_id}/enrich", {
            "processor": ENRICHMENT_PROCESSOR,
            "output_schema": {"type": "json", "json_schema": ENRICHMENT_SCHEMA},
        }, timeout=60)
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[discovery] enrichment not attached: {exc}")

    return findall_id


def progress(findall_id: str) -> dict:
    """How far along a run is, for a page that is waiting on it."""
    try:
        state = get(f"{RUNS_PATH}/{findall_id}", timeout=30).get("status") or {}
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        # The status travels with the message: the page turns 402 into a
        # sentence about credit, and str(exc) alone would lose that.
        return {"running": False, "error": str(exc), "status": exc.status,
                "generated": 0, "matched": 0}
    metrics = state.get("metrics") or {}
    return {
        "running": bool(state.get("is_active", False)),
        "status": str(state.get("status") or ""),
        "generated": metrics.get("generated_candidates_count", 0),
        "matched": metrics.get("matched_candidates_count", 0),
        "error": "",
    }


def collect(findall_id: str, *, exclude: set[str] | None = None) -> list[dict]:
    """The confirmed matches of a run, whether or not it has finished."""
    try:
        result = get(f"{RUNS_PATH}/{findall_id}/result", timeout=60)
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[discovery] no result: {exc}")
        return []
    return _clean(result.get("candidates") or [], exclude or set())


def find(
    objective: str,
    *,
    match_limit: int = 10,
    generator: str = DEFAULT_GENERATOR,
    exclude: set[str] | None = None,
    conditions: list[dict] | None = None,
    entity_type: str = "",
) -> list[dict]:
    """Run a discovery to completion. Returns [] rather than raising.

    Blocking, so it belongs in a script or a background task rather than in a
    request handler. The web pages use start/progress/collect instead.

    `exclude` is a set of tickers already on the watchlist: proposing something
    the user is already watching wastes the one thing this feature has to earn,
    which is the reader's attention on an unfamiliar name.
    """
    try:
        findall_id = start(objective, match_limit=match_limit, generator=generator,
                           conditions=conditions, entity_type=entity_type)
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[discovery] could not start: {exc}")
        return []

    # The run's state arrives nested: {"status": {"status": ..., "is_active": ...}}.
    # `is_active` is the reliable terminator; the string alone has no single
    # "done" value across generators.
    waited = 0
    while waited < MAX_WAIT_SECONDS:
        try:
            state = get(f"{RUNS_PATH}/{findall_id}", timeout=30).get("status") or {}
        except NoCredit:
            raise  # an empty account is not an empty result
        except ParallelError as exc:
            print(f"[discovery] poll failed: {exc}")
            break
        if not state.get("is_active", True):
            break
        if str(state.get("status") or "").lower() in ("failed", "cancelled", "error"):
            print(f"[discovery] run {state.get('status')}")
            return []
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS

    # A snapshot from a run that is still going is genuinely partial: candidates
    # sit at `generated` until each has been checked against every condition, so
    # reading early reports "nothing matched" for a search that had simply not
    # finished. It is still read rather than discarded, but the caller is told.
    if waited >= MAX_WAIT_SECONDS:
        print(f"[discovery] still running after {MAX_WAIT_SECONDS}s, "
              f"reading a partial result")
    return collect(findall_id, exclude=exclude)


def _field(candidate: dict, name: str) -> str:
    """Read one enrichment value, whatever shape the API wrapped it in."""
    output = candidate.get("output") or {}
    value = output.get(name, candidate.get(name, ""))
    if isinstance(value, dict):
        value = value.get("value") or value.get("content") or ""
    return " ".join(str(value or "").split())


def _clean(candidates: list[dict], exclude: set[str]) -> list[dict]:
    """Keep confirmed matches that carry a usable US ticker."""
    out: dict[str, dict] = {}
    for c in candidates:
        # FindAll returns every candidate it generated, including ones it has
        # not validated yet ("generated") and ones it rejected. Only confirmed
        # matches are shown: presenting the rest as suggestions would
        # misrepresent what the agent actually decided.
        status = str(c.get("match_status") or c.get("status") or "").lower()
        if status not in ("matched", "match", "confirmed", "true"):
            continue

        ticker = _field(c, "ticker").upper().split(":")[-1].strip()
        if not _TICKER.match(ticker):
            # Enrichment can lag the match decision, but the listing condition
            # states the symbol in prose ("listed on NASDAQ under ticker AVAV"),
            # so a match is not thrown away just for arriving early.
            ticker = _ticker_from_text(c)
        if not _TICKER.match(ticker) or ticker in exclude or ticker in out:
            continue

        name = (c.get("name") or c.get("entity") or _field(c, "name")).strip()
        if not name:
            continue

        # The description is the fallback when enrichment did not return a
        # one-liner of its own.
        blurb = _field(c, "what_it_does") or " ".join(
            str(c.get("description") or "").split())

        reason, source, confidence = "", "", ""
        for b in c.get("basis") or []:
            reason = reason or " ".join(str(b.get("reasoning") or "").split())
            confidence = confidence or str(b.get("confidence") or "").lower()
            for cit in b.get("citations") or []:
                source = source or (cit.get("url") or "")

        out[ticker] = {
            "ticker": ticker,
            "company_name": name,
            "exchange": _field(c, "exchange"),
            "what_it_does": blurb[:200],
            "reason": reason[:300],
            "confidence": confidence,
            "source_url": source,
        }
    return list(out.values())
