"""Narrative generation with Gemini.

Two hard rules encoded here, both learned from production failures:

1. Price levels come from the quote payload, never from the model's memory.
2. A truncated response is reported, not shipped silently. A cut response
   loses its tail, which is the part that matters most.
"""
from __future__ import annotations

from typing import Any

from ..adapters import gemini_enterprise as gem

MODEL = gem.MODEL
MAX_OUTPUT_TOKENS = 4096

SYSTEM_RULES = """You are a market research assistant for The Ticker Room.

You describe what happened. You never recommend an action.

Hard rules:
- Your memory of prices is out of date. Use ONLY the price figures given to you.
- Every support or resistance level you mention must fall inside the 3-month or
  52-week range provided. If no price data is given, give no levels at all.
- Never state a fact that is not in the supplied articles. No outside knowledge.
- Never write "buy", "sell", "should invest", or a price target.
- If there is no news, say plainly that there were no developments.

Write neutral, factual prose. Cite the source of each claim by its number."""


class TruncatedResponse(RuntimeError):
    """The model hit its output cap; the tail of the answer is missing."""


def _build_prompt(ticker: str, company: str, quote: dict | None, articles: list[dict]) -> str:
    parts = [f"Company: {company} ({ticker})\n"]

    if quote:
        parts.append(
            "REAL PRICE DATA (authoritative, use these numbers):\n"
            f"- Spot: ${quote['spot']} ({quote['change_pct']:+.2f}%)\n"
            f"- 3-month range: ${quote['low_3mo']} to ${quote['high_3mo']}\n"
            f"- MA20: ${quote['ma20']} | MA50: ${quote['ma50']}\n"
            f"- 52-week range: ${quote.get('low_52w')} to ${quote.get('high_52w')}\n"
            f"- Off 52-week high: {quote.get('pct_off_52w_high')}%\n"
        )
    else:
        parts.append("NO PRICE DATA AVAILABLE. Do not mention any price level.\n")

    if articles:
        parts.append("\nARTICLES:\n")
        for i, a in enumerate(articles, 1):
            excerpts = a.get("excerpts") or []
            body = " ".join(str(e) for e in excerpts)[:1200]
            parts.append(f"[{i}] {a.get('title', '')}\n    {a.get('url', '')}\n    {body}\n")
    else:
        parts.append("\nNO ARTICLES FOUND for this company in the requested window.\n")

    parts.append(
        "\nWrite a short briefing: what happened, why it matters, and where the "
        "price stands. Two or three paragraphs. If there is no news, say so."
    )
    return "".join(parts)


def summarize(ticker: str, company: str, quote: dict | None, articles: list[dict]) -> dict[str, Any]:
    payload = gem.generate(
        system_instruction=SYSTEM_RULES,
        prompt=_build_prompt(ticker, company, quote, articles),
        temperature=0.3,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    text, finish = gem.extract(payload)

    # The known mute failure: a cut answer used to ship as if it were complete.
    if finish == "MAX_TOKENS":
        raise TruncatedResponse(
            f"{ticker}: response hit the {MAX_OUTPUT_TOKENS}-token cap and lost its tail"
        )

    return {"text": text, "finish_reason": finish, "model": MODEL}
