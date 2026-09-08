"""Turn [n] markers in a briefing into linked, hoverable citations.

The model is told to cite each claim by number. Those numbers are the 1-based
index of the article list it was given, so they map straight back to sources.

`readable()` is public because it is the definition of "usable preview text":
`repo.repair_previews` asks it which excerpts are worth replacing via Parallel's
Extract API, and the two must agree or a repaired excerpt could still fail here.
"""
from __future__ import annotations

import html
import re

# A citation is one bracket, but the model routinely puts several numbers in
# it: "[2, 6, 8]". Matching only \[(\d+)\] left every grouped citation as
# literal text, which on a real briefing is nearly all of them (the live ONDS
# page had one lone [7] and eight grouped markers, so exactly one citation was
# hoverable and the rest read as broken punctuation).
_MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


# Excerpts often arrive as scraped page furniture: nav links, cookie banners,
# markdown link soup. A preview made of that is worse than no preview.
_JUNK = re.compile(r"\[[^\]]*\]\([^)]*\)|https?://\S+|[|>#*_`]+")

# Scraped excerpts carry raw HTML, and it arrives MALFORMED: the upstream text
# is literally "<strong trending down by -7.65%!</strong" with the closing ">"
# already missing. A well-formed <[^>]*> pattern therefore matches none of it,
# and _JUNK only ate the bare ">", which is why the tag NAME survived into the
# popup: the preview read "<strong Ondas Inc stocks ... </strong" on screen.
#
# So the match is anchored on "<" plus a known tag name, with the closing
# bracket optional. The attribute run is capped rather than open-ended: with no
# ">" to stop it, an unbounded [^<>]* runs to the end of the string and eats the
# whole excerpt (measured: a real preview collapsed to ""). Real attributes are
# short, so 80 characters keeps them while leaving prose after a broken tag.
_TAG_NAMES = (
    r"strong|b|em|i|span|div|p|a|br|li|ul|ol|h[1-6]|img|figure|figcaption"
    r"|small|sub|sup|code|pre|blockquote|table|tr|td|th|tbody|thead"
    r"|section|article|header|footer|nav|iframe|script|style"
)
_TAGS = re.compile(
    rf"</?\s*(?:{_TAG_NAMES})\b(?:[^<>]{{0,80}}?>|(?!\w))",
    re.I,
)


def readable(text: str, limit: int = 220) -> str:
    """The first prose-looking part of an excerpt, or nothing."""
    # Tags first: _JUNK would strip the ">" off a well-formed tag and leave the
    # name behind as prose, so the tag pattern has to see the text intact.
    cleaned = _TAGS.sub(" ", text or "")
    cleaned = _JUNK.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,-|/")
    # Require a real sentence: enough words, and not mostly punctuation.
    words = [w for w in cleaned.split() if len(w) > 2]
    if len(words) < 8:
        return ""
    return cleaned[:limit].strip()


def _host(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else ""


def link_citations(text: str, articles: list[dict]) -> str:
    """Replace [n] with a superscript link carrying a hover preview.

    A marker with no matching article is left as plain text rather than
    linked to the wrong source.
    """
    if not text:
        return ""

    def one(n: int) -> str:
        """One source as a superscript link, or "" if it points nowhere."""
        if not (1 <= n <= len(articles)):
            return ""
        a = articles[n - 1]
        url = a.get("url", "")
        title = (a.get("title") or url or "")[:120]
        excerpt = readable(a.get("excerpt") or "")
        return (
            f'<a class="cite" href="{html.escape(url)}" target="_blank" rel="noopener">'
            f"<sup>{n}</sup>"
            f'<span class="cite-pop">'
            f'<b>{html.escape(title)}</b>'
            f'<i>{html.escape(_host(url))}</i>'
            + (f"<em>{html.escape(excerpt)}&hellip;</em>" if excerpt else "")
            + "</span></a>"
        )

    def repl(m: re.Match[str]) -> str:
        # "[2, 6, 8]" is three sources, so it becomes three separate links,
        # each with its own preview: a single link carrying three previews has
        # nowhere to put the other two, and dropping all but the first would
        # quietly hide two of the three sources behind the claim.
        links = [one(int(part)) for part in m.group(1).split(",")]
        if not any(links):
            return html.escape(m.group(0))
        # A number with no article is kept as plain text in place, so the
        # bracket still reads as the model wrote it.
        parts = m.group(1).split(",")
        out = [links[i] or html.escape(parts[i].strip()) for i in range(len(parts))]
        return '<span class="cites">' + ", ".join(out) + "</span>"

    return _MARKER.sub(repl, html.escape(text))


# The model writes markdown: **bold** for emphasis and "## What happened" for
# section headings. Escaped and rendered verbatim, that shipped literal
# asterisks to the lobby card, which reads as an unfinished product on the one
# page a first-time visitor always sees. These run AFTER html.escape, so they
# match escaped text and emit the only tags allowed through.
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![\*\w])\*(?=\S)([^\*\n]+?)(?<=\S)\*(?!\*)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
# A leading "- " or "* " bullet: kept as a line, shown with a real bullet.
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+(.*)$")


def _inline_md(escaped: str) -> str:
    """Apply bold and italic to already-escaped text."""
    out = _BOLD.sub(r"<strong>\1</strong>", escaped)
    return _ITALIC.sub(r"<em>\1</em>", out)


def strip_markdown(text: str) -> str:
    """Plain text with the markdown syntax removed, for previews and cards.

    Used where HTML is not wanted (a lobby teaser is truncated mid-string, and
    cutting inside a tag would ship broken markup).
    """
    if not text:
        return ""
    lines = []
    for raw in text.split("\n"):
        line = _HEADING.sub(r"\1", raw)
        line = _BOLD_ONLY.sub(r"\1", line)
        line = _BULLET.sub(r"\1", line)
        line = _BOLD.sub(r"\1", line)
        line = _ITALIC.sub(r"\1", line)
        lines.append(line)
    return " ".join(" ".join(lines).split())


# A line that is nothing but bold text is a section label, whatever syntax the
# model reached for. Gemini writes "**Price and Technical Context**" as often as
# "## Price and Technical Context", and rendered as a bold paragraph it sat at
# body size with no space above it, so the answer read as an undifferentiated
# wall. Promoted to the same .bh heading the briefings use, the structure the
# model intended actually shows.
_BOLD_ONLY = re.compile(r"^\s*\*\*(?=\S)(.+?)(?<=\S)\*\*\s*:?\s*$")


def paragraphs(text: str, articles: list[dict]) -> str:
    """Render a briefing: markdown structure, citations, nothing else.

    Only the tags produced here reach the page. The text is escaped first, so
    a model that emits raw HTML gets it shown, not executed.
    """
    if not text:
        return ('<p style="color:var(--muted)">No briefing yet. The next scheduled pass writes one.</p>')
    out = []
    bullets: list[str] = []

    def flush() -> None:
        if bullets:
            out.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for raw in text.split("\n"):
        if not raw.strip():
            flush()
            continue
        heading = _HEADING.match(raw) or _BOLD_ONLY.match(raw)
        if heading:
            flush()
            inner = _inline_md(link_citations(heading.group(1), articles))
            out.append(f'<h3 class="bh">{inner}</h3>')
            continue
        bullet = _BULLET.match(raw)
        if bullet:
            bullets.append(_inline_md(link_citations(bullet.group(1), articles)))
            continue
        flush()
        out.append(f"<p>{_inline_md(link_citations(raw, articles))}</p>")
    flush()
    return "".join(out)
