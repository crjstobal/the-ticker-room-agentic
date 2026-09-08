"""A second opinion on a question, from Parallel's Responses API.

The Ask page runs a real agent loop on Gemini: it picks tools and answers from
what this service has already stored. That is the product's own view, and it is
only ever as good as the last research pass.

This is the other half of the same question. Responses goes to the live web and
answers from what is published right now, with its own citations. Neither is
authoritative and they are shown side by side on purpose: where the two agree,
the reader has two independent paths to the same fact; where they differ, the
difference is itself the finding, and usually means the stored history has
fallen behind.

Auth is not the same as the rest of the API. Responses is OpenAI-compatible and
wants `Authorization: Bearer`; the `x-api-key` header every other endpoint uses
answers "No API key provided" here, which reads like a bad key and is not one.
The model name is always the literal string "parallel".
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .parallel_api import BASE_URL, NoCredit, ParallelError
from .secrets import get_key

PATH = "/v1/responses"

# The endpoint returns a spurious 401 every few calls under load. It is not the
# key: the identical request succeeds on the next attempt. Measured 2026-09-07,
# roughly one call in three.
MAX_ATTEMPTS = 3


def _post(body: dict[str, Any], timeout: int) -> dict:
    last: ParallelError | None = None
    for _ in range(MAX_ATTEMPTS):
        req = urllib.request.Request(
            f"{BASE_URL}{PATH}",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {get_key('parallel.env', 'PARALLEL_API_KEY')}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode(errors="replace")[:300]
            except Exception:  # noqa: BLE001 - body is best-effort context
                detail = "<error body unavailable>"
            if exc.code == 402:
                raise NoCredit(f"POST {PATH} -> 402: {detail}", status=402) from exc
            last = ParallelError(f"POST {PATH} -> {exc.code}: {detail}", status=exc.code)
            if exc.code not in (401, 429, 500, 502, 503, 504):
                raise last from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = ParallelError(f"POST {PATH} failed: {exc}")
    assert last is not None
    raise last


def ask(question: str, *, timeout: int = 120) -> dict[str, Any]:
    """Answer a question from the live web. Returns {} rather than raising.

    An empty dict means the second opinion is simply unavailable, and the Ask
    page renders without it. The primary answer must never depend on this.
    """
    try:
        payload = _post({"model": "parallel", "input": question}, timeout)
    except NoCredit:
        raise
    except ParallelError as exc:
        print(f"[responses] {exc}")
        return {}

    text, sources = "", []
    seen: set[str] = set()
    for item in payload.get("output") or []:
        for chunk in item.get("content") or []:
            text += chunk.get("text") or ""
            for note in chunk.get("annotations") or []:
                url = note.get("url") or ""
                # Citations repeat heavily: the same forecast page is annotated
                # once per sentence it supports, which would render as a wall
                # of identical links.
                if url and url not in seen:
                    seen.add(url)
                    sources.append({"url": url, "title": note.get("title") or ""})

    if not text.strip():
        return {}
    return {"text": text.strip(), "sources": sources,
            "tokens": (payload.get("usage") or {}).get("total_tokens")}
