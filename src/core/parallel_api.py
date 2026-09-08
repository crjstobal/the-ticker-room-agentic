"""One HTTP client for every Parallel API the product uses.

Search, Task, Monitor, FindAll and Extract all live on the same host behind
the same key, and previously each module carried its own `_post`, `_get` and
polling loop. That duplication is why the news search shipped without
`max_results` for weeks while Reddit and X had it: a fix applied in one copy
did not reach the others.

Nothing here knows about tickers. Callers own the schemas and the meaning.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .secrets import get_key

BASE_URL = "https://api.parallel.ai"
DEFAULT_TIMEOUT = 90

# A run researches up to six tickers at once, each making several calls, so a
# burst of 429s is the expected case rather than the edge case. Every caller
# turns a ParallelError into an empty result, which reaches the page as "this
# company has no analyst coverage and no filings" — indistinguishable from the
# truth. One retry ladder here is worth more than error handling in any caller.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
BACKOFF_BASE = 1.5      # seconds: 1.5, 3, 6 between the four attempts
BACKOFF_CAP = 20.0
RETRY_AFTER_CAP = 30.0  # honour the server, but never block a run for minutes


class ParallelError(RuntimeError):
    """An API call that failed in a way the caller may want to report.

    `status` is the HTTP code when there was one, so a caller can tell a
    genuine empty answer from a lookup that never completed.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class NoCredit(ParallelError):
    """The account is out of credit: HTTP 402.

    A subclass rather than a plain ParallelError because callers deliberately
    swallow errors and return [] — a failing secondary source must not abort a
    run. That is right for a timeout and wrong for this: with no credit every
    lookup fails, so the run "succeeds" while reporting nothing, and the page
    shows a quiet week that never happened. This one is meant to escape.

    Measured: the account was empty from 2026-08-23 to 2026-09-04 and the app
    said nothing for twelve days.
    """


# The beta search and extract endpoints are gated behind a header naming the
# beta. Without it `/v1beta/search` answers, but as the older shape: the
# `excerpts` block is ignored and results come back with the short excerpts,
# which is the whole reason for using it.
BETA = "search-extract-2025-10-10"


def _headers() -> dict[str, str]:
    return {
        "x-api-key": get_key("parallel.env", "PARALLEL_API_KEY"),
        "Content-Type": "application/json",
        "parallel-beta": BETA,
    }


def request(
    path: str,
    body: dict[str, Any] | None = None,
    *,
    method: str = "POST",
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """One call. Raises ParallelError with the server's own message attached.

    A bare 422 naming no field has cost real debugging time here before (an
    `exclude_domains` entry carrying a path), so the response body is kept.
    """
    payload = json.dumps(body).encode() if body is not None else None
    last: ParallelError | None = None

    for attempt in range(MAX_ATTEMPTS):
        # Rebuilt per attempt: the key is read fresh, and a Request object is
        # not safe to resend once urlopen has consumed it.
        req = urllib.request.Request(
            f"{BASE_URL}{path}", data=payload, headers=_headers(), method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            # Reading the error body can itself fail if the peer drops the
            # connection, and that must not escape as a raw socket error: the
            # status code is the part worth keeping.
            try:
                detail = exc.read().decode(errors="replace")[:400]
            except Exception:  # noqa: BLE001 - body is best-effort context
                detail = "<error body unavailable>"
            cls = NoCredit if exc.code == 402 else ParallelError
            last = cls(f"{method} {path} -> {exc.code}: {detail}", status=exc.code)
            if exc.code not in RETRY_STATUS:
                raise last from exc      # 4xx: retrying sends the same bad request
            delay = _retry_after(exc) or min(BACKOFF_BASE * 2 ** attempt, BACKOFF_CAP)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            # A refused connection or a read timeout is usually transient.
            last = ParallelError(f"{method} {path} failed: {exc}")
            delay = min(BACKOFF_BASE * 2 ** attempt, BACKOFF_CAP)

        if attempt == MAX_ATTEMPTS - 1:
            break
        print(f"[parallel] {method} {path}: {last}; retrying in {delay:.1f}s")
        time.sleep(delay)

    assert last is not None
    raise last


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """The server's own Retry-After, in seconds, when it sent a usable one.

    Only the delta-seconds form is honoured. The HTTP-date form is rare here
    and parsing it wrong would sleep for hours, so it falls back to backoff.
    """
    raw = (exc.headers.get("Retry-After") or "").strip() if exc.headers else ""
    if not raw:
        return None
    try:
        return max(0.0, min(float(raw), RETRY_AFTER_CAP))
    except ValueError:
        return None


def get(path: str, *, timeout: int = 30) -> dict:
    return request(path, None, method="GET", timeout=timeout)


# --- Task API ----------------------------------------------------------

# The documented run lifecycle: queued, action_required, running, completed,
# failed, cancelling, cancelled. `cancelling` is a real in-flight state, not a
# terminal one, so it must not be treated as an error the moment it appears.
IN_FLIGHT = {"queued", "running", "action_required", "cancelling"}
TERMINAL_BAD = {"failed", "cancelled"}

def run_task(
    input_text: str,
    schema: dict,
    *,
    processor: str = "base",
    poll_seconds: int = 8,
    max_wait: int = 360,
    on_status: Callable[[str], None] | None = None,
) -> tuple[dict, list[dict]]:
    """Run a Task to completion and return (content, basis).

    Task runs are asynchronous and take one to three minutes, so this polls.
    The second element is the per-field evidence Parallel returns alongside the
    answer: which URL, which excerpt, what reasoning, and a confidence level.
    Callers that ignore it throw away the only thing that makes an extracted
    row auditable.
    """
    run = request(
        "/v1/tasks/runs",
        {
            "input": input_text,
            "task_spec": {"output_schema": {"type": "json", "json_schema": schema}},
            "processor": processor,
        },
        timeout=60,
    )
    run_id = run.get("run_id")
    if not run_id:
        raise ParallelError(f"task run had no run_id: {str(run)[:200]}")

    # Measured against the clock, not by counting sleeps: a poll that takes ten
    # seconds to answer still spends those ten seconds, and adding only
    # `poll_seconds` each time let a slow run overrun `max_wait` substantially.
    started = time.monotonic()
    while time.monotonic() - started < max_wait:
        status = get(f"/v1/tasks/runs/{run_id}").get("status", "")
        if on_status:
            on_status(status)
        if status == "completed":
            break
        if status in TERMINAL_BAD:
            raise ParallelError(f"task run {status}")
        # Anything else is treated as still running, but only while the status
        # is one the API actually documents. An unrecognised or missing status
        # used to poll until the full max_wait (six minutes for filings) and
        # then surface as a timeout, which reads as a slow upstream rather
        # than the malformed response it is.
        if status not in IN_FLIGHT:
            raise ParallelError(f"task run returned unknown status {status!r}")
        time.sleep(poll_seconds)
    else:
        raise ParallelError(f"task run timed out after {max_wait}s")

    result = get(f"/v1/tasks/runs/{run_id}/result", timeout=60)
    output = result.get("output") or {}
    return (output.get("content") or {}), (output.get("basis") or [])
