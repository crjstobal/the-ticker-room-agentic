"""The "How does it work" page.

This page exists because the product is legible only to someone who already
knows how it is wired. Two things in particular were confusing, and both are
answered here in plain words before any architecture appears:

- What is real and what is a placeholder. The room holds one shared watchlist
  and everything in it was actually fetched, but a visitor cannot tell stored
  history from a mock-up by looking, so the page says which is which.
- Where the two front-door buttons go. "Open the room" and "See what it caught"
  land on different pages of the same single product, not on a private area and
  a demo. Naming them side by side is the whole fix.

The second half is for a judge: the request path drawn as a diagram, then the
six Parallel APIs and the Google Cloud surface, each tied to the file that
calls it so the claim is checkable rather than asserted.

Diagrams are inline SVG. No library, no build step, and they inherit the theme
variables, which a rendered image could not.
"""
from __future__ import annotations

from .render import _esc, _nav, _shell

# Every row is checkable: the file named is the one that makes the call.
PARALLEL_APIS = [
    ("Search", "src/core/research.py",
     "Reporting, Reddit and X. <code>one-shot</code> for the news behind a "
     "briefing, <code>fast</code> for the social sweeps.",
     "Two processors, not one. <code>one-shot</code> returns about three times "
     "the excerpt text at half the latency, which is what a briefing needs; "
     "the social sweeps only need the headline and the score."),
    ("Task", "src/core/targets.py, src/core/filings.py",
     "Analyst price targets and SEC filings, extracted against a JSON schema.",
     "Schema-shaped, so results arrive as rows that can be sorted, compared and "
     "alerted on. Prose could not move a consensus figure."),
    ("Monitor", "src/core/monitors.py",
     "A standing hourly watch per ticker, delivering events by webhook between "
     "the twice-daily runs.",
     "This is the part that closes the gap the product is named after: the "
     "scheduled run reacts at best in half a day, the watch in minutes. A "
     "caught event is read back through Task against the same schema, so it "
     "lands as a target or filing row rather than stopping at a notification."),
    ("FindAll", "src/core/discovery.py",
     "Proposing companies not on the watchlist: peers of a name you hold, or "
     "anything matching a plain-language theme.",
     "The watchlist goes in <code>exclude_list</code>, so the match budget is "
     "spent on names that could actually be new to you."),
    ("Extract", "src/core/extract.py",
     "Repairing citation previews whose indexed excerpt is nav bars and cookie "
     "banners.",
     "A citation you cannot read is a citation you cannot check, which would "
     "defeat the point of keeping one."),
    ("Responses", "src/core/responses.py",
     "A second answer on the Ask page, read live from the open web and shown "
     "beside the agent&#8217;s own.",
     "The agent answers from what this service stored, which is only ever as "
     "fresh as the last run. Asking a different corpus the same question is "
     "how a reader can tell a settled fact from a stale one. Note the auth: "
     "Responses is OpenAI-compatible and wants <code>Authorization: Bearer</code>, "
     "where every other endpoint takes <code>x-api-key</code>."),
]

GOOGLE_CLOUD = [
    ("Gemini, on the Gemini Enterprise Agent Platform",
     "src/adapters/gemini_enterprise.py",
     "Writes the briefing from what Parallel gathered, and answers on the Ask "
     "page. Every claim is cited back to a numbered source."),
    ("Cloud Run", "Dockerfile",
     "Hosts the service. Runs with <code>--min-instances=1</code>, because a "
     "cold start was twelve seconds and a first-time visitor makes exactly one "
     "cold request."),
    ("Firestore", "src/adapters/firestore_store.py",
     "Stores the history in production: articles, briefings, targets, filings, "
     "quotes and caught events. Locally the same interface is backed by SQLite."),
    ("Cloud IAM", "the service account",
     "The service runs as <code>ticker-room-agent</code> with four roles and "
     "no others: Vertex AI user, Datastore user, Secret Manager accessor, and "
     "log writer. It cannot reach anything else in the project."),
]

# The confusions this page was written to answer, in the order they arise.
FAQ = [
    ("What is real here, and what is a placeholder?",
     "Everything on screen was actually fetched. The articles, price targets, "
     "filings and caught events are stored results from real runs against the "
     "live web, not seeded fixtures, and the counts on the front page count "
     "rows in the database. What is <b>not</b> real yet is separation between "
     "people: there is no sign-in, and the room holds one shared watchlist. "
     "Add a ticker and you are adding it to the same list everyone else sees. "
     "Per-user watchlists are the next thing to build, not something hidden "
     "behind a login that does not exist."),
    ("Where do I see what the watch caught?",
     "On the page for the company it happened to. Open a ticker from the "
     "watchlist and you get its standing watch, the events that watch picked "
     "up between scheduled runs, and any Grafana alert that fired on it, "
     "alongside the briefing and the numbers. There used to be a separate "
     "<i>Alerts</i> page carrying the same events again as one combined "
     "stream, which meant reading your own watchlist twice to find the one "
     "name you came for."),
    ("Why did the menu keep changing?",
     "It was a bug in how the pages were written, and it is fixed. Each page "
     "used to print its own list of links, so the destinations shifted as you "
     "moved: Watchlist disappeared once you were inside, and Ask and Settings "
     "appeared only on some pages. The menu is now defined once and is "
     "identical everywhere, with the page you are on marked in amber instead "
     "of removed from the list."),
    ("Does it tell me what to buy?",
     "No, and it is built so it cannot drift into doing so. It reports what "
     "changed and shows the sentence it read that from. Every extracted figure "
     "keeps its source, the reasoning, and Parallel's own confidence level: "
     "hover the <b>?</b> beside a price target and you get the evidence rather "
     "than an assurance."),
]

WHERE = [
    ("The Lobby", "/lobby",
     "Every ticker being tracked, ranked so the name that needs attention is "
     "first. Each card carries the latest briefing, the price, and how coverage "
     "has moved. Click a ticker for its own page."),

    ("Discover", "/discover",
     "Companies you have <i>not</i> named, proposed with evidence: peers of "
     "something you hold, or matches for a theme you describe in plain words."),
    ("Ask", "/ask",
     "A question in plain language, answered by Gemini from the stored history "
     "rather than from the open web, so the answer cites rows you can go and "
     "check."),
    ("Settings", "/settings",
     "Alert thresholds, and whether Reddit is read for sentiment."),
]

EXPLAIN_CSS = """
.ex-lede{font-size:16.5px;line-height:1.68;color:#c8c8d4;max-width:64ch;
  margin:0 0 10px}
.ex-h{font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);margin:66px 0 18px;font-weight:600}
.ex-h:first-of-type{margin-top:34px}

.faq{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);
  border-radius:12px;overflow:hidden}
.faq-i{background:var(--panel);padding:24px 28px;display:grid;
  grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);gap:28px;align-items:start}
.faq-q{font-size:15.5px;color:var(--ink);font-weight:600;line-height:1.45;margin:0}
.faq-a{font-size:14px;color:#b8b8c6;line-height:1.66;margin:0}
.faq-a b{color:var(--ink);font-weight:600}

/* The diagram is inline SVG so it picks up the theme variables and stays sharp.
   It scrolls inside its own box: on a narrow screen a wide diagram must never
   widen the page itself. */
.diagram{border:1px solid var(--line);border-radius:12px;background:var(--panel);
  padding:26px 20px;overflow-x:auto;width:100%}
.diagram svg{display:block;min-width:660px;margin:0 auto;height:auto;max-width:100%}
.d-lbl{font:600 11px var(--mono);fill:var(--ink);letter-spacing:.04em}
.d-sub{font:10px var(--mono);fill:var(--muted)}
.d-cap{font:600 9.5px var(--mono);fill:var(--muted);letter-spacing:.14em}
.d-box{fill:var(--panel-2);stroke:var(--line)}
.d-box.hi{stroke:var(--amber)}
.d-arrow{stroke:var(--line);stroke-width:1.4;fill:none}

/* The plain-language diagram. Bigger type than the technical one below it on
   purpose: this is the one a visitor reads, so it is sized to be read at a
   glance rather than studied. */
.u-box{fill:var(--panel-2);stroke:var(--line)}
.u-num{fill:var(--amber)}
.u-n{font:600 13px var(--mono);fill:#12121a}
.u-t{font:600 13px var(--sans,inherit);fill:var(--ink)}
.u-sub{font:11.5px var(--sans,inherit);fill:var(--muted)}
.u-chev{stroke:var(--line);stroke-width:2;fill:none;stroke-linecap:round;
  stroke-linejoin:round}

/* The API cards. The amber tab down the left edge is what makes five boxes
   scan as a set rather than as five unrelated rectangles. */
.a-tab{fill:var(--amber)}
.a-name{font:600 13px var(--mono);fill:var(--ink)}
.a-when{font:10px var(--mono);fill:var(--amber);letter-spacing:.04em}
.d-box.dim{stroke-dasharray:4 3}
.dim-t{fill:var(--muted)}
.diagram figcaption{font-size:12px;color:var(--muted);text-align:center;
  margin-top:16px;line-height:1.6}

/* Four plain statements under the plain diagram. A grid rather than a list,
   because these are peers and none of them is a step after another. */
.plain{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);
  border-radius:12px;overflow:hidden;margin-top:18px}
.plain-i{background:var(--panel);padding:20px 22px;font-size:13.5px;
  line-height:1.66;color:#b8b8c6}
.plain-i b{color:var(--ink);font-weight:600}
.plain .q{font-family:var(--mono);color:var(--amber);border:1px solid var(--line);
  border-radius:50%;padding:0 5px;font-size:11px}
.ex-note{font-size:13.5px;color:var(--muted);line-height:1.66;max-width:62ch;
  margin:-6px 0 16px}

/* `table-layout:fixed` is the whole fix for the column widths. Under the
   default `auto`, the browser sizes columns from their content and treats the
   `width` on a `th` as a suggestion it may ignore, and `max-width` on a `td`
   has no effect at all. The Google Cloud table came out 904/101/61: the
   service-name column took the width of its longest name and the prose that
   matters was squeezed to about two words a line. Fixed layout makes the
   declared widths authoritative, so the prose column gets everything left
   over. Every `.api` table therefore needs a width on each non-prose column. */
.api{width:100%;border-collapse:collapse;font-size:13.5px;table-layout:fixed}
.api th{text-align:left;font-size:10.5px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);font-weight:600;
  padding:0 16px 11px 0;border-bottom:1px solid var(--line)}
.api td{padding:17px 16px 17px 0;border-bottom:1px solid var(--line);
  vertical-align:top;color:#b8b8c6;line-height:1.6}
.api tr:last-child td{border-bottom:0}
.api .n{font-family:var(--mono);color:var(--amber);font-weight:600;
  white-space:nowrap;font-size:13px}
/* A long service name must wrap rather than force the table past its column.
   `white-space:normal` alone was not enough: without a width the cell still
   claimed its longest line ("Gemini, on the Gemini Enterprise Agent Platform")
   and the prose column next to it collapsed to 101px, one or two words per
   line. A `width` on the `th` is only a hint the browser is free to override,
   so the cap goes on the cell itself. */
.api .n.wrap{white-space:normal;line-height:1.45;max-width:210px}
/* Same trap in the third column: a file path in `code` cannot break, so it
   sets the column's minimum width no matter what the header asks for. Letting
   it break anywhere keeps the prose column readable. */
.api td:last-child code{overflow-wrap:anywhere}
.api code{font-family:var(--mono);font-size:11.5px;color:var(--muted);
  background:var(--panel-2);padding:1px 5px;border-radius:4px}
.api .why{color:var(--muted);font-size:12.5px;display:block;margin-top:7px;
  line-height:1.6}
.api-wrap{border:1px solid var(--line);border-radius:12px;background:var(--panel);
  padding:6px 24px 8px;overflow-x:auto;width:100%}

.where{display:grid;grid-template-columns:repeat(auto-fit,minmax(268px,1fr));
  gap:14px}
.w-i{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:20px 22px}
.w-i:hover{border-color:var(--muted)}
.w-t{display:flex;align-items:baseline;gap:9px;margin-bottom:7px}
.w-t b{font-size:14.5px;color:var(--ink);font-weight:600}
.w-t span{font-family:var(--mono);font-size:11px;color:var(--amber)}
.w-i p{margin:0;font-size:13px;color:#b0b0be;line-height:1.6}

@media (max-width:760px){
  .faq-i{grid-template-columns:1fr;gap:12px}
  .diagram{padding:20px 14px}
  /* Fixed layout honours the declared 150 and 210 even when there is no room
     left for the prose between them: at 500px the middle column came out at
     54px, which is one word per line. Below this width the table stops trying
     to fit and scrolls inside `.api-wrap` instead, the same way the diagrams
     do. 620 is the narrowest width at which the prose column still holds a
     readable line. */
  .api{min-width:620px}
}
"""


def _user_svg() -> str:
    """The product in four steps, in the reader's own terms.

    Deliberately carries no API names, no file paths and no crossing arrows.
    Somebody who has never heard of Parallel should be able to read this one
    and stop; the technical diagram below exists only for whoever wants it.
    """
    def step(x, n, title, l1, l2, l3=""):
        third = (f'<text x="{x + 95}" y="194" text-anchor="middle" '
                 f'class="u-sub">{l3}</text>') if l3 else ""
        return (
            f'<circle cx="{x + 95}" cy="40" r="16" class="u-num"/>'
            f'<text x="{x + 95}" y="45" text-anchor="middle" class="u-n">{n}</text>'
            f'<rect x="{x}" y="72" width="190" height="134" rx="10" class="u-box"/>'
            f'<text x="{x + 95}" y="105" text-anchor="middle" class="u-t">{title}</text>'
            f'<text x="{x + 95}" y="138" text-anchor="middle" class="u-sub">{l1}</text>'
            f'<text x="{x + 95}" y="156" text-anchor="middle" class="u-sub">{l2}</text>'
            f'{third}'
        )

    def chev(x):
        return f'<path d="M{x} 132 L{x + 13} 140 L{x} 148" class="u-chev"/>'

    return f"""<svg viewBox="0 0 900 240" role="img"
  aria-label="Four steps: you add a company, the room reads about it twice a
  day, it keeps watching in between, and you get a short briefing in which
  every figure can be traced back to the sentence it came from.">
{step(10, "1", "You add a company", "Type a ticker, or let", "the room suggest", "similar names")}
{chev(212)}
{step(240, "2", "It does the reading", "News, Reddit, filings", "and analyst targets,", "twice every weekday")}
{chev(442)}
{step(470, "3", "It keeps watching", "In between it checks", "every hour and says", "what actually changed")}
{chev(672)}
{step(700, "4", "You read the short version", "A briefing where every", "figure carries the", "sentence behind it")}
</svg>
<figcaption>Nothing here asks you to search, filter or configure. You name a
company once; the rest happens whether or not anybody is looking.</figcaption>"""


def _flow_svg() -> str:
    """One ticker's journey, left to right, as a request actually travels.

    Drawn by hand rather than generated: there are seven boxes and they never
    change, so a layout engine would be more code than the picture.
    """
    def box(x, y, w, h, label, sub, hi=False):
        cls = "d-box hi" if hi else "d-box"
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="{cls}"/>'
            f'<text x="{x + w / 2}" y="{y + 22}" text-anchor="middle" class="d-lbl">{label}</text>'
            f'<text x="{x + w / 2}" y="{y + 39}" text-anchor="middle" class="d-sub">{sub}</text>'
        )

    def arrow(x1, y1, x2, y2):
        return (f'<path d="M{x1} {y1} L{x2} {y2}" class="d-arrow" '
                f'marker-end="url(#ah)"/>')

    return f"""<svg viewBox="0 0 900 340" role="img"
  aria-label="A ticker flows into Parallel Search and Task, then into Gemini,
  then into Firestore, and out to the page, with Monitor feeding events back in
  and Grafana reading the stored history.">
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
  markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#2a2a38"/>
</marker></defs>

<text x="20" y="24" class="d-cap">SCHEDULED RUN &#183; 09:45 AND 17:45 ET, WEEKDAYS</text>
{box(20, 40, 130, 56, "Ticker", "researched once", hi=True)}
{arrow(150, 68, 205, 68)}
{box(210, 40, 165, 56, "Parallel Search", "news &#183; Reddit &#183; X")}
{arrow(375, 68, 430, 68)}
{box(435, 40, 165, 56, "Parallel Task", "targets &#183; filings")}
{arrow(600, 68, 655, 68)}
{box(660, 40, 220, 56, "Gemini", "writes the briefing")}

{arrow(770, 96, 770, 145)}
{box(660, 149, 220, 56, "Firestore", "the history accumulates")}

<text x="20" y="133" class="d-cap">BETWEEN RUNS &#183; EVERY HOUR</text>
{box(20, 149, 165, 56, "Parallel Monitor", "standing hourly watch")}
{arrow(185, 177, 240, 177)}
{box(245, 149, 175, 56, "Webhook", "/hooks/parallel")}
{arrow(420, 177, 475, 177)}
{box(480, 149, 165, 56, "Parallel Task", "same schema")}
{arrow(645, 177, 658, 177)}

<text x="20" y="242" class="d-cap">WHAT YOU SEE</text>
{box(20, 258, 210, 56, "The room", "lobby &#183; discover &#183; ask", hi=True)}
{box(250, 258, 210, 56, "Grafana", "alerts on the history")}
<path d="M770 205 L770 230 Q770 240 760 240 L245 240 Q235 240 235 250 L235 254"
  class="d-arrow" marker-end="url(#ah)"/>

<text x="490" y="284" class="d-sub">every figure keeps the sentence it came from</text>
<text x="490" y="300" class="d-sub">a ticker on ten watchlists is researched once, not ten times</text>
</svg>
<figcaption>A ticker is researched top-left to top-right, and what is learned
lands in Firestore. The middle row is the part that runs while nobody is
looking: a standing monitor catches an event, and it is read back through the
same schema so it becomes a row, not a notification.</figcaption>"""


def _apis_svg() -> str:
    """The six Parallel APIs, each with the job it does here.

    Six and not nine: Parallel's own product page lists nine cards, but three
    of them (Interactions, Deep Research, Enrichment) are labelled Task API and
    are use cases of it, not separate endpoints. Six is the real surface, and
    all six are called by this codebase.

    Sits after the flow diagram because that one shows *when* each runs and
    this shows *why* that one and not another. Three of the six never appear in
    the scheduled path: they answer a question a reader asked, so a diagram of
    the run alone would leave them unexplained.
    """
    # SVG text does not wrap, so every line here is measured to fit inside the
    # card rather than trusted to. The usable width is 252 (288 less the 18
    # inset on each side), which is about 41 characters of the 10px mono, and
    # the lines below were checked against it. An earlier set was written by
    # eye and ran up to 65 units past the right edge of the box, with three
    # lines in the right-hand column spilling out of the viewBox itself.
    def card(x, y, name, when, l1, l2, l3):
        return (
            f'<rect x="{x}" y="{y}" width="288" height="124" rx="10" class="d-box"/>'
            f'<rect x="{x}" y="{y}" width="4" height="124" class="a-tab"/>'
            f'<text x="{x + 18}" y="{y + 25}" class="a-name">{name}</text>'
            f'<text x="{x + 18}" y="{y + 43}" class="a-when">{when}</text>'
            f'<text x="{x + 18}" y="{y + 68}" class="d-sub">{l1}</text>'
            f'<text x="{x + 18}" y="{y + 86}" class="d-sub">{l2}</text>'
            f'<text x="{x + 18}" y="{y + 104}" class="d-sub">{l3}</text>'
        )

    return f"""<svg viewBox="0 0 900 494" role="img"
  aria-label="The six Parallel APIs used here. On every scheduled run: Search
  for reporting and social chatter, Task for analyst targets and SEC filings,
  Monitor for the hourly watch. Only when you ask: FindAll proposes companies
  you have not named, Extract repairs unreadable citations, and Responses gives
  a second opinion read live from the web.">
<text x="10" y="18" class="d-cap">ON EVERY SCHEDULED RUN &#183; COSTS MONEY WHETHER OR NOT ANYBODY LOOKS</text>
{card(10, 30, "Search", "twice a weekday, per ticker",
      "Finds the reporting, the Reddit threads",
      "and the X posts. one-shot for the news,",
      "fast for the chatter.")}
{card(316, 30, "Task", "twice a weekday, per ticker",
      "Reads analyst targets and SEC filings",
      "into a fixed schema, so they arrive as",
      "rows you can sort and diff.")}
{card(622, 30, "Monitor", "every hour, standing",
      "Watches between runs and pushes an",
      "event by webhook when something",
      "happens. The interrupt path.")}

<text x="10" y="194" class="d-cap">ONLY WHEN SOMEBODY ASKS &#183; NO CLICK, NO COST</text>
{card(10, 206, "FindAll", "when you open Discover",
      "Turns a plain sentence into a list of",
      "companies that fit it, evidence",
      "attached. Widens the watchlist.")}
{card(316, 206, "Extract", "when a citation is unreadable",
      "Goes back to the page for a clean",
      "passage when the indexed excerpt is a",
      "cookie banner instead of prose.")}
{card(622, 206, "Responses", "when you ask a question",
      "Answers from the live web beside the",
      "agent's answer, with its own citations.",
      "A cross-check, not a rival.")}

<text x="10" y="370" class="d-cap">WHY SIX AND NOT ONE</text>
<rect x="10" y="382" width="880" height="96" rx="10" class="d-box dim"/>
<text x="30" y="408" class="d-sub">Search finds text. Task turns that text into numbers. Monitor removes the waiting between runs.</text>
<text x="30" y="428" class="d-sub">FindAll asks the question backwards: not &#8220;what about this company&#8221; but &#8220;which companies fit this sentence&#8221;.</text>
<text x="30" y="448" class="d-sub">Extract repairs what the web index got wrong. Responses answers the same question from a different corpus,</text>
<text x="30" y="468" class="d-sub">so an answer can be checked against something other than this service&#8217;s own memory.</text>
</svg>
<figcaption>Six APIs, three on the clock and three answering a question
somebody asked. The split is also the cost model: the top row runs whether or
not anybody is watching, the bottom row only ever runs because of a click.
Parallel&#8217;s product page shows nine cards, but Interactions, Deep Research
and Enrichment are all the Task API under different names.</figcaption>"""


def _evidence_svg() -> str:
    """Why a number on this page can be checked: what travels with it."""
    return """<svg viewBox="0 0 900 200" role="img"
  aria-label="A source sentence becomes a schema-extracted field that keeps its
  quote, reasoning and confidence, which the page shows on hover.">
<defs><marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
  markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#2a2a38"/>
</marker></defs>

<rect x="20" y="40" width="250" height="112" rx="8" class="d-box"/>
<text x="145" y="66" text-anchor="middle" class="d-lbl">SOURCE PAGE</text>
<text x="145" y="90" text-anchor="middle" class="d-sub">&#8220;&#8230;raised its target</text>
<text x="145" y="106" text-anchor="middle" class="d-sub">to $24 from $19&#8230;&#8221;</text>
<text x="145" y="132" text-anchor="middle" class="d-sub">one sentence, in situ</text>

<path d="M270 96 L325 96" class="d-arrow" marker-end="url(#ah2)"/>

<rect x="330" y="40" width="230" height="112" rx="8" class="d-box hi"/>
<text x="445" y="66" text-anchor="middle" class="d-lbl">PARALLEL TASK</text>
<text x="445" y="90" text-anchor="middle" class="d-sub">extracted to a schema</text>
<text x="445" y="112" text-anchor="middle" class="d-sub">target = 24.00</text>
<text x="445" y="132" text-anchor="middle" class="d-sub">+ basis, + confidence</text>

<path d="M560 96 L615 96" class="d-arrow" marker-end="url(#ah2)"/>

<rect x="620" y="40" width="260" height="112" rx="8" class="d-box"/>
<text x="750" y="66" text-anchor="middle" class="d-lbl">ON THE PAGE</text>
<text x="750" y="90" text-anchor="middle" class="d-sub">$24.00 &#160;?</text>
<text x="750" y="114" text-anchor="middle" class="d-sub">hover the ? and the</text>
<text x="750" y="130" text-anchor="middle" class="d-sub">sentence comes back</text>
</svg>
<figcaption>Nothing is asserted on its own authority. The sentence a figure was
read from travels with the figure all the way to the screen, which is why a
number here can be disagreed with.</figcaption>"""


def render(last_run: dict | None = None) -> str:
    faq = "".join(
        f'<div class="faq-i"><p class="faq-q">{q}</p><p class="faq-a">{a}</p></div>'
        for q, a in FAQ
    )
    where = "".join(
        f'<a class="w-i" href="{href}"><div class="w-t"><b>{name}</b>'
        f'<span>{href}</span></div><p>{body}</p></a>'
        for name, href, body in WHERE
    )
    apis = "".join(
        f'<tr><td class="n">{name}</td><td>{what}'
        f'<span class="why">{why}</span></td>'
        f'<td><code>{_esc(where_)}</code></td></tr>'
        for name, where_, what, why in PARALLEL_APIS
    )
    gcp = "".join(
        f'<tr><td class="n wrap">{name}</td><td>{what}</td>'
        f'<td><code>{_esc(where_)}</code></td></tr>'
        for name, where_, what in GOOGLE_CLOUD
    )

    body = f"""
<h2 style="font-size:27px;margin:0 0 14px;letter-spacing:-.015em">How it works</h2>
<p class="ex-lede">Keeping up with a company means reading the same handful of
places over and over: the news, the filings, what analysts moved, what people
are arguing about. The Ticker Room does that reading on a schedule and hands
you the short version, with the sentence behind every figure still attached.</p>

<h3 class="ex-h">The whole thing in four steps</h3>
<figure class="diagram" style="margin:0">{_user_svg()}</figure>

<div class="plain">
  <div class="plain-i"><b>Twice a weekday, not constantly.</b> Once a quarter
  hour after the US market opens, once just after it closes. Companies file
  most of their news in the hour after the close, so that is when it looks.</div>
  <div class="plain-i"><b>And once an hour in between.</b> The scheduled read
  is thorough but slow to react, so a lighter watch runs every hour and only
  speaks up when something actually happened. That is what fills <i>what the
  watch caught</i> on each company's page.</div>
  <div class="plain-i"><b>Every number can be checked.</b> Hover the small
  <span class="q">?</span> next to any figure and the sentence it was read
  from comes back, with a link to the page it came from. Nothing here asks to
  be taken on trust.</div>
  <div class="plain-i"><b>It is not advice.</b> It reports what was published
  and who said it. It never tells you to buy or sell anything.</div>
</div>

<h3 class="ex-h">Questions this page exists to answer</h3>
<div class="faq">{faq}</div>

<h3 class="ex-h">Where everything is</h3>
<div class="where">{where}</div>

<h3 class="ex-h">Under the hood, once a ticker is researched</h3>
<p class="ex-note">The same four steps again, this time naming what does the
work. Everything below is for whoever wants to check the wiring.</p>
<figure class="diagram" style="margin:0">{_flow_svg()}</figure>

<h3 class="ex-h">The six Parallel APIs, and what each one is for</h3>
<p class="ex-note">The diagram above shows when each one runs. This shows why
that one and not another, and which of them only ever run because somebody
clicked.</p>
<figure class="diagram" style="margin:0">{_apis_svg()}</figure>

<h3 class="ex-h">Why you can check any number on the page</h3>
<figure class="diagram" style="margin:0">{_evidence_svg()}</figure>

<h3 class="ex-h">Parallel, api by api, with the file that calls it</h3>
<div class="api-wrap"><table class="api">
<thead><tr><th style="width:104px">API</th><th>What it does here, and why this
one</th><th style="width:210px">Where</th></tr></thead>
<tbody>{apis}</tbody></table></div>

<h3 class="ex-h">Google Cloud</h3>
<div class="api-wrap"><table class="api">
<thead><tr><th style="width:150px">Service</th><th>What it does here</th>
<th style="width:210px">Where</th></tr></thead>
<tbody>{gcp}</tbody></table></div>

<h3 class="ex-h">The rest of it</h3>
<div class="api-wrap"><table class="api">
<colgroup><col style="width:150px"><col><col style="width:210px"></colgroup>
<tbody>
<tr><td class="n">Grafana</td><td>Reads the stored history and alerts on
coverage spikes, target cuts and dilution. Alerts arrive back into the app at
<code>/hooks/grafana</code>, behind a shared secret.<span class="why">Alert
rules currently aggregate over the whole watchlist, so a notification can tell
you a target was cut without naming the company. Per-ticker labels are
known work, not a claim.</span></td><td><code>grafana/provisioning</code></td></tr>
<tr><td class="n">Storage</td><td>Firestore in production, SQLite when you run
it locally. One interface, so the same code path is exercised either
way.</td><td><code>src/core/storage.py</code></td></tr>
<tr><td class="n">Licence</td><td>AGPL-3.0. The whole thing is readable,
including the parts described above.</td>
<td><code>LICENSE</code></td></tr>
</tbody></table></div>

<h3 class="ex-h">What is not built yet</h3>
<div class="api-wrap"><table class="api">
<colgroup><col style="width:150px"><col><col style="width:210px"></colgroup>
<tbody>
<tr><td class="n">Accounts</td><td>No sign-in, and one shared watchlist for
everyone. This is the honest limit of the current build, and the reason the
room looks the same to every visitor.</td><td></td></tr>
<tr><td class="n">Per-ticker alerts</td><td>Grafana rules aggregate across the
watchlist rather than labelling by company.</td><td></td></tr>
</tbody></table></div>
"""
    return _shell("How it works \u00b7 The Ticker Room", body, last_run,
                  here="/how-it-works", extra_css=EXPLAIN_CSS)
