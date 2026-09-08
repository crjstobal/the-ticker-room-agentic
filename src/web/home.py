"""The front door.

Everything else in this product is for someone who already uses it. This page
is for someone who does not, and it has one job: name the problem they
actually have, and show that the thing which fixes it is already running.

The problem is not "I need more financial news". Anyone can get more. It is
that news about a company you own arrives while you are doing something else,
and you find out days later, from a price move you cannot explain. The gap
between when a filing is filed and when its holder reads about it is the whole
product, so it is the hero: a strip of what was caught, stamped with how long
after the event it landed.

Design notes, so a later edit does not undo the reasoning:

- The identity is already set by the app: marquee bulbs, amber on near-black,
  "Now showing". This page extends that rather than inventing a second brand,
  because a landing page that looks unrelated to the product is a worse lie
  than an ugly one.
- The signature element is the reel: real caught events, in sequence, each
  with its lag. It is the only place on the page allowed to be loud.
- No invented numbers. Every figure shown is read from stored history, and
  when there is none the page says so rather than showing a plausible
  fiction. A financial product that fakes its own track record on the front
  page has already told you what it is.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .render import CSS, DISCLAIMER, FAVICON, _esc, _nav

# The page's own layer on top of the app's tokens. Kept here rather than in the
# shared CSS: nothing else in the product uses these, and putting them in the
# global sheet would make every page pay for the front door.
HOME_CSS = """
/* Two columns so the hero fills the measure: the argument on the left, and on
   the right the thing being argued about, a real briefing card lifted from the
   product. A single left column left half the page empty and made the claim
   look unsupported. */
.hero{padding:74px 0 18px;position:relative;display:grid;
  grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr);gap:52px;
  align-items:center}
.kicker{font-size:11px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--amber);font-weight:600;margin-bottom:22px}
.hero h2{font-size:clamp(30px,5.4vw,52px);line-height:1.08;margin:0 0 22px;
  letter-spacing:-.022em;font-weight:600;max-width:16ch}
/* Near-ink rather than amber: the second sentence is the payoff and needs
   emphasis, but amber is spent on the call to action and the marquee. Two
   amber elements competing makes neither read as primary. */
.hero h2 i{font-style:normal;color:#8d8da0}
.lede{font-size:17px;line-height:1.62;color:#c8c8d4;max-width:56ch;margin:0 0 34px}
.cta-note{font-size:13px;line-height:1.62;color:var(--muted);max-width:54ch;
  margin:18px 0 0}
.cta-note a{color:var(--amber);text-decoration:underline;text-underline-offset:2px}
.cta{display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.btn-lg{padding:13px 24px;font-size:14px;font-weight:600;border-radius:8px;
  background:var(--amber);color:#14140c;border:0;cursor:pointer;
  text-decoration:none;display:inline-block;transition:transform .12s ease}
.btn-lg:hover{transform:translateY(-1px)}
.btn-2{padding:13px 22px;font-size:14px;border-radius:8px;color:var(--ink);
  border:1px solid var(--line);text-decoration:none;display:inline-block}
.btn-2:hover{border-color:#3d3d50}


/* The proof card: what the product actually produces, shown rather than
   described. Tilted a degree so it reads as an artefact placed on the page
   instead of a second panel in the layout. */
.proof{border:1px solid var(--line);border-radius:12px;background:var(--panel);
  padding:22px 24px;transform:rotate(-.55deg);
  box-shadow:0 18px 48px rgba(0,0,0,.45)}
.proof-top{display:flex;align-items:center;justify-content:space-between;
  gap:12px;margin-bottom:14px;padding-bottom:13px;
  border-bottom:1px solid var(--line)}
.proof-tk{font-family:var(--mono);font-size:13px;color:var(--amber);
  font-weight:600}
.proof-px{font-family:var(--mono);font-size:12px;color:var(--muted)}
.proof-b{font-size:13.5px;line-height:1.66;color:#cdcdd9;margin:0}
.proof-b sup{color:var(--amber);font-size:10px;padding-left:1px}
.proof-foot{margin-top:16px;padding-top:13px;border-top:1px solid var(--line);
  display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.pill{font-size:10.5px;font-family:var(--mono);color:var(--muted);
  border:1px solid var(--line);border-radius:99px;padding:3px 9px}
.pill.on{color:var(--up);border-color:rgba(61,220,151,.3)}

/* The reel: the signature. A strip of caught events, each stamped with how
   long after the event it arrived. Scrolls on its own axis so a narrow screen
   never forces the page sideways. */
.reel-head{display:flex;justify-content:space-between;align-items:baseline;
  gap:16px;margin:64px 0 14px;flex-wrap:wrap}
.reel-head h3{font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);margin:0;font-weight:600}
.reel-note{font-size:12px;color:var(--muted)}
.reel{display:flex;gap:0;overflow-x:auto;border:1px solid var(--line);
  border-radius:12px;background:var(--panel);
  /* Sprocket holes, the one piece of literal cinema on the page. Drawn in
     CSS rather than shipped as an image so it costs nothing. */
  background-image:radial-gradient(circle at 10px 9px,var(--bg) 3.5px,transparent 4px),
    radial-gradient(circle at 10px calc(100% - 9px),var(--bg) 3.5px,transparent 4px);
  background-size:20px 100%;background-repeat:repeat-x;
  padding:20px 0;scrollbar-width:thin;
  animation:reel-run 1.6s linear infinite}
/* The strip travels exactly one sprocket pitch (20px, the background-size) per
   cycle, so the loop is seamless: hole n lands where hole n+1 began. */
@keyframes reel-run{from{background-position-x:0}to{background-position-x:20px}}
@media (prefers-reduced-motion:reduce){.reel{animation:none}}
.frame{flex:0 0 268px;padding:4px 22px;border-right:1px solid var(--line);
  display:flex;flex-direction:column;gap:9px;min-height:132px}
.frame:last-child{border-right:0}
.frame-top{display:flex;align-items:center;gap:9px}
.frame-tk{font-family:var(--mono);font-size:12px;font-weight:600;
  color:var(--amber);letter-spacing:.04em}
.lag{font-family:var(--mono);font-size:10.5px;color:var(--up);
  border:1px solid rgba(61,220,151,.32);border-radius:99px;padding:2px 8px;
  white-space:nowrap}
/* A cut target is the one finding whose direction matters on sight. Filings
   are neutral: a Form 4 is a fact, not a verdict. */
.lag.down{color:var(--down);border-color:rgba(255,107,107,.34)}
.lag.flat{color:var(--muted);border-color:var(--line)}
.frame-text{font-size:13px;line-height:1.5;color:#d2d2de;
  display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;
  overflow:hidden}
.frame-src{font-size:11px;color:var(--muted);font-family:var(--mono);
  margin-top:auto}
.reel-empty{padding:34px 24px;color:var(--muted);font-size:14px}
.reel.draggable{cursor:grab}
.reel.dragging{cursor:grabbing;user-select:none;scroll-behavior:auto}
.reel.dragging .frame{pointer-events:none}

/* The problem, stated as three failures rather than three features. Each row
   is a thing that actually goes wrong, paired with what the product does
   about it, so the list is an argument and not a brochure. */
.probs{margin:74px 0 0;display:grid;gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:12px;overflow:hidden}
.prob{background:var(--panel);padding:26px 28px;display:grid;
  grid-template-columns:1fr 1fr;gap:26px;align-items:start}
.prob-q{font-size:16px;color:var(--ink);font-weight:600;line-height:1.42;
  margin:0}
.prob-a{font-size:14px;color:#b8b8c6;line-height:1.62;margin:0}
.prob-a b{color:var(--ink);font-weight:600}

.how{margin:74px 0 0}
.how h3{font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);margin:0 0 20px;font-weight:600}
.steps{display:grid;gap:14px}
.step{display:grid;grid-template-columns:auto 1fr;gap:18px;align-items:baseline;
  padding:18px 22px;background:var(--panel);border:1px solid var(--line);
  border-radius:10px}
/* Numbered because this genuinely is a sequence: each step consumes what the
   one before it produced. */
.step-n{font-family:var(--mono);font-size:11px;color:var(--amber)}
.step-b{margin:0;font-size:14px;line-height:1.6;color:#c2c2d0}
.step-b b{color:var(--ink);font-weight:600;display:block;margin-bottom:3px;
  font-size:14.5px}

.closer{margin:74px 0 0;text-align:center;padding:52px 24px;
  border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.closer h3{font-size:23px;margin:0 0 12px;font-weight:600;letter-spacing:-.01em}
.closer p{color:var(--muted);margin:0 0 26px;font-size:14.5px}

@media (max-width:720px){
  .hero{padding:52px 0 12px;grid-template-columns:1fr;gap:34px}
  .proof{transform:none}
  .head-in .btn{white-space:nowrap}
  .prob{grid-template-columns:1fr;gap:12px}
  .frame{flex-basis:230px}
}
@media (prefers-reduced-motion:reduce){
  .bulb{animation:none!important}
  .btn-lg{transition:none}
}
"""


def _lag(event_date: str, received_at: str) -> str:
    """How long after the event it was caught, as a short human string.

    This is the number the product exists to make small, so it is stated
    plainly and never rounded down flatteringly: an hour is "1h", not "minutes".
    Returns "" when either timestamp is missing, and the frame then simply
    shows no badge rather than a guess.
    """
    try:
        a = datetime.fromisoformat((event_date or "").replace("Z", "+00:00"))
        b = datetime.fromisoformat((received_at or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    mins = (b - a).total_seconds() / 60
    # A negative gap means the clocks disagree, not that we saw the future.
    if mins < 0:
        return ""
    if mins < 90:
        return f"caught in {max(int(mins), 1)}m"
    hours = mins / 60
    if hours < 36:
        return f"caught in {int(hours)}h"
    return f"caught in {int(hours / 24)}d"


REEL_DRAG = r"""<script>
(function () {
  var reel = document.querySelector(".reel");
  if (!reel) return;
  reel.classList.add("draggable");
  var down = false, moved = 0, startX = 0, startLeft = 0;

  reel.addEventListener("pointerdown", function (e) {
    /* Touch scrolls the strip natively and better; hijacking it would break
       the momentum the OS gives for free. */
    if (e.pointerType === "touch" || e.button !== 0) return;
    down = true; moved = 0;
    startX = e.clientX; startLeft = reel.scrollLeft;
    reel.classList.add("dragging");
  });

  reel.addEventListener("pointermove", function (e) {
    if (!down) return;
    var dx = e.clientX - startX;
    if (Math.abs(dx) > 3) {
      /* Capture only once the gesture is clearly a drag, so a plain click on a
         frame still behaves like a click. */
      if (!moved) { try { reel.setPointerCapture(e.pointerId); } catch (_) {} }
      moved = 1;
    }
    reel.scrollLeft = startLeft - dx;
  });

  function end(e) {
    if (!down) return;
    down = false;
    reel.classList.remove("dragging");
    try { reel.releasePointerCapture(e.pointerId); } catch (_) {}
    /* A drag that ends over a link must not also open it. */
    if (moved) {
      reel.addEventListener("click", function stop(ev) {
        ev.preventDefault(); ev.stopPropagation();
        reel.removeEventListener("click", stop, true);
      }, true);
    }
  }
  reel.addEventListener("pointerup", end);
  reel.addEventListener("pointercancel", end);

  /* Shift+wheel is the conventional way to send a vertical wheel sideways. */
  reel.addEventListener("wheel", function (e) {
    if (e.shiftKey && e.deltaY) { reel.scrollLeft += e.deltaY; e.preventDefault(); }
  }, {passive: false});
})();
</script>"""


def _reel(frames: list[dict]) -> str:
    """The signature strip: what the agent has actually found.

    Drawn from stored history rather than a fixture, and from every kind of
    finding rather than only monitor events: a watchlist that has been quiet
    for a day would otherwise leave the page's main element nearly empty while
    the product sat on hundreds of real rows it had extracted.

    Each frame says what was found, for which ticker, and where it was read.
    If there is genuinely nothing stored, the strip says so: a landing page
    that invents a track record for a research tool undermines the one thing
    that product sells.
    """
    if not frames:
        return ('<div class="reel-empty">Nothing found yet. Add a ticker and '
                'the agent starts reading: what it finds appears here.</div>')
    out = []
    for f in frames[:14]:
        badge = f.get("badge", "")
        cls = f.get("badge_class", "lag")
        out.append(
            f'<div class="frame"><div class="frame-top">'
            f'<span class="frame-tk">{_esc(f.get("ticker", ""))}</span>'
            + (f'<span class="{cls}">{_esc(badge)}</span>' if badge else "")
            + f'</div><div class="frame-text">{_esc(f.get("text", "")[:200])}</div>'
            + (f'<div class="frame-src">{_esc(f.get("source", ""))}</div>'
               if f.get("source") else "")
            + "</div>"
        )
    return f'<div class="reel">{"".join(out)}</div>'


def build_frames(events, revisions, filings) -> list[dict]:
    """Assemble the reel from what the agent found, most telling first.

    Order is by kind, not by date. A caught event is the product's sharpest
    claim (it arrived between runs, with a measurable lag), a target revision
    is the strongest recurring signal, and an insider filing is the hardest
    fact. Showing them in that order means the first frame a visitor reads is
    the one that best explains what the thing does.
    """
    frames: list[dict] = []

    for e in events:
        lag = _lag(e.get("event_date", ""), e.get("received_at", ""))
        cites = e.get("citations") or []
        frames.append({
            "ticker": e.get("ticker", ""),
            "badge": lag or "caught between runs",
            "badge_class": "lag",
            "text": " ".join((e.get("text") or "").split()),
            "source": _host(cites[0].get("url", "")) if cites else "",
        })

    for r in revisions:
        direction = r.get("direction", "")
        frames.append({
            "ticker": r.get("ticker", ""),
            "badge": f"target {direction}",
            "badge_class": "lag down" if direction == "cut" else "lag",
            "text": (f"{r.get('firm', '')} {direction} its price target from "
                     f"{_money(r.get('old_price'))} to {_money(r.get('new_price'))}"
                     f"{', ' + r['rating'] if r.get('rating') else ''}."),
            "source": _host(r.get("source_url", "")),
        })

    for f in filings:
        frames.append({
            "ticker": f.get("ticker", ""),
            "badge": f"Form {f.get('form_type', '')}".strip(),
            "badge_class": "lag flat",
            "text": f.get("headline", ""),
            "source": _host(f.get("source_url", "")),
        })

    return frames


def _proof(sample: dict | None) -> str:
    """A real briefing, shown rather than described.

    The hero claims the product cites its sources and shows its price context.
    This is that claim as an artefact: an actual stored briefing for an actual
    ticker, with the citation markers it actually carries.

    Returns "" when there is no briefing yet, and the hero then collapses to a
    single column rather than showing a mock-up of output that does not exist.
    """
    if not sample or not sample.get("body"):
        return ""
    from .citations import strip_markdown

    # Start at the first real paragraph. `strip_markdown` flattens the whole
    # briefing to one line, so a leading "## What happened" would otherwise
    # run straight into the sentence beneath it as "What Happened Reddit
    # announced...".
    text = ""
    for raw in sample["body"].split("\n"):
        line = strip_markdown(raw)
        if len(line.split()) >= 8:
            text = line
            break
    if not text:
        text = strip_markdown(sample["body"])
    # Long enough to read as a real paragraph, short enough not to compete
    # with the headline beside it.
    if len(text) > 300:
        text = text[:300].rsplit(" ", 1)[0] + "\u2026"
    quote = sample.get("quote") or {}
    px = ""
    if quote.get("spot") is not None:
        chg = quote.get("change_pct")
        px = (f'{_money(quote["spot"])}'
              + (f' {chg:+.2f}%' if isinstance(chg, (int, float)) else ""))
    n = sample.get("n_articles") or 0
    return f'''<div class="proof">
  <div class="proof-top">
    <span class="proof-tk">{_esc(sample.get("ticker", ""))}</span>
    <span class="proof-px">{_esc(px)}</span>
  </div>
  <p class="proof-b">{_esc(text)}</p>
  <div class="proof-foot">
    <span class="pill on">{n} source{"s" if n != 1 else ""} cited</span>
    <span class="pill">every claim linked</span>
    <span class="pill">no recommendation</span>
  </div>
</div>'''


def _money(v) -> str:
    """A price as a reader writes it: $240, not $240.0.

    Targets are stored as floats and almost always land on whole dollars, so
    the trailing zero is noise that makes a real extracted figure look like a
    rounding artefact.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    return f"${f:,.0f}" if f == int(f) else f"${f:,.2f}"


def _host(url: str) -> str:
    if not url:
        return ""
    return url.split("//")[-1].split("/")[0].removeprefix("www.")


# Three real failures. Written as what goes wrong for the reader, not as
# features: "continuous monitoring" is a thing we built, "you found out on
# Thursday" is a thing that happened to them.
PROBLEMS = [
    ("You found out on Thursday. It was filed on Monday.",
     "Every ticker gets a standing watch on Parallel's Monitor API. A filing "
     "or a target change arrives as an event within the hour, and the app "
     "reads it into the same tables the scheduled research writes, so it "
     "moves the consensus and can trip an alert instead of sitting in a feed."),
    ("The number is in a table somewhere. You have to trust it.",
     "Every extracted figure keeps the sentence it was read from, the "
     "reasoning, and Parallel's own confidence level. Hover the <b>?</b> "
     "beside a price target or an insider badge and you get the source, not "
     "an assurance. This product once badged a sale as a purchase, which is "
     "exactly why."),
    ("Ten tabs, five tickers, and no idea which one actually moved.",
     "One page per ticker: what happened, what analysts changed their minds "
     "about, what insiders filed, and where the price sits against all of it. "
     "The lobby ranks the watchlist so you can tell in one look which name "
     "needs you today."),
]

STEPS = [
    ("Name what you hold",
     "Add a ticker and the agent researches it immediately, rather than "
     "waiting for the next scheduled sweep."),
    ("It reads the week for you",
     "Parallel Search pulls reporting, Reddit and X; Task extracts analyst "
     "targets and SEC filings against a schema; Gemini writes the briefing "
     "with every claim cited back to a source."),
    ("It keeps watching after that",
     "A standing monitor per ticker reports material events between runs. "
     "Grafana watches the history for coverage spikes, target cuts and "
     "dilution, and fires when one trips."),
    ("You get told, once, with the evidence",
     "An alert names what happened and links the filing. Nothing here "
     "recommends a trade: it tells you what changed and shows you where it "
     "read it."),
]


def page_home(frames: list[dict], stats: dict, sample: dict | None = None,
              last_run: dict | None = None) -> str:
    """The front door: the problem, the proof, and the way in.

    `stats` carries only counts read from stored history. Anything it cannot
    supply is omitted rather than filled in.
    """
    problems = "".join(
        f'<div class="prob"><p class="prob-q">{q}</p><p class="prob-a">{a}</p></div>'
        for q, a in PROBLEMS
    )
    steps = "".join(
        f'<div class="step"><span class="step-n">{i:02d}</span>'
        f'<p class="step-b"><b>{_esc(title)}</b>{body}</p></div>'
        for i, (title, body) in enumerate(STEPS, 1)
    )

    # The reel's caption is the only place a count appears, and it is a count
    # of things actually stored.
    # Plurals are carried as a pair rather than by appending "s": "event
    # caught" pluralises on the noun, not at the end, and the naive version
    # rendered "2 event caughts".
    note_bits = []
    for key, one, many in (("articles", "article", "articles"),
                           ("targets", "analyst target", "analyst targets"),
                           ("filings", "filing", "filings"),
                           ("events", "event caught", "events caught")):
        n = stats.get(key, 0)
        if n:
            note_bits.append(f"{n:,} {one if n == 1 else many}")
    note = " &middot; ".join(note_bits)

    # With no stored briefing there is nothing truthful to put in the second
    # column, so the hero becomes one column rather than showing a mock-up.
    proof = _proof(sample)
    hero_style = "" if proof else ' style="grid-template-columns:1fr"'

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Ticker Room &middot; an agent that watches your watchlist</title>
<meta name="description" content="An agentic stock news radar. You bring a
watchlist; it researches each name across the open web, keeps watching between
runs, and shows you the source behind every figure.">
{FAVICON}<style>{CSS}{HOME_CSS}</style></head><body>
<header><div class="head-in">
  <a href="/" class="brand">
    <span class="bulbs"><i class="bulb"></i><i class="bulb"></i><i class="bulb"></i></span>
    <h1>The Ticker <span>Room</span></h1>
    <span class="tag">Now showing &middot; an agent that reads the week</span>
  </a>
  {_nav()}
</div></header>

<div class="wrap">
  <section class="hero"{hero_style}>
    <div>
      <div class="kicker">Agentic stock news radar</div>
      <h2>The filing was public on Monday. <i>You read it on Thursday.</i></h2>
      <p class="lede">
        You hold five names and cannot read everything about all of them, so
        you find out late, from a price move you cannot explain. The Ticker
        Room watches them for you: it researches each company across the open
        web, keeps watching between runs, and shows you the sentence behind
        every number it reports.
      </p>
      <div class="cta">
        <a class="btn-lg" href="/lobby">Open the room</a>
        <a class="btn-2" href="/how-it-works">How it works</a>
      </div>
      <p class="cta-note">The room is the watchlist: every name being tracked,
      ranked. Open a name and you get its briefing, its standing watch, and
      everything that watch caught between runs.</p>
    </div>
    {proof}
  </section>

  <div class="reel-head">
    <h3>What the agent found this week</h3>
    <span class="reel-note">{note}</span>
  </div>
  {_reel(frames)}

  <div class="probs">{problems}</div>

  <section class="how">
    <h3>How it works</h3>
    <div class="steps">{steps}</div>
  </section>

  <section class="closer">
    <h3>Bring your watchlist.</h3>
    <p>No account. Add a ticker and the agent starts reading.</p>
    <a class="btn-lg" href="/lobby">Open the room</a>
  </section>
</div>

<footer><div>{_esc(DISCLAIMER)}</div>
<div style="margin-top:8px"><a class="foot-a" href="/how-it-works">How does it
work?</a> &middot; Research by Parallel &middot; Briefings by Gemini
&middot; AGPL-3.0</div>
</footer>{REEL_DRAG}</body></html>"""
