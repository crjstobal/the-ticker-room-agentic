"""The analyst agent, built on Gemini Enterprise Agent Platform.

This is a genuine agent loop, not a fixed script: the model is given five tools
over the stored history and the live web, and it chooses which to call and in
what order for the question it was asked. The scheduled research pipeline stays
deterministic on purpose, because a nightly briefing should always do the same
four things; open-ended questions are where choosing actually helps.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import vertexai
from vertexai.generative_models import (
    Content, FunctionDeclaration, GenerationConfig, GenerativeModel, Part, Tool,
)

from ..core.parallel_api import NoCredit
from ..core.tools import REGISTRY

PROJECT = "ticker-room"
LOCATION = "global"
MODEL = "gemini-3.6-flash"
MAX_TURNS = 6

# The date is injected rather than left to the model. Without it there is no
# reference point against which a stored reading can be judged old, and the
# model has no reliable sense of the current date on its own.
SYSTEM = """You are the analyst in The Ticker Room.

Today's date is {today}.

You answer questions about companies on the user's watchlist using the tools
provided. Rules you must follow:

- Use tools to get facts. Never state a price, a date or a headline you did not
  get from a tool.
- Every tool result carries `as_of`, `age` and `is_stale`, describing when that
  reading was captured. Treat them as part of the fact, not as metadata.
- Never present a stale reading as the present. If `is_stale` is true, either
  call search_web to confirm it against the live web, or say plainly how old the
  figure is: "as of 25 August" and not "currently".
- Words like "currently", "now", "today" and "latest" are only for readings
  whose `is_stale` is false.
- For anything asking what is happening now or lately, call search_web as well
  as the stored tools. Stored history can be days old; the question is not.
- You describe what happened. You never recommend buying or selling, never give
  a price target, and never phrase anything as a trading signal.
- If the tools do not answer the question, say so plainly.
- Cite the ticker and the source of each fact by name: the publication, or
  "stored history". Never name the tool or function you called; `get_price` and
  `search_web` are plumbing and mean nothing to the reader.
- Keep answers to a few short paragraphs. Head each one with a short section
  title on its own line, written as `## Title` and no more than five words:
  "## Recent earnings", "## What Reddit is saying". These become headings on
  the page, so write them as titles rather than sentences.
- Never use backticks."""

_DECLARATIONS = [
    FunctionDeclaration(
        name="get_price",
        description="Current price and technical context (spot, moving averages, 52-week range).",
        parameters={"type": "object", "properties": {
            "ticker": {"type": "string", "description": "Ticker symbol, e.g. ONDS"}},
            "required": ["ticker"]},
    ),
    FunctionDeclaration(
        name="get_coverage_history",
        description="Articles found per day over the last 60 days, with the average and busiest day. Use for attention or spike questions.",
        parameters={"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]},
    ),
    FunctionDeclaration(
        name="get_stored_articles",
        description="Headlines already collected for a ticker, newest first.",
        parameters={"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]},
    ),
    FunctionDeclaration(
        name="get_sentiment",
        description="Most recent Reddit sentiment reading: score, label, themes and which subreddits it came from.",
        parameters={"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]},
    ),
    FunctionDeclaration(
        name="search_web",
        description="Search the live web for current news. Call this whenever the question is about what is happening now or recently, and whenever a stored reading came back with is_stale true.",
        parameters={"type": "object", "properties": {
            "ticker": {"type": "string"},
            "company_name": {"type": "string", "description": "Full company name if known"}},
            "required": ["ticker"]},
    ),
]


def _model() -> GenerativeModel:
    vertexai.init(project=PROJECT, location=LOCATION)
    today = datetime.now(timezone.utc).strftime("%d %B %Y")
    return GenerativeModel(
        MODEL,
        system_instruction=SYSTEM.format(today=today),
        tools=[Tool(function_declarations=_DECLARATIONS)],
        generation_config=GenerationConfig(temperature=0.2, max_output_tokens=2048),
    )


def ask(question: str) -> dict[str, Any]:
    """Run the agent loop until it produces an answer.

    Returns the answer plus the trace of tool calls, so the reasoning is
    auditable rather than a black box.
    """
    chat = _model().start_chat()
    trace: list[dict] = []
    response = chat.send_message(question)

    for _ in range(MAX_TURNS):
        calls = [p.function_call for c in response.candidates
                 for p in c.content.parts if p.function_call and p.function_call.name]
        if not calls:
            break

        replies = []
        for call in calls:
            fn = REGISTRY.get(call.name)
            args = dict(call.args) if call.args else {}
            if fn is None:
                result = {"error": f"Unknown tool {call.name}"}
            else:
                try:
                    result = fn(**args)
                except NoCredit:
                    # The one exception to catching everything here. An empty
                    # account makes every lookup fail, and handing that to the
                    # model as a tool result lets it narrate around the gap and
                    # answer from memory: the reader gets a confident answer
                    # built on nothing. It has to stop the turn and be seen.
                    raise
                except Exception as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}
            trace.append({"tool": call.name, "args": args,
                          "result_preview": json.dumps(result, default=str)[:300]})
            replies.append(Part.from_function_response(
                name=call.name, response={"content": result}))

        response = chat.send_message(Content(role="user", parts=replies))

    text = ""
    for c in response.candidates:
        for p in c.content.parts:
            if getattr(p, "text", ""):
                text += p.text

    return {"answer": text.strip(), "trace": trace, "model": MODEL}
