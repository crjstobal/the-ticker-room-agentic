"""Retail sentiment from social discussion.

Reads Reddit threads and X posts together. Reddit alone is thin for most
tickers — five threads is an anecdote, not a reading — while X carries the
cashtag conversation that Reddit does not.

The score is derived from the posts themselves by the model, and it is reported
as what people are saying, never as a signal to act on.
"""
from __future__ import annotations

import json
import re

from ..adapters import gemini_enterprise as gem

RULES = """You classify retail investor sentiment from social media posts.

Return ONLY a JSON object, no prose and no code fence:
{"score": <int -100..100>, "label": "<bullish|bearish|mixed|quiet>",
 "themes": ["<short phrase>", ...], "summary": "<one or two sentences>"}

score: -100 is uniformly bearish, 0 is balanced, +100 is uniformly bullish.
label: "quiet" when there is too little discussion to call.
themes: at most 4 recurring topics, each 2-5 words.
summary: describe what people are discussing. Never advise an action.
Base everything only on the supplied posts.

Weigh a reasoned argument more heavily than a one-line punt, and treat a
company's own account as promotion rather than sentiment."""


def _extract_json(text: str) -> dict | None:
    """Parse the model's JSON, tolerating a code fence around it.

    The response is requested as application/json, so the common case is a
    clean parse. The fence stripping is a fallback, and it must run on the
    whole string rather than per line: an earlier version used MULTILINE and
    mangled valid JSON, which silently downgraded every reading to "quiet".
    """
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _cited(threads: list[dict], x_posts: list[dict]) -> list[dict]:
    """The posts the model actually saw, slimmed for storage and display.

    Only the ones passed in the prompt are listed: citing a thread the reading
    never read would be worse than citing nothing. The slices below mirror the
    [:12] caps used when the prompt is built, so the two cannot drift.
    """
    out = []
    for t in threads[:12]:
        url = t.get("url") or ""
        if not url:
            continue
        out.append({
            "platform": "reddit",
            "url": url,
            "title": (t.get("title") or url)[:180],
            "where": f"r/{t['subreddit']}" if t.get("subreddit") else "reddit",
        })
    for x in x_posts[:12]:
        url = x.get("url") or ""
        text = (x.get("post_text") or "").strip()
        if not url or not text:
            continue
        author = x.get("author") or ""
        out.append({
            "platform": "x",
            "url": url,
            "title": text[:180],
            "where": f"@{author}" if author else "X",
        })
    return out


def analyze(
    ticker: str,
    company: str,
    threads: list[dict],
    window_days: int = 7,
    x_posts: list[dict] | None = None,
) -> dict:
    """Score sentiment across Reddit and X. Returns 'quiet' when there is nothing."""
    x_posts = x_posts or []
    if not threads and not x_posts:
        return {"score": 0, "label": "quiet", "themes": [],
                "summary": f"No discussion found in the last {window_days} days.",
                "n_threads": 0, "subreddits": [], "n_x": 0, "posts": [],
                "window_days": window_days}

    lines = []
    for t in threads[:12]:
        excerpts = t.get("excerpts") or []
        body = " ".join(str(e) for e in excerpts)[:500]
        sub = t.get("subreddit") or "reddit"
        lines.append(f"- [r/{sub}] {t.get('title', '')}\n  {body}")
    for x in x_posts[:12]:
        text = (x.get("post_text") or "")[:400]
        if not text:
            continue
        author = x.get("author") or "unknown"
        lines.append(f"- [X @{author}] {text}")

    prompt = (
        f"Company: {company} ({ticker})\n\n"
        "Each post is tagged with where it came from: a subreddit, or X.\n\n"
        "POSTS:\n" + "\n".join(lines)
    )
    # The model occasionally returns something unparseable or empty. It is
    # cheap to ask again, and a retry is far better than reporting a wrong
    # "unavailable" for a ticker people are actively discussing.
    parsed: dict = {}
    error: str | None = None
    for attempt in range(2):
        try:
            payload = gem.generate(
                system_instruction=RULES,
                prompt=prompt,
                temperature=0.2 if attempt == 0 else 0.0,
                max_output_tokens=1400,
                response_mime_type="application/json",
                timeout=90,
            )
            text, finish = gem.extract(payload)
            parsed = _extract_json(text) or {}
            if parsed:
                error = None
                break
            error = (
                "response hit the output cap" if finish == "MAX_TOKENS"
                else "model returned no parseable JSON"
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    if error:
        print(f"[sentiment] failed for {ticker}: {error}")

    subs = {}
    for t in threads:
        sub = t.get("subreddit")
        if sub:
            subs[sub] = subs.get(sub, 0) + 1
    if x_posts:
        subs["X"] = len(x_posts)

    # A failed call must not look like a genuine "quiet" reading: that hides a
    # broken pipeline behind a plausible number. Say so instead.
    if error:
        # The posts still travel: the reading failed, but what it was going to
        # read is the useful half of the answer and the reader can go look.
        return {
            "score": 0, "label": "unavailable", "themes": [],
            "summary": f"Sentiment could not be read ({error}).",
            "n_threads": len(threads), "subreddits": [], "window_days": window_days,
            "posts": _cited(threads, x_posts), "error": error,
        }

    return {
        "score": int(parsed.get("score", 0)),
        "label": parsed.get("label", "quiet"),
        "themes": parsed.get("themes", [])[:4],
        "summary": parsed.get("summary", ""),
        "n_threads": len(threads) + len(x_posts),
        "n_x": len(x_posts),
        # Which communities this reading is based on, so the number is auditable.
        "subreddits": sorted(subs.items(), key=lambda kv: -kv[1])[:6],
        # The posts behind the score, so the page can cite them.
        "posts": _cited(threads, x_posts),
        "window_days": window_days,
    }
