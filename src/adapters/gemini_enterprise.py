"""Gemini access through Gemini Enterprise Agent Platform (formerly Vertex AI).

This is the platform the project is required to run on, and it differs from the
AI Studio endpoint in how it authenticates: a Google Cloud identity with IAM
roles rather than a standalone API key. The calling code does not change.

Auth resolution order:
  1. Application Default Credentials (a service account on Cloud Run, or
     `gcloud auth application-default login` locally).
  2. The gcloud user credential, as a local development fallback.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from functools import lru_cache

PROJECT = "ticker-room"
# gemini-3.6-flash is served from the `global` location; regional endpoints
# return 404 for it.
LOCATION = "global"
MODEL = "gemini-3.6-flash"
BASE = (
    f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}"
    f"/locations/{LOCATION}/publishers/google/models"
)
SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class AuthUnavailable(RuntimeError):
    """No Google Cloud credential could be resolved."""


@lru_cache(maxsize=1)
def _adc():
    try:
        from google.auth import default

        creds, _ = default(scopes=[SCOPE])
        return creds
    except Exception:
        return None


def _token() -> str:
    creds = _adc()
    if creds is not None:
        from google.auth.transport.requests import Request

        if not creds.valid:
            creds.refresh(Request())
        return creds.token

    try:
        return subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        raise AuthUnavailable(
            "No Google Cloud credential. Run `gcloud auth application-default login`."
        ) from exc


def generate(
    *,
    system_instruction: str,
    prompt: str,
    temperature: float = 0.3,
    max_output_tokens: int = 4096,
    response_mime_type: str | None = None,
    timeout: int = 120,
) -> dict:
    """Call Gemini and return the raw response payload."""
    generation_config: dict = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if response_mime_type:
        generation_config["responseMimeType"] = response_mime_type

    body = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    req = urllib.request.Request(
        f"{BASE}/{MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def extract(payload: dict) -> tuple[str, str]:
    """Pull the text and finish reason out of a response."""
    cand = (payload.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    return text.strip(), cand.get("finishReason", "")
