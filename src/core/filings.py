"""SEC filings: insider trades, dilution and material events.

The hardest information the product carries. A Form 4 saying the COO sold $6.3M
of stock is a filed document with a date, not an interpretation of chatter, and
that is exactly what deserves an alert.

Extracted with Parallel's Task API against a schema, so the results are rows
rather than pages, and carrying Parallel's basis, so each row can show the
sentence it was read from. This module once badged a sale as a purchase; the
evidence is what lets a reader catch that rather than trust it.
"""
from __future__ import annotations

import re

from . import evidence
from .parallel_api import NoCredit, ParallelError, run_task

# Forms worth surfacing, and what each one means to a reader.
FORM_MEANING = {
    "4": "insider bought or sold",
    "3": "new insider registered",
    "5": "late insider transaction",
    "8-K": "material event",
    "S-3": "shelf registration, allows future share sales",
    "424B5": "share offering priced",
    "S-1": "registration of new shares",
    "13D": "activist stake",
    "13G": "passive stake above 5%",
    "10-Q": "quarterly report",
    "10-K": "annual report",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "filings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "form_type": {"type": "string", "description": "Form 4, 8-K, S-3, 424B5 etc"},
                    "filed_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "insider_name": {"type": "string", "description": "Person filing, for Form 4"},
                    "insider_role": {"type": "string", "description": "CEO, COO, Director etc"},
                    "transaction": {"type": "string", "description": "buy, sell, grant, or n/a"},
                    "shares": {"type": "number"},
                    "value_usd": {"type": "number"},
                    "headline": {"type": "string", "description": "One line on what the filing says"},
                    "source_url": {"type": "string"},
                },
                "required": ["form_type", "headline"],
            },
        }
    },
    "required": ["filings"],
}


def fetch_filings(ticker: str, company_name: str, *, days: int = 90) -> list[dict]:
    """Recent SEC filings for a ticker. Returns [] rather than raising."""
    try:
        content, basis = run_task(
            f"SEC filings for {company_name} ({ticker}) from the last {days} days: "
            f"Form 4 insider buys and sells with the person's name and role, share "
            f"offerings or dilution (S-3, 424B5), and material 8-K events. Include "
            f"filed date, share counts and dollar value where stated.",
            SCHEMA,
            max_wait=360,
        )
    except NoCredit:
        raise  # an empty account is not an empty result
    except ParallelError as exc:
        print(f"[filings] {ticker}: {exc}")
        return []

    rows = _clean(content.get("filings") or [], ticker)
    facts = evidence.normalize(basis)
    if facts:
        confidence = evidence.overall_confidence(facts)
        # The transaction direction is the field this module has actually got
        # wrong before, so that is the citation worth surfacing.
        cite = evidence.first_excerpt(facts, "transaction")
        for row in rows:
            row["confidence"] = confidence
            row["evidence"] = cite
    return rows


# SEC filers write a name however the form was typed: "Huffman Steve Ladd",
# "Steve Ladd Huffman" and "Steven Ladd Huffman" are one person, and the
# extractor faithfully reproduces all three. Keyed on the raw string they
# became three rows on the page, which reads as three separate trades.
_NAME_NOISE = re.compile(r"[.,]|\b(jr|sr|ii|iii|iv|mr|mrs|ms|dr)\b", re.IGNORECASE)

# Diminutives seen on real Form 4 filings for the current watchlist. Kept
# deliberately small: a general nickname table would start merging people who
# are genuinely different, which is a worse error than showing a duplicate.
_DIMINUTIVES = {
    "steve": "steven", "steven": "steven",
    "mike": "michael", "bill": "william", "bob": "robert",
    "dave": "david", "jim": "james", "tom": "thomas",
    "chris": "christopher", "dan": "daniel", "matt": "matthew",
    "rob": "robert", "rick": "richard", "dick": "richard",
    "pat": "patricia", "patty": "patricia", "kate": "katherine",
    "beth": "elizabeth", "liz": "elizabeth", "sarah": "sara",
}


def name_key(name: str) -> str:
    """A stable identity for one filer, order- and nickname-insensitive.

    The tokens are sorted, so "Huffman Steve" and "Steve Huffman" agree without
    having to guess which half is the surname. Initials are dropped: "David C.
    Habiger" and "David Habiger" are the same director, and a middle initial
    that appears on one filing and not the next would otherwise split them.
    """
    cleaned = _NAME_NOISE.sub(" ", (name or "").lower())
    # A hyphen inside a surname is a spelling choice, not a word boundary:
    # RDDT's filings carry both "Fili-Krushel" and "Filikrushel" for the same
    # director, and splitting on the hyphen made them two different people.
    # Removed rather than replaced with a space, so the two spellings converge.
    cleaned = cleaned.replace("-", "").replace("'", "")
    tokens = [t for t in re.split(r"[^a-z]+", cleaned) if len(t) > 1]
    return " ".join(sorted(_DIMINUTIVES.get(t, t) for t in tokens))


def display_name(name: str) -> str:
    """Title-case a filer name, leaving an already-mixed-case name alone.

    Filings arrive shouting ("FILIKRUSHEL PATRICIA") or in file-under order.
    Only the all-caps case is touched: recasing a normal name would turn
    "David C. Habiger" into "David C. Habiger" at best and mangle it at worst.
    """
    n = (name or "").strip()
    if n and n == n.upper():
        return " ".join(w.capitalize() for w in n.split())
    return n


# Same guard as targets: a model that cannot find a filing date writes "Not
# stated" rather than leaving the field blank, and that string sorts above
# every real date.
_NON_DATE = re.compile(
    r"^(n/?a|none|not\s|unknown|unspecified|undated|no\s)", re.IGNORECASE)


def _date(value) -> str:
    """An ISO date, or empty."""
    text = str(value or "").strip()
    if not text or _NON_DATE.match(text):
        return ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return m.group(0) if m else ""


def _normalize_form(form: str) -> str:
    f = (form or "").strip().upper().replace("FORM", "").strip()
    return f or "?"


def _clean(filings: list[dict], ticker: str) -> list[dict]:
    out: dict[tuple, dict] = {}
    for f in filings:
        form = _normalize_form(f.get("form_type", ""))
        headline = (f.get("headline") or "").strip()
        if not headline or is_negative_finding(headline):
            continue
        date = _date(f.get("filed_date"))
        row = {
            "ticker": ticker.upper(),
            "form_type": form,
            "form_meaning": FORM_MEANING.get(form, ""),
            "filed_date": date,
            "insider_name": display_name(f.get("insider_name") or ""),
            "insider_role": (f.get("insider_role") or "").strip(),
            "transaction": (f.get("transaction") or "").strip().lower(),
            "shares": _num(f.get("shares")),
            "value_usd": _num(f.get("value_usd")),
            "headline": headline,
            "source_url": (f.get("source_url") or "").strip(),
        }
        # A headline describing a different person than the row's filer is a
        # crossed wire, not a filing. Blanking the headline rather than the row
        # keeps the trade, which is the part that is true.
        if headline_names_other(headline, row["insider_name"]):
            row["headline"] = generic_headline(row)

        # Same person, same form, same day is the same filing, whatever order
        # the filer's name was typed in.
        key = (form, date, name_key(row["insider_name"]))
        prior = out.get(key)
        if prior is None:
            out[key] = row
        else:
            _merge(prior, row)
    return sorted(out.values(), key=lambda r: r["filed_date"], reverse=True)


def headline_names_other(headline: str, insider_name: str) -> bool:
    """True if the headline names a person who is not this row's filer.

    The extractor sometimes attaches a sentence about one director to another
    director's row. Both were on the same page, both are named in it, and the
    schema has one slot per row, so the pairing is a coin flip.

    Only surnames are compared, and only when the headline names exactly one
    of them: "Seven Reddit directors received..." names nobody and is left
    alone, and a headline listing several people is not a mismatch either.
    """
    if not headline or not insider_name:
        return False
    own = set(name_key(insider_name).split())
    if not own:
        return False
    # Capitalised words in the headline that could be a person's name.
    candidates = re.findall(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)?\b", headline)
    named = {name_key(c) for c in candidates} - {""}
    # A surname shared with the filer means the headline is about them.
    if named & own:
        return False
    # Only treat it as a mismatch when the headline clearly names a person:
    # a first name followed by a surname, neither belonging to this filer.
    pairs = re.findall(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b", headline)
    for first, last in pairs:
        if name_key(last) not in own and name_key(first) not in own:
            # "Reddit Inc" and "Form 4" are capitalised pairs too; require the
            # surname to be absent from the known non-name vocabulary.
            if last.lower() not in _NOT_NAMES and first.lower() not in _NOT_NAMES:
                return True
    return False


# Capitalised words that appear in filing headlines and are not people.
_NOT_NAMES = {
    "form", "reddit", "ondas", "holdings", "inc", "corp", "corporation",
    "company", "class", "common", "stock", "shares", "restricted", "unit",
    "units", "director", "directors", "officer", "chief", "executive",
    "board", "the", "securities", "exchange", "commission", "sec", "series",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}


def generic_headline(row: dict) -> str:
    """A truthful one-liner built only from this row's own fields.

    Used when the extracted headline turned out to describe somebody else.
    Says less than the original, and everything it says is this row's.
    """
    who = row.get("insider_name") or "An insider"
    role = f" ({row['insider_role']})" if row.get("insider_role") else ""
    action = {"buy": "bought", "sell": "sold", "grant": "was granted"}.get(
        row.get("transaction", ""), "reported a transaction in")
    shares = row.get("shares")
    amount = f" {shares:,.0f} shares".replace(",", ",") if shares else " shares"
    return f"{who}{role} {action}{amount}."


def _merge(prior: dict, row: dict) -> None:
    """Fold a duplicate filing into the one already kept.

    The duplicates are not identical: one copy often carries the share count
    and another the dollar value, and their headlines differ in wording. The
    richer field wins, so merging recovers data instead of discarding it.

    The headline is the exception. It is prose describing a specific person,
    and RDDT showed why swapping it matters: a row whose headline named
    Patricia Fili-Krushel sat beside an insider_name of FARRELL SARAH E,
    because a generic "seven directors received..." sentence had overwritten a
    specific one. The first headline is kept, and a headline naming somebody
    other than this row's filer is rejected outright by `_clean`.
    """
    for field in ("shares", "value_usd"):
        if prior.get(field) is None and row.get(field) is not None:
            prior[field] = row[field]
    for field in ("insider_role", "transaction", "source_url", "filed_date"):
        if not prior.get(field) and row.get(field):
            prior[field] = row[field]
    # Prefer the name that looks like a real rendering over a shouted one.
    if prior.get("insider_name", "").isupper() and not row.get("insider_name", "").isupper():
        prior["insider_name"] = row["insider_name"]


def _num(v) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


# Words that decide what a Form 4 actually did. The `transaction` field is
# often "n/a" even when the headline plainly says "sold", so the headline is
# the fallback: mislabelling a sale as a purchase is the worst error this
# module can make.
_SOLD = re.compile(r"\b(sold|sale|disposed|disposition)\b", re.IGNORECASE)
_BOUGHT = re.compile(r"\b(bought|purchased|acquired)\b", re.IGNORECASE)
_GRANT = re.compile(r"\b(grant|granted|award|awarded|vest|vesting|rsu)\b", re.IGNORECASE)

# The model answers the question it was asked, and when a company filed nothing
# of a kind it reports that as a finding: "No S-3 or 424B5 share-offering filing
# was identified in the reviewed Reddit SEC filings". That is a true statement
# and a useful one, but it is not a filing, and listing it in a table of filings
# with a form type and a date asserts a document exists that does not.
# The absence has to be the subject of the sentence, not a detail inside it.
# An earlier version matched "no ... offering" anywhere and deleted a real ONDS
# 424B7 whose headline ended "no offering dollar value was stated" — a fact
# about a filing that exists. So the pattern is anchored to the start, where a
# report of an absence puts it: "No S-3 or 424B5 filing was identified...".
_NEGATIVE = re.compile(
    r"^\s*(?:"
    r"(?:no|none)\b(?![^.]*\b(?:value|price|dollar|amount|consideration)\b)"
    r"|there (?:were|was|are|is) no\b"
    r"|not any\b"
    r"|[^.]{0,80}\b(?:filing list|filings list|filing index|SEC filings)\b"
    r"[^.]{0,60}\b(?:contains?|shows?|lists?|includes?) no\b"
    r")",
    re.IGNORECASE)

# A second signal, allowed anywhere: the extractor stating it looked and found
# nothing. This is phrasing no real filing headline uses.
_NOT_FOUND = re.compile(
    r"\b(?:was|were) not (?:found|identified|disclosed|reported)\b"
    r"|\bno (?:such|relevant|applicable) (?:filing|filings|form|forms)\b",
    re.IGNORECASE)


def is_negative_finding(headline: str) -> bool:
    """Whether a row says a filing does NOT exist rather than describing one."""
    text = (headline or "").strip()
    return bool(_NEGATIVE.search(text) or _NOT_FOUND.search(text))


def classify(f: dict) -> str:
    """What this filing is, as one of the kinds the UI knows how to show.

    Returns "" for filings that are routine and should carry no badge.
    """
    form = (f.get("form_type") or "").upper()
    tx = (f.get("transaction") or "").strip().lower()
    text = f"{f.get('headline', '')} {f.get('transaction', '')}"

    if form in ("S-3", "424B5", "S-1"):
        return "dilution"
    if form == "13D":
        return "activist"
    if form != "4":
        return ""

    # An option exercise followed by a sale is a sale; grants alone are not.
    if tx in ("sell", "sale") or _SOLD.search(text):
        return "insider-sell"
    if tx in ("buy", "purchase") or (_BOUGHT.search(text) and not _GRANT.search(text)):
        return "insider-buy"
    if tx == "grant" or _GRANT.search(text):
        return "grant"
    return ""


def notable(filings: list[dict], *, min_value: float = 0) -> list[dict]:
    """The filings worth waking someone for.

    An insider sale or purchase, dilution, or an activist stake: all discrete,
    dated facts rather than drifting trends. Routine grants and vesting are
    excluded — they are compensation, not a decision about the company.
    """
    events = []
    for f in filings:
        kind = classify(f)
        if kind in ("insider-sell", "insider-buy", "dilution", "activist"):
            if kind == "insider-sell" and min_value:
                if (f.get("value_usd") or 0) < min_value:
                    continue
            events.append({**f, "kind": kind})
    return events
