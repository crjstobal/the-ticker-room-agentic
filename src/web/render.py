"""HTML rendering. Self-contained, no build step, no external assets."""
from __future__ import annotations

import html
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from src.web.citations import paragraphs as _cite_paragraphs
from src.web.citations import strip_markdown


def adds_open() -> bool:
    """Whether the add form is live, read the same way the server reads it.

    `app.ADDS_OPEN` guards `POST /watchlist/add`; this guards the button that
    posts to it. Read from the environment rather than passed down, so the two
    can never disagree: a live button over a 403 endpoint reads as a broken
    product, and a disabled button over an open endpoint hides a working one.
    """
    return os.getenv("TICKERROOM_ALLOW_ADD") == "1"

CSS = """
:root{
  --bg:#0b0b0f; --panel:#14141c; --panel-2:#1b1b25; --line:#2a2a38;
  --ink:#f2f2f7; --muted:#9a9aad; --amber:#f0b429; --up:#3ddc97; --down:#ff6b6b;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box}
/* The footer used to sit wherever the content ended, so it rode up and down
   the viewport as pages of different lengths loaded: a short page (an empty
   Discover, a one-line error) put it halfway up the screen, a long one pushed
   it off. Making the body a flex column and letting .wrap grow pins it to the
   bottom of the viewport at minimum, and below the content when there is more
   of it, so it stops moving between pages. */
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
  line-height:1.6;-webkit-font-smoothing:antialiased;
  min-height:100vh;min-height:100dvh;display:flex;flex-direction:column}
a{color:inherit;text-decoration:none}
/* `flex:1 0 auto` and not `flex:1`: the shorthand sets flex-basis:0, which
   makes the wrap ignore its own content height and lets a long page collapse
   under the footer. `min-height` gives short pages a floor so the footer does
   not creep up next to a two-line result. */
.wrap{max-width:1180px;margin:0 auto;padding:0 32px 100px;width:100%;
  flex:1 0 auto;min-height:52vh}

/* Positioned so the nav tooltips, which hang below the header, paint over the
   page instead of being covered by the first card. A static header creates no
   stacking context, so content later in the document wins regardless of the
   popup's own z-index. */
/* Sticky: the menu is how you move around, so it should not have to be
   scrolled back to. `position:sticky` and not `fixed` so the header keeps
   taking part in layout and nothing needs a compensating top padding.
   The background must be opaque now that content scrolls under it: the old
   gradient faded to transparent, which was fine for a header that stayed at
   the top of the document and would have let cards show through here. */
header{border-bottom:1px solid var(--line);margin-bottom:56px;
  background:linear-gradient(180deg,#12121a,#0e0e14);
  position:sticky;top:0;z-index:50}
/* Two rows, both centred. The header used to carry four things (brand, nav,
   freshness, a run button) on a two-column grid, and below ~900px they
   collided: the nav, the badge and the button each shrank until the button was
   clipped off-screen. The freshness badge now lives above the watchlist cards,
   which is what it describes, and the run button is gone, so the header is
   only the mark and the menu and both simply centre. */
.head-in{max-width:1180px;margin:0 auto;padding:22px 32px 0;
  display:flex;flex-direction:column;align-items:center;gap:16px}
.head-in .nav{align-self:stretch;border-top:1px solid var(--line);
  margin-top:-2px;padding:2px 0}
/* The mark is [bulbs][wordmark] as ONE block, with the tagline centred under
   that block. Three earlier versions got this wrong. Putting the bulbs inside
   the stacked text block sat them above the wordmark. Pairing the bulbs with
   the whole two-line block sat them beside the gap between the two lines, to
   the left of the tagline as well. The third was a two-column grid with the
   tagline spanning both columns, which is what put the gap back: the tagline
   is WIDER than bulbs+wordmark, so it set the grid's width and the two `auto`
   columns shared out the surplus, pushing the bulbs away from the wordmark.
   `inline-grid` does not save it, because the grid still sizes to its widest
   row.

   So row 1 is its own flex box, sized by its own content and nothing else.
   The column layout below only centres the two blocks on each other; it can
   never stretch row 1, because the tagline is no longer inside it. */
.brand{display:flex;flex-direction:column;align-items:center;gap:2px;
  text-align:center}
.brand-top{display:flex;align-items:center;gap:15px}
.bulbs{display:flex;gap:5px}
.bulb{width:8px;height:8px;border-radius:50%;background:var(--amber);opacity:.85;
  box-shadow:0 0 10px rgba(240,180,41,.7)}
.bulb:nth-child(2){animation:f 2.4s infinite .3s}
.bulb:nth-child(3){animation:f 2.4s infinite .6s}
@keyframes f{0%,100%{opacity:.85}50%{opacity:.3}}
h1{font-size:19px;margin:0;letter-spacing:.16em;text-transform:uppercase;font-weight:600}
h1 span{color:var(--amber)}
.tag{display:block;font-size:11px;color:var(--muted);letter-spacing:.1em;text-transform:uppercase}

.btn{background:var(--amber);color:#1a1200;border:0;padding:11px 22px;border-radius:8px;
  font-weight:650;font-size:13.5px;cursor:pointer;font-family:inherit}
.btn:hover{filter:brightness(1.08)}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--line)}
/* A shut door should look shut. Without this the disabled button kept the
   amber fill and only stopped responding, which reads as a broken click. */
.btn:disabled,.btn-ghost:disabled{background:transparent;color:var(--muted);
  border:1px solid var(--line);cursor:not-allowed;opacity:.55;filter:none}
.btn:disabled:hover,.btn-ghost:disabled:hover{filter:none;color:var(--muted);
  border-color:var(--line)}
form.add input:disabled{opacity:.5;cursor:not-allowed}
.add-note{font-size:12px;color:var(--muted);margin:10px 0 0;max-width:60ch}
.btn-ghost:hover{color:var(--ink);border-color:var(--muted)}

.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:32px 34px;margin-bottom:30px}
.card-top{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;
  flex-wrap:wrap;margin-bottom:26px}
.tk{font-family:var(--mono);font-size:26px;font-weight:700;letter-spacing:.02em}
.tk:hover{color:var(--amber)}
.co{color:var(--muted);font-size:13px;margin-top:2px}
.px{font-family:var(--mono);font-size:26px;text-align:right;font-weight:600}
.chg{font-family:var(--mono);font-size:13px;text-align:right}
.up{color:var(--up)} .down{color:var(--down)}

.body p{margin:0 0 18px}
.body p:last-child{margin-bottom:0}
.body{font-size:15.5px;color:#dcdce6;line-height:1.78}
/* The model writes its briefing in markdown. These are the only tags the
   renderer emits, so this is the whole of its vocabulary. */
.body strong{color:var(--ink);font-weight:600}
.body em{font-style:italic;color:#e6e6ef}
.body .bh{font-size:12px;margin:26px 0 10px;color:var(--muted);
  letter-spacing:.13em;text-transform:uppercase;font-weight:600}
.body .bh:first-child{margin-top:0}
.body ul{margin:0 0 18px;padding-left:20px}
.body li{margin:0 0 7px}
.meta{margin-top:26px;padding-top:18px;border-top:1px solid var(--line);
  font-size:11.5px;color:var(--muted);display:flex;gap:22px;flex-wrap:wrap;
  letter-spacing:.05em;text-transform:uppercase}

.spark{display:flex;align-items:flex-end;gap:4px;height:42px;margin:24px 0 0}
/* `max-width` capped each bar at 34px, so a short history (nine days after a
   credit outage, one day on a fresh ticker) drew a huddle of bars against the
   left edge with the rest of the card empty, which reads as a chart that
   failed to draw rather than one with little to draw. The bars share the full
   width however many there are; the cap only stops a single bar becoming a
   slab. */
.bar{flex:1 1 0;min-width:6px;max-width:96px;background:var(--panel-2);
  border-radius:3px 3px 0 0;min-height:3px;transition:background .15s}
.bar:hover{background:#3a3a4a}
.bar.hot{background:var(--amber)}
.bar.hot:hover{background:#ffc94d}
.spark-label{font-size:11.5px;color:var(--muted);margin-top:12px;
  display:flex;align-items:center;gap:2px}
.spark-label b{color:var(--ink);font-weight:600}
.bar.hot{background:var(--amber)}

table{width:100%;border-collapse:collapse;font-size:14px}
td{padding:15px 0;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.55}
td a:hover{color:var(--amber)}
.date{color:var(--muted);font-family:var(--mono);font-size:12px;
  white-space:nowrap;text-align:right;width:90px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.15em;color:var(--muted);
  margin:52px 0 18px;font-weight:600}
/* Seven metrics is a prime number, so an auto-fit grid always leaves an orphan
   cell with dead space beside it. A fixed four-column grid wraps to 4 + 3 and
   the last cell spans the leftover column, so the block stays a clean
   rectangle. Rounding is applied per corner cell rather than per first/last
   child, which on a wrapped grid would round a cell in the middle of a row. */
/* Bento, not a fixed grid. The number of stats varies (a ticker with no
   52-week history has fewer), and a fixed column count either leaves a hole or
   forces some cell to span it. Flexbox is the right tool here rather than
   grid: cells are given a sensible basis and allowed to grow, so the last row
   absorbs whatever space is left instead of ending in dead panel. No cell has
   to know how many siblings it has.

   `dense` grid was tried first and does not solve it: backfilling only helps
   when items differ in size, and these are all one cell wide. */
.stats{display:flex;flex-wrap:wrap;position:relative;
  gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;
  margin-bottom:30px;overflow:visible}
.stat{background:var(--panel);padding:19px 20px;position:relative;
  flex:1 1 190px;min-width:0}

/* Rounding follows the visual corners rather than the DOM order, which on a
   reflowing grid are not the same cells. `overflow:hidden` on the grid would do
   it in one line and clip every tooltip, a bug this file already fixed once. */
.stats > :first-child{border-top-left-radius:13px}
.stats > :last-child{border-bottom-right-radius:13px}

.stat b{display:block;font-family:var(--mono);font-size:17px;margin-top:4px;
  font-weight:600;overflow-wrap:anywhere}
.stat i{font-style:normal;font-size:10.5px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.08em;
  display:flex;align-items:center;min-width:0}
/* Only the label text is held on one line, never the popup nested inside it:
   `white-space:nowrap` on `.stat i` was inherited by `.hint-pop`, so the
   tooltip's own text refused to wrap and ran straight out of its box. */
.stat i > span:first-of-type,.stat-label{white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.hint-pop{white-space:normal}
form.add{display:flex;gap:11px;flex-wrap:wrap;margin-bottom:20px}
input{background:var(--panel);border:1px solid var(--line);color:var(--ink);
  padding:12px 15px;border-radius:8px;font-family:inherit;font-size:14px}
input:focus{outline:0;border-color:var(--amber)}
/* Lobby rows: a summary, not a second copy of the ticker page. */
/* --- the lobby cards, as cinema tickets ---------------------------------
   The list of what is showing is a row of ticket stubs: a stub down the left
   edge on a warmer ground, a dashed amber perforation, and two notches
   punched through the card where the stub would tear off.

   The notches are cut with `mask`, not painted. Background layers stack, they
   do not subtract, so a "hole" drawn as a background is really a circle of
   some colour sitting on top: it has to match the page exactly, it stops
   working the moment the card sits on anything else, and anything painted
   below it (the stub tint, the perforation dashes) still shows through and
   fills the hole back in. A mask removes the pixels, so what shows is the
   page itself, whatever it is.

   Everything inside the notch must be cleared for the effect to read: the
   perforation stops short of both notches, and the mask cuts the stub tint
   along with the rest of the card. */
.row{position:relative;display:block;border-radius:12px;
  padding:22px 26px 22px 52px;margin-bottom:14px;
  transition:transform .15s,box-shadow .15s,filter .15s;
  background:
    linear-gradient(90deg,rgba(240,180,41,.09) 0 38px,transparent 38px),
    var(--panel);
  /* A white field with two transparent circles punched out of it: white keeps
     the pixel, transparent drops it. The circles are centred on the tear line
     at the very top and bottom edges, so each shows as a half-round bite. */
  --notch:radial-gradient(circle at 38px 0,transparent 10px,#fff 10.5px),
          radial-gradient(circle at 38px 100%,transparent 10px,#fff 10.5px);
  -webkit-mask:var(--notch);mask:var(--notch);
  -webkit-mask-composite:source-in;mask-composite:intersect}
/* The border is drawn as an inset ring rather than a real border: a border is
   painted outside the padding box and the mask would cut it into two arcs
   floating either side of each notch. */
.row::after{content:"";position:absolute;inset:0;border-radius:12px;
  box-shadow:inset 0 0 0 1px var(--line);pointer-events:none}
/* The perforation, clearing both notches so nothing crosses the holes. */
.row::before{content:"";position:absolute;left:38px;top:16px;bottom:16px;
  border-left:1px dashed rgba(240,180,41,.5)}
.row:hover{transform:translateY(-2px);box-shadow:0 10px 26px rgba(0,0,0,.5)}
.row:hover::after{box-shadow:inset 0 0 0 1px var(--amber)}
.row:hover::before{border-left-color:var(--amber)}
@media (prefers-reduced-motion:reduce){
  .row{transition:none}
  .row:hover{transform:none}
}
/* The stub narrows before the company name would be squeezed off its line. */
@media (max-width:560px){
  .row{padding:20px 18px 20px 38px;
    background:
      linear-gradient(90deg,rgba(240,180,41,.09) 0 26px,transparent 26px),
      var(--panel);
    --notch:radial-gradient(circle at 26px 0,transparent 9px,#fff 9.5px),
            radial-gradient(circle at 26px 100%,transparent 9px,#fff 9.5px)}
  .row::before{left:26px;top:14px;bottom:14px}
}
.row-main{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
.row-id{display:flex;align-items:baseline;gap:11px;flex:1;min-width:180px}
.row-id .tk{font-size:21px}
.row-id .co{font-size:12.5px;color:var(--muted)}
.row-flags{display:flex;gap:7px;flex-wrap:wrap}
.row-flag,.row-sent{font-size:10px;text-transform:uppercase;letter-spacing:.08em;
  padding:3px 9px;border-radius:4px;border:1px solid currentColor;font-weight:600}
.row-flag.down,.row-sent.bearish{color:var(--down)}
.row-flag.up,.row-sent.bullish{color:var(--up)}
.row-flag.amber{color:var(--amber)}
.row-sent.mixed{color:var(--muted)}
.row-line{font-size:14px;color:#c9c9d6;margin-top:14px;line-height:1.65}
.row-meta{font-size:11px;color:var(--muted);margin-top:12px;
  text-transform:uppercase;letter-spacing:.05em}
.row .px{font-size:21px} .row .chg{font-size:12px}

.empty{color:var(--muted);text-align:center;padding:60px 20px;
  border:1px dashed var(--line);border-radius:12px}

/* Citations: superscript link with a hover preview of the source. */
/* A grouped marker ("[2, 6, 8]") is several links side by side. The commas
   between them are body-size text sitting next to superscripts, which reads
   as a list dropped into the sentence, so the whole group is lifted and
   shrunk together and the numbers keep their own baseline. */
.cites{font-size:10px;vertical-align:super;color:var(--muted);white-space:nowrap}
.cites .cite sup{font-size:inherit;vertical-align:baseline}
.cite{position:relative;color:var(--amber);font-weight:600;text-decoration:none}
.cite sup{font-size:10px;padding:0 1px}
.cite:hover{text-decoration:underline}
/* width, not min-width: the popup sits inside a .cites group whose
   white-space:nowrap is inherited, so without an explicit override the title
   and excerpt refuse to wrap and the box grows past its own 310px, spilling
   out of the card on both sides. overflow-wrap breaks the long unspaced runs
   that scraped excerpts are full of. */
.cite-pop{position:absolute;bottom:calc(100% + 9px);left:50%;transform:translateX(-50%);
  width:310px;max-width:calc(100vw - 24px);background:#0f0f16;
  border:1px solid var(--line);border-radius:9px;
  padding:12px 14px;box-shadow:0 12px 34px rgba(0,0,0,.6);opacity:0;visibility:hidden;
  transition:opacity .13s,visibility .13s;z-index:40;pointer-events:none;
  font-weight:400;line-height:1.5;text-align:left;
  white-space:normal;overflow-wrap:anywhere}
.cite:hover .cite-pop{opacity:1;visibility:visible}
.cite-pop b{display:block;color:var(--ink);font-size:12.5px;margin-bottom:5px;font-weight:600}
.cite-pop i{display:block;color:var(--amber);font-size:10.5px;font-style:normal;
  letter-spacing:.05em;margin-bottom:6px}
.cite-pop em{display:block;color:var(--muted);font-size:11.5px;font-style:normal}

/* Explainer chip: hover to learn what a panel will show once history builds. */
.hint{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;
  border-radius:50%;border:1px solid var(--line);color:var(--muted);font-size:10px;
  cursor:help;position:relative;margin-left:7px;vertical-align:middle;font-weight:600}
.hint:hover{color:var(--amber);border-color:var(--amber)}
.hint-pop{position:absolute;bottom:calc(100% + 10px);left:50%;transform:translateX(-50%);
  width:min(290px,78vw);background:#0f0f16;border:1px solid var(--line);border-radius:9px;
  padding:13px 15px;box-shadow:0 12px 34px rgba(0,0,0,.6);opacity:0;visibility:hidden;
  transition:opacity .13s,visibility .13s;z-index:40;pointer-events:none;
  color:var(--muted);font-size:11.5px;line-height:1.65;text-align:left;
  font-weight:400;text-transform:none;letter-spacing:0}
.hint:hover .hint-pop{opacity:1;visibility:visible}
/* Near the edges the popup would be clipped, so it anchors inward instead. */
/* On a four-column grid the popup is clipped at either edge of every row, so
   it anchors by column position rather than by position in the whole list. */
.stat:nth-child(4n+1) .hint-pop{left:0;transform:none}
.stat:nth-child(4n) .hint-pop{left:auto;right:0;transform:none}
.fil-table th:last-child .hint-pop{left:auto;right:0;transform:none}
/* The filings table lives inside .tbl-scroll, and overflow-x:auto makes that
   box a scroll container on BOTH axes: a popup hanging above the header row is
   cut off at the top edge of the box, not painted over it. Header hints drop
   downward instead, where the rows give them room inside the same box. The
   first column's popup also has to anchor left: `Filed` is now the leftmost
   header and a centred popup would run off the left edge. */
.fil-head th .hint-pop{bottom:auto;top:calc(100% + 4px)}
.fil-table th:first-child .hint-pop{left:0;right:auto;transform:none}
.hint-pop b{color:var(--ink);display:block;margin-bottom:5px}
.demo-bars{display:flex;align-items:flex-end;gap:2px;height:26px;margin:8px 0 6px}
.demo-bars div{flex:1;background:var(--panel-2);border-radius:2px 2px 0 0}
.demo-bars div.hot{background:var(--amber)}

/* The row above the cards: the order control on the left, the freshness badge
   on the right. `wrap-reverse` so that when it does break, the badge goes
   above the chips rather than the chips being pushed away from the list they
   act on. */
/* The cards' own box, so reordering them in the browser cannot move them
   past the "Add to watchlist" form that follows. */
.rows{display:block}
.list-head{display:flex;justify-content:space-between;align-items:center;
  gap:12px;margin:0 0 14px;min-height:18px;flex-wrap:wrap-reverse}
.sorts{display:flex;align-items:center;gap:3px;flex-wrap:wrap}
.sorts-l{font-size:10px;text-transform:uppercase;letter-spacing:.12em;
  color:var(--muted);margin-right:7px}
.sorts a{position:relative;font-size:11.5px;color:var(--muted);
  letter-spacing:.04em;text-decoration:none;padding:5px 10px;border-radius:6px;
  border:1px solid transparent}
.sorts a:hover{color:var(--ink);background:rgba(240,180,41,.07)}
.sorts a.on{color:var(--amber);border-color:rgba(240,180,41,.35);
  background:rgba(240,180,41,.09)}
/* Four chips plus the label do not fit one phone line, and wrapping left a
   single chip stranded on a second row. Tightened so all four sit together,
   and the "Sort" label goes: the chips are self-evidently a choice. */
@media (max-width:560px){
  .sorts{gap:2px}
  .sorts-l{display:none}
  .sorts a{padding:5px 8px;font-size:11px}
}
.updated{font-size:11px;color:var(--muted);letter-spacing:.05em}
.updated b{color:var(--ink);font-weight:600}
/* While a run is in flight the badge becomes a live indicator. The dot is a
   bare <b> so the markup stays one element either way. */
.updated.running{color:var(--amber);display:inline-flex;align-items:center;gap:7px}
.updated.running b.live{width:7px;height:7px;border-radius:50%;
  background:var(--amber);box-shadow:0 0 8px rgba(240,180,41,.8);
  animation:pulse 1.4s ease-in-out infinite;flex:0 0 auto}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.run-since{color:var(--muted)}
@media (max-width:520px){.run-since{display:none}}
.stale{color:var(--amber)}
/* Out of credit is not a shade of stale: nothing is being refreshed at all,
   so it gets the alarm colour rather than the warning one. */
/* The second opinion is deliberately quieter than the agent's own answer:
   dashed edge, no fill. It is corroboration, not a rival headline. */
.card.so{border-style:dashed}
.so-cites{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px;
  padding-top:14px;border-top:1px solid var(--line)}
.so-cite{font-family:var(--mono);font-size:11px;color:var(--muted);
  background:var(--panel-2);border:1px solid var(--line);border-radius:5px;
  padding:3px 8px}
.so-cite:hover{color:var(--ink);border-color:var(--muted)}
.updated.nocredit{color:var(--down)}
.updated.nocredit b{color:var(--down);font-weight:600}
footer{border-top:1px solid var(--line);margin-top:60px;padding:26px 32px;
  color:var(--muted);font-size:11.5px;text-align:center;line-height:1.8;
  flex:0 0 auto}
/* The footer now carries the Settings link, so it needs real spacing between
   its rows rather than the single inline margin it had. */
/* Seven links, not two. The gap came down and a divider marks where the
   product links end and the legal boilerplate begins: without it the row reads
   as one undifferentiated list and "Settings" sits next to "Privacy" as though
   they were the same kind of thing. */
.foot-nav{display:flex;gap:8px 14px;flex-wrap:wrap;justify-content:center;
  margin-top:12px;align-items:center}
.foot-a{color:var(--amber);text-decoration:underline;text-underline-offset:2px}
.foot-a:hover{filter:brightness(1.15)}
.foot-sep{color:var(--line);user-select:none}
@media (max-width:600px){.foot-nav{gap:7px 12px}.foot-sep{display:none}}
/* Analyst price targets */
.tgt-head{display:flex;justify-content:space-between;align-items:baseline;
  gap:20px;flex-wrap:wrap;margin-bottom:34px}
.tgt-avg{font-family:var(--mono);font-size:30px;font-weight:700;color:var(--ink)}
.tgt-avg-note{font-size:12.5px;color:var(--muted);margin-left:10px}
.tgt-gap{font-family:var(--mono);font-size:19px;font-weight:700}
.tgt-gap-note{font-size:12px;color:var(--muted);margin-left:9px}
.tgt-scale{position:relative;height:3px;background:var(--panel-2);border-radius:2px;
  margin:0 0 62px}
.tgt-dot{position:absolute;top:-4px;width:11px;height:11px;border-radius:50%;
  background:var(--amber);opacity:.62;transform:translateX(-50%);cursor:help;
  border:2px solid var(--panel)}
.tgt-dot:hover{opacity:1;transform:translateX(-50%) scale(1.35);z-index:41}
/* A firm that just moved its own target is coloured by the direction it moved,
   so the scale shows where the revisions sit, not only where the levels do. */
.tgt-dot.raised{background:var(--up)} .tgt-dot.cut{background:var(--down)}
/* The popup hangs off the dot, which is the positioned parent. It drops BELOW
   the rail: the rail sits near the top of the card and a popup above it ran off
   the top of the section, which is the same clipping the filings header had. */
.tgt-pop{opacity:0;visibility:hidden;bottom:auto;top:calc(100% + 10px)}
.tgt-dot:hover .tgt-pop,.tgt-dot:focus-visible .tgt-pop{opacity:1;visibility:visible}
/* The 10px between the dot and its popup was dead space: moving the pointer
   down to read the card left the dot, hover ended, and the card vanished
   mid-reach unless you crossed the gap fast enough. The dot grows an invisible
   apron over that gap so the pointer never leaves the hover region on the way
   down. It is ::before on the dot rather than padding on the popup because the
   popup is only rendered on hover, so it cannot hold a hover it has to be
   reached to start. */
.tgt-dot::before{content:"";position:absolute;left:50%;transform:translateX(-50%);
  top:100%;width:26px;height:14px}
/* The popup is pointer-events:none so it never blocks the dot next to it, but
   the source link inside has to be clickable, so it opts back in. */
.tgt-pop{pointer-events:none}
.tgt-dot:hover .tgt-pop{pointer-events:auto}
/* Once the pointer is on the card, the card itself keeps it open: without this
   the dot loses hover as soon as you move onto the popup and the link inside
   can never be clicked. */
.tgt-pop:hover{opacity:1;visibility:visible;pointer-events:auto}
.tgt-pop em{display:block;font-style:normal;color:#c8c8d6;font-size:12px;
  margin-bottom:3px}
.tgt-pop em.up{color:var(--up)} .tgt-pop em.down{color:var(--down)}
.tgt-pop i{display:block;font-style:normal;font-family:var(--mono);font-size:10.5px;
  color:var(--muted);margin-top:5px}
.tgt-pop a{display:inline-block;margin-top:8px;color:var(--amber);font-size:11px;
  text-decoration:underline;text-underline-offset:2px}
/* The revision that rides in the targets row. */
.tgt-rev{white-space:nowrap}
.rev-pct{font-family:var(--mono);font-weight:700}
.rev-pct.up{color:var(--up)} .rev-pct.down{color:var(--down)}
/* Without widths the four short columns share the leftover space equally and
   the numbers drift into the middle of the row, far from their headers. Every
   column sizes to its content and the firm name absorbs the slack, but capped:
   left to `auto` it took over half the row for a 15-character name and opened
   a gulf between the firm and its own numbers. */
.tgt-list td:first-child,.tgt-list th:first-child{width:34%;padding-right:18px}
.tgt-list td:nth-child(2),.tgt-list th:nth-child(2){width:1%;padding-right:26px;
  white-space:nowrap}
.tgt-list td:nth-child(3),.tgt-list th:nth-child(3){width:1%;padding-right:26px;
  white-space:nowrap}
.tgt-list td:nth-child(4),.tgt-list th:nth-child(4){width:1%;padding-right:26px}
/* The date is last and right-aligned, so it can hold the remaining slack:
   the gap then falls between the revision and the date rather than between
   the firm and its rating. */
.tgt-list td:last-child,.tgt-list th:last-child{width:auto}
/* `.tgt-price` is right-aligned, which under its own left-aligned header reads
   as a column that does not belong to it. Both align left here. */
.tgt-list .tgt-price{text-align:left}
.tgt-list th{text-align:left}
.tgt-list th:last-child,.tgt-list td.date{text-align:right}
.tgt-more[hidden]{display:none}
.tgt-spot{position:absolute;top:16px;transform:translateX(-50%);text-align:center;
  white-space:nowrap}
.tgt-spot b{display:block;font-family:var(--mono);font-size:12.5px;color:var(--ink)}
.tgt-spot i{font-style:normal;font-size:9.5px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.09em}
.tgt-spot::before{content:"";position:absolute;top:-14px;left:50%;width:2px;
  height:12px;background:var(--ink);transform:translateX(-50%)}
.tgt-end{position:absolute;top:12px;font-family:var(--mono);font-size:10.5px;
  color:var(--muted)}
.tgt-end.left{left:0} .tgt-end.right{right:0}
/* Set by `_targets_block` when the spot marker would print on top of
   the end label. The marker states the price itself, so the label is
   the one that goes. */
.tgt-spot.hide-left ~ .tgt-end.left,
.tgt-spot.hide-right ~ .tgt-end.right{display:none}
.tgt-table{width:100%;border-collapse:collapse;font-size:13.5px}
.tgt-table td{padding:12px 0;border-bottom:1px solid var(--line);vertical-align:top}
.fil-head th{font-size:10px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--muted);font-weight:600;text-align:left;padding:0 0 12px;
  border-bottom:1px solid var(--line);white-space:nowrap}
/* Column 4 is the badge: it must not wrap, and the number beside it needs
   air. Keyed to position, so it moves whenever the columns are reordered. */
.fil-table td:nth-child(4){white-space:nowrap;padding-right:12px}
/* The date leads, so it needs its own gutter: without a width the table
   shrink-wraps it against the form type ("2026-08-27" and "4" touching)
   and a long form type ("S-3/424B5") wraps under the date instead. */
/* `.date` is right-aligned and 90px wide because everywhere else it is the
   last column. Here it leads, so it aligns left and sizes to its content. */
.fil-table td:first-child,.fil-table th:first-child{padding-right:22px;
  white-space:nowrap;width:1%;text-align:left}
.fil-table td:nth-child(2),.fil-table th:nth-child(2){padding-right:18px;
  white-space:nowrap;width:1%}
/* The scroller is pinned to the width of its container, not its content:
   without an explicit width a block box shrink-wraps nothing and the table
   inside simply grows the page instead of scrolling. The table keeps
   width:100% so it fills that box and only its nowrap columns force the
   scroll. */
.tbl-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;
  width:100%;max-width:100%}
.tbl-scroll > table{width:100%}
.tgt-analyst{display:block;font-size:11px;color:var(--muted);margin-top:3px}
.tgt-rating{font-size:11.5px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.06em}
.tgt-price{font-family:var(--mono);text-align:right;font-weight:600;color:var(--amber)}
.tgt-price.up{color:var(--up)} .tgt-price.down{color:var(--down)}
.rev-move{font-family:var(--mono);font-size:13px;color:var(--muted)}
.rev-old{text-decoration:line-through;opacity:.65}
.rev-new{font-weight:600}
.rev-new.up{color:var(--up)} .rev-new.down{color:var(--down)}

/* SEC filings */
.fil-form b{font-family:var(--mono);font-size:12.5px;color:var(--ink)}
.fil-mean{display:block;font-size:10px;color:var(--muted);margin-top:3px;
  text-transform:uppercase;letter-spacing:.06em;max-width:120px;line-height:1.4}
.fil-who{display:block;font-size:11.5px;color:var(--muted);margin-top:4px}
.src-link{border-bottom:1px solid transparent}
.src-link:hover{color:var(--amber);border-bottom-color:var(--amber)}
.stat i .hint{margin-left:5px;width:13px;height:13px;font-size:9px}
.fil-badge{display:inline-block;font-size:9.5px;text-transform:uppercase;
  letter-spacing:.09em;padding:2px 8px;border-radius:4px;margin-top:6px;
  border:1px solid currentColor;font-weight:600}
.fil-badge.up{color:var(--up)} .fil-badge.down{color:var(--down)}
.fil-badge.amber{color:var(--amber)}
.fil-amount{font-family:var(--mono);text-align:right;font-size:13px;
  white-space:nowrap;color:var(--muted)}
.fil-amount.up{color:var(--up)} .fil-amount.down{color:var(--down)}
.fil-show{margin-top:14px;background:none;border:1px solid var(--line);
  color:var(--muted);font:inherit;font-size:11.5px;letter-spacing:.06em;
  text-transform:uppercase;padding:9px 16px;border-radius:7px;cursor:pointer}
.fil-show:hover{color:var(--amber);border-color:var(--amber)}
/* `hidden` is only display:none in the browser sheet, so any display rule on
   the class would win over it. Same trap as the ticker input and .ask-working. */
.fil-show[hidden]{display:none !important}

/* The "show more" control, centred under a fade. A left-aligned button under a
   full-width table reads as a stray form control; centred beneath a fade it
   reads as the bottom edge of something that continues, which is what it is.
   Same shape as the briefing's control, because it is the same gesture.

   The wrapper is the thing shown and hidden, so the fade never outlives the
   button. `position:relative` on it and the fade pulled upward with a negative
   margin, so the tint lies over the last rows of the table without being a
   child of the table (a row-level tint would have to know which row is last,
   and that changes when the rows are revealed). */
.more-wrap{position:relative;display:flex;justify-content:center;
  margin-top:-46px;padding-top:46px}
.more-wrap[hidden]{display:none !important}
.more-fade{position:absolute;left:0;right:0;top:0;height:46px;
  background:linear-gradient(180deg,transparent,var(--panel));
  pointer-events:none}
/* The button paints over the fade rather than through it. */
.more-wrap .fil-show{position:relative;z-index:1;background:var(--panel)}
/* Only the narrow-screen block above reveals this: on a wide screen the Form
   column already carries the form type and printing it twice would be noise. */
.fil-form-sm{display:none}

/* Alert strip: what would have woken you */
/* Same bento rule as the stats: the number of alerts is whatever the data
   happened to produce, so the chips grow to fill the row rather than ending in
   a ragged tail of empty page. */
.alert-strip{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 30px}
/* The direction used to be a 3px stripe down the left edge. A stripe that thin
   is read one chip at a time: to see that four of five chips are bad news you
   had to look at each in turn. A whole-chip wash is read at a glance across
   the row, which is the only job this strip has. The tint is kept very low
   (7% over the panel) so the chips still sit on the page rather than shouting;
   the badge keeps the full-strength colour so the pairing is unambiguous for
   anyone who cannot separate the two washes. */
.alert-chip{display:flex;flex-direction:column;gap:3px;padding:12px 15px;
  background:var(--panel);border:1px solid var(--line);border-radius:9px;
  flex:1 1 240px;min-width:0}
.alert-chip span{overflow-wrap:anywhere}
.alert-chip b{font-size:10px;text-transform:uppercase;letter-spacing:.09em}
.alert-chip span{font-size:12.5px;color:var(--muted)}
.alert-chip.up{background:color-mix(in srgb,var(--up) 7%,var(--panel));
  border-color:color-mix(in srgb,var(--up) 22%,var(--line))}
.alert-chip.up b{color:var(--up)}
.alert-chip.down{background:color-mix(in srgb,var(--down) 7%,var(--panel));
  border-color:color-mix(in srgb,var(--down) 22%,var(--line))}
.alert-chip.down b{color:var(--down)}
.alert-chip.amber{background:color-mix(in srgb,var(--amber) 7%,var(--panel));
  border-color:color-mix(in srgb,var(--amber) 22%,var(--line))}
.alert-chip.amber b{color:var(--amber)}

/* --- quick overview + briefing teaser --------------------------------- */
/* The overview card holds the alert chips and the stats grid, both of which
   bring their own panel background and border. Nesting those inside another
   panel would draw a box inside a box, so the outer card is padding and a
   border only, and its children keep their own surfaces. */
.card.overview{padding:0;background:transparent;border:0;margin-bottom:30px;
  min-width:0}
.card.overview .alert-strip{margin-bottom:14px}
.card.overview .stats{margin-bottom:0}
.pending-wrap{background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:32px 34px}

/* The teaser is the full briefing under a height clip, not a shortened copy:
   the text below the fold is still in the DOM for Find-in-page, for a screen
   reader and for print. `max-height` and not `display` so lifting the clip is
   one class toggle and the fade can sit over the cut. */
.teaser{position:relative;padding-bottom:22px}
.teaser-body{max-height:190px;overflow:hidden}
.teaser.open .teaser-body{max-height:none}
/* The fade covers the cut edge so the last visible line is not sliced through
   mid-letter, which reads as a rendering fault rather than as more to come.
   It ends in the card's own colour, so it has to move with the card. */
.teaser-fade{position:absolute;left:1px;right:1px;bottom:52px;height:96px;
  background:linear-gradient(180deg,transparent,var(--panel));
  pointer-events:none;border-radius:0 0 14px 14px}
.teaser.open .teaser-fade{display:none}
/* The control is a `.fil-show`, the same button the filings and targets tables
   use to reveal their hidden rows: all three do the identical job of "there is
   more of this than is on screen", and three different-looking controls for
   one behaviour is what made the page feel assembled rather than designed.
   Only the placement differs, since this one sits under a fade rather than
   under a table. */
/* `background:none` is right for a button under a table, but here the clipped
   text fades directly behind it, so the label would sit on top of half a
   sentence. It needs the card's own colour under it. */
.teaser-more{position:relative;z-index:1;display:block;margin:18px auto 0;
  background:var(--panel)}
/* `display:block` above beats the browser's own `[hidden]{display:none}`, so
   the script hiding the control would have had no effect. Same trap as the
   ask banner and the ticker input. */
.teaser-more[hidden],.teaser-fade[hidden]{display:none!important}

/* Section headings carry a `?`. The heading is uppercase with wide tracking,
   neither of which should reach the explainer inside it: `.hint-pop` already
   resets both, and this keeps the chip itself from inheriting the baseline
   shift the tracking would otherwise give it. */
.sec-h2{display:flex;align-items:center}
.sec-h2 .hint{flex:none}

.back{color:var(--muted);font-size:12px;letter-spacing:.08em;text-transform:uppercase}
.back:hover{color:var(--amber)}

/* Reddit sentiment */
.sent{margin:28px 0 0;padding-top:24px;border-top:1px solid var(--line)}
.sent-head{display:flex;align-items:center;gap:8px;margin-bottom:16px}
.sent-verdict{display:flex;align-items:baseline;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.sent-score{font-family:var(--mono);font-size:30px;font-weight:700;line-height:1}
.sent-word{font-size:14px;font-weight:650;text-transform:uppercase;letter-spacing:.08em}
.sent-gloss{font-size:12.5px;color:var(--muted)}
.gauge-tick{position:absolute;top:-19px;font-size:9.5px;color:var(--muted);
  font-family:var(--mono)}
.themes-label{font-size:10.5px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.1em;margin-top:22px}
.sent-note{font-size:12.5px;color:var(--muted);margin-top:12px;line-height:1.6}
.sent-note b{color:var(--ink);font-weight:600}
.sent-summary{font-size:14px;color:#c9c9d6;margin-top:16px;line-height:1.7}
.sub-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.sub-chip{font-size:11px;color:var(--muted);background:var(--panel-2);
  border:1px solid var(--line);padding:5px 11px;border-radius:6px;
  display:inline-flex;gap:7px;align-items:center}
.sub-chip b{color:var(--amber);font-weight:600}
.gauge-end{position:absolute;top:12px;font-size:9.5px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.08em}
.gauge-end.left{left:0} .gauge-end.right{right:0}
.gauge{position:relative;width:100%;height:7px;border-radius:4px;margin:26px 0 24px;
  background:linear-gradient(90deg,#ff6b6b,#3a3a48 45%,#3a3a48 55%,#3ddc97)}
.gauge i{position:absolute;top:-4px;width:3px;height:14px;background:var(--ink);
  border-radius:2px;transform:translateX(-50%);box-shadow:0 0 7px rgba(255,255,255,.55)}
.sent-lab{font-size:11px;text-transform:uppercase;letter-spacing:.09em;font-weight:650}
.bullish{color:var(--up)} .bearish{color:var(--down)}
.mixed,.quiet{color:var(--muted)}
.themes{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.theme{font-size:11px;color:var(--muted);border:1px solid var(--line);
  padding:5px 12px;border-radius:20px;line-height:1.4}

/* --- contents rail ---------------------------------------------------- */
/* A ticker page is a dozen blocks deep, so it needs a way to jump. Grid and
   not float: the rail must be able to stick without the main column flowing
   around it. */
.tk-body{display:grid;grid-template-columns:184px minmax(0,1fr);gap:44px;
  align-items:start}
/* minmax(0,1fr) above and this here for the same reason: a grid item's default
   min-width is auto, so a wide table inside would push the column wider than
   the grid instead of scrolling in its own box. */
.tk-main{min-width:0}
/* h2 carries 52px of top margin so consecutive sections breathe, but the very
   first heading in the column has nothing above it to be separated from: that
   margin is what dropped the main column half a section below the rail, which
   starts at the top of the grid row. Both columns now begin on the same line.

   The heading is wrapped in a <section>, so `.tk-main > h2` never matched it:
   the selector has to reach through the section. Measured before and after,
   the rail and the first heading now start within a pixel of each other. */
.tk-main > section:first-child > h2:first-child{margin-top:0}
/* The offsets below are all measured from the sticky header, which is two
   rows tall (mark, then menu) rather than one: pinning the rail at a guessed
   96px slid it under the header instead of below it. The height is published
   as a variable so the rail, the scroll-margin and the observer's top margin
   all move together if the header ever changes shape. */
.tk-body{--head-h:150px}
.toc{position:sticky;top:calc(var(--head-h) + 14px);display:flex;
  flex-direction:column;gap:1px;font-size:12px;
  max-height:calc(100dvh - var(--head-h) - 40px);overflow-y:auto}
.toc-lab{font-family:var(--mono);font-size:10.5px;color:var(--muted);
  letter-spacing:.12em;text-transform:uppercase;padding:0 10px 8px;
  border-bottom:1px solid var(--line);margin-bottom:8px}
.toc a{color:var(--muted);padding:7px 10px;border-radius:6px;line-height:1.35;
  transition:color .13s,background .13s}
.toc a:hover{color:var(--ink);background:var(--panel)}
/* Same reasoning as the alert chips: the marker was a 2px amber stripe on the
   left edge, which is a thing you have to look for. A soft amber wash across
   the whole entry is what the eye lands on when it comes back to the rail. */
.toc a.on{color:var(--amber);
  background:color-mix(in srgb,var(--amber) 11%,transparent)}
/* "Back to top" as a floating control, not a rail entry. In the rail it was
   only reachable once you had found the rail, and it vanished entirely at the
   width where the rail is hidden, which is the narrow screen where a page this
   long needs it most. Fixed to the viewport corner it is in the same place at
   every scroll depth and on every width.

   It appears only once there is something to go back to: `.on` is added by the
   script past a screenful of scrolling. Opacity and not `display`, so the
   arrival is a fade rather than a jump, and `pointer-events` so the invisible
   button cannot be clicked. */
.to-top{position:fixed;right:24px;bottom:24px;z-index:60;
  width:44px;height:44px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  background:var(--panel-2);border:1px solid var(--line);color:var(--muted);
  font-size:16px;line-height:1;box-shadow:0 6px 20px rgba(0,0,0,.45);
  opacity:0;pointer-events:none;transition:opacity .18s,color .13s,border-color .13s}
.to-top.on{opacity:1;pointer-events:auto}
.to-top:hover{color:var(--amber);border-color:var(--amber)}
/* No no-JS rule needed: it starts transparent and unclickable, so a browser
   that never runs the reveal simply never shows it. */
/* The header is sticky, so a fragment jump would land the heading underneath
   it. scroll-margin pushes the landing point clear. */
.tk-main section{scroll-margin-top:calc(var(--head-h) + 16px)}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
/* Below the breakpoint the rail would eat a third of a phone screen, so it
   goes away entirely: the page is short enough to scroll and the anchors are
   still reachable from the top of the document. */
@media (max-width:900px){
  .tk-body{display:block}
  .toc{display:none}
}

/* --- social & coverage ------------------------------------------------ */
/* Two halves of one section, each labelled: merged without these the block
   read as one long unbroken list and the chart looked like part of the
   sentiment reading rather than its own measure. */
.sub-head{font-size:10.5px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.11em;font-weight:650;display:flex;align-items:center;gap:2px}
/* A rule for any sub-head that follows another block inside the same card,
   separating the two halves of Social & coverage and the three parts of
   Alerts. Without the divider the parts run together and the card reads as one
   long list rather than as named sections of one answer. */
.cov-head,.wat-head{margin-top:38px;padding-top:26px;
  border-top:1px solid var(--line)}
/* The first .sent inside the card already draws its own top rule, which would
   double up with the sub-head directly above it. */
.sub-head + .sent{margin-top:14px;padding-top:0;border-top:0}

/* The posts a sentiment score was read from. */
.posts-label{font-size:10.5px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.1em;margin-top:26px}
.posts{display:flex;flex-direction:column;gap:1px;margin-top:10px}
.post{display:flex;gap:11px;align-items:baseline;padding:9px 10px;
  border-radius:7px;font-size:13px;color:#c9c9d6;transition:background .13s}
.post:hover{background:var(--panel-2);color:var(--ink)}
.post-where{font-family:var(--mono);font-size:10.5px;flex:0 0 auto;
  min-width:96px;color:var(--muted)}
.post-where.x{color:#8ab4f8} .post-where.rd{color:var(--amber)}
/* The title is one line: these are up to fourteen rows, and a wrapped one
   turns the list into a wall that hides how many posts there were. */
.post-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  line-height:1.5}
.posts-more,.posts-none{font-size:12px;color:var(--muted);margin-top:10px;
  line-height:1.6}
@media (max-width:600px){
  .post{flex-direction:column;gap:3px}
  .post-title{white-space:normal;overflow:visible}
}

/* The stories behind one coverage bar. Anchored to the bar, which needs to be
   a positioned parent for it. */
.bar{position:relative}
.bar-pop{bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);
  width:min(340px,74vw);text-align:left}
/* Flipped below the bar when the sticky header would cover it. The bars are
   short, so "below" is barely lower than the bar itself. */
.bar-pop.pop-down{bottom:auto;top:calc(100% + 8px)}
.bar:hover .bar-pop{opacity:1;visibility:visible;pointer-events:auto}
.bar-pop a{display:block;color:#c9c9d6;font-size:11.5px;line-height:1.5;
  padding:4px 0;border-bottom:1px solid var(--line)}
.bar-pop a:last-of-type{border-bottom:0}
.bar-pop a:hover{color:var(--amber)}
.bar-pop em{display:block;font-style:normal;color:var(--muted);font-size:11px;
  margin-top:6px}
.spark-stale{display:block;font-size:11.5px;color:var(--muted);margin-top:7px;
  line-height:1.6}
.spark-stale b{color:var(--ink);font-weight:600}

/* Embedded Grafana */
.gpanel{width:100%;border:1px solid var(--line);border-radius:11px;background:var(--panel);
  display:block}
/* Nav links were 18px tall, well under the 44px a finger needs. The padding
   is what makes them tappable; the negative margin keeps them looking the
   same weight in the header as before. */
/* Centred: the nav has its own full-width row, so left-aligning it left a wide
   gap on the right and read as unfinished. */
.nav{display:flex;gap:4px;align-items:center;justify-content:center}
/* Each item explains itself on hover. Positioned relative to the link, and
   above it, so it never covers the item being pointed at. */
.nav a{position:relative}
.nav-tip{position:absolute;top:calc(100% + 8px);left:50%;transform:translateX(-50%);
  width:max-content;max-width:238px;background:#0f0f16;border:1px solid var(--line);
  border-radius:9px;padding:10px 13px;box-shadow:0 12px 34px rgba(0,0,0,.6);
  opacity:0;visibility:hidden;transition:opacity .13s,visibility .13s;z-index:60;
  pointer-events:none;color:var(--muted);font-size:11.5px;line-height:1.55;
  text-align:left;font-weight:400;text-transform:none;letter-spacing:0;
  /* The nav sets nowrap for its own items; without resetting it here the
     sentence stays on one line and runs outside the panel it is painted on. */
  white-space:normal}
.nav a:hover .nav-tip,.nav a:focus-visible .nav-tip,
.sorts a:hover .nav-tip,.sorts a:focus-visible .nav-tip{opacity:1;visibility:visible}
@media (prefers-reduced-motion:reduce){.nav-tip{transition:none}}
.nav a{font-size:11.5px;color:var(--muted);letter-spacing:.09em;
  text-transform:uppercase;padding:14px 12px;border-radius:7px;
  transition:color .15s,background .15s;white-space:nowrap}
.nav a:hover,.nav a.on{color:var(--amber)}
.nav a:hover{background:rgba(240,180,41,.07)}
/* Settings form rows. Named .frow, not .row: .row is already the lobby
   briefing card above, and the duplicate rule was overriding its
   display:block with display:flex. */
.frow{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-bottom:18px}
label.sw{display:flex;align-items:center;gap:10px;cursor:pointer;font-size:14px}
select{background:var(--panel);border:1px solid var(--line);color:var(--ink);
  padding:8px 12px;border-radius:6px;font-family:inherit;font-size:13px}
.help{font-size:12.5px;color:var(--muted);margin-top:8px;line-height:1.75}

/* --- continuous watch ------------------------------------------------- */
.ev{border-left:2px solid var(--line);padding:0 0 22px 20px;position:relative}
.ev:last-child{padding-bottom:0}
.ev::before{content:"";position:absolute;left:-5px;top:6px;width:8px;height:8px;
  border-radius:50%;background:var(--amber);box-shadow:0 0 8px rgba(240,180,41,.6)}
.ev-top{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.ev-tk{font-family:var(--mono);font-weight:700;font-size:14px}
.ev-when{font-size:11.5px;color:var(--muted);font-family:var(--mono)}
.ev-text{margin-top:6px;font-size:14.5px;color:#dcdce6;line-height:1.7}
.ev-src{margin-top:9px;display:flex;gap:8px;flex-wrap:wrap}
.ev-src a{font-size:11px;color:var(--muted);border:1px solid var(--line);
  border-radius:20px;padding:3px 11px}
.ev-src a:hover{color:var(--amber);border-color:var(--amber)}

/* Wraps rather than collides: on a narrow screen the ticker and the
   "every 1h - lite" side ran into each other because neither could shrink
   below its text. flex-wrap plus a min-width lets the right half drop under
   the left instead of overlapping it. */
.mon{display:flex;align-items:center;justify-content:space-between;gap:8px 16px;
  padding:13px 0;border-bottom:1px solid var(--line);font-size:13.5px;flex-wrap:wrap}
.mon > div:first-child{min-width:150px}
.mon:last-child{border-bottom:0}
.mon-id{font-family:var(--mono);font-size:10.5px;color:var(--muted);opacity:.75}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:8px}
.dot.live{background:var(--up);box-shadow:0 0 8px rgba(61,220,151,.7)}
.dot.off{background:var(--muted)}
/* The button and its explanation sit side by side, but the button must not be
   squeezed into a three-line stack when the text takes the room: it keeps its
   width and the note wraps beside it, or drops below on a narrow screen. */
.pull-row{margin-top:22px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.pull-row form{flex:0 0 auto}
.pull-row button{white-space:nowrap}
.pull-row > span{flex:1 1 220px;min-width:0}

/* --- discovery -------------------------------------------------------- */
.sug{border:1px solid var(--line);border-radius:12px;padding:20px 22px;
  margin-bottom:14px;background:var(--panel-2)}
.sug-top{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.sug-tk{font-family:var(--mono);font-size:18px;font-weight:700}
.sug-ex{font-size:11px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
.sug-what{font-size:14px;color:#dcdce6;margin-bottom:10px;line-height:1.65}
.sug-why{font-size:12.5px;color:var(--muted);line-height:1.65;
  border-left:2px solid var(--line);padding-left:13px;margin-bottom:14px}
.sug-act{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.conf{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
  border:1px solid var(--line);border-radius:20px;padding:2px 9px;color:var(--muted)}
.conf.high{color:var(--up);border-color:rgba(61,220,151,.35)}
.conf.medium{color:var(--amber);border-color:rgba(240,180,41,.35)}
.disc-form{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.disc-form input{flex:1;min-width:280px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:26px}
.chips a{font-size:12px;color:var(--muted);border:1px solid var(--line);
  border-radius:20px;padding:5px 13px}
.chips a:hover{color:var(--amber);border-color:var(--amber)}
/* FindAll is the one paid call in this product with a per-query price rather
   than a per-thousand one, so a click here is not free the way every other
   button is. Saying so next to the button is cheaper than a surprised bill. */
.disc-cost{font-size:11.5px;color:var(--muted);line-height:1.55;margin-top:14px}
/* A chip starts a search that takes seconds to hand back a redirect, so the
   click is acknowledged where it happened. Without this the page sat visibly
   idle and the only reasonable reading was that nothing had been clicked. */
.chips a.is-busy{color:var(--amber);border-color:var(--amber);
  pointer-events:none;opacity:.85}
.chips a.is-busy::before{content:"";display:inline-block;width:10px;height:10px;
  margin-right:7px;vertical-align:-1px;border:2px solid currentColor;
  border-right-color:transparent;border-radius:50%;animation:spin .7s linear infinite}

/* Three axes of the same question, side by side. Equal columns on purpose:
   the facets are alternatives to each other, not a ranking. */
.fac-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;
  align-items:start}
.fac{min-width:0}
.fac h3{font-size:13px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);margin:0 0 4px;display:flex;align-items:center;gap:8px}
.fac.working h3{color:var(--amber)}
.fac-n{font-family:var(--mono);font-size:11px;color:var(--fg);
  background:rgba(255,255,255,.06);border-radius:999px;padding:2px 8px;
  letter-spacing:0}
.fac-n.working{width:7px;height:7px;padding:0;border-radius:50%;
  background:var(--amber);animation:pulse 1.4s ease-in-out infinite}
.fac-cap{font-size:12px;color:var(--muted);line-height:1.55;margin-bottom:14px;
  padding-bottom:12px;border-bottom:1px solid var(--line)}
.fac .sug{padding:16px 18px;margin-bottom:12px}
.fac .sug-tk{font-size:15px}
.fac-wait{display:flex;gap:11px;align-items:flex-start;font-size:13px;
  color:var(--muted);border:1px dashed var(--line);border-radius:12px;
  padding:18px}
.fac-note{font-size:11.5px;margin-top:4px;line-height:1.5}
.fac-none{font-size:12.5px;color:var(--muted);border:1px dashed var(--line);
  border-radius:12px;padding:18px;line-height:1.6}
.fac-head{margin-bottom:6px}
.fac-head h2{margin-bottom:8px}
.fac-prof{display:flex;gap:8px;flex-wrap:wrap;align-items:center;
  margin-bottom:16px}
.pf{font-size:12px;border:1px solid var(--line);border-radius:999px;
  padding:5px 12px;color:var(--fg)}
.pf i{font-style:normal;color:var(--muted);text-transform:uppercase;
  letter-spacing:.07em;font-size:10px;margin-right:7px}
.pf-src{font-size:11px;color:var(--muted);letter-spacing:.04em}
/* The count is bolded mid-sentence, and as a flex item it became its own
   line box: "2 of / 3" split across two lines on a narrow screen. The text is
   one block that wraps as prose, with only the spinner as a flex sibling. */
.fac-bar b{white-space:nowrap}
.fac-bar{display:flex;align-items:center;gap:10px;font-size:13px;
  color:var(--muted);border:1px solid rgba(240,180,41,.3);
  background:rgba(240,180,41,.06);border-radius:10px;padding:11px 15px;
  margin-bottom:20px}
.spin{display:inline-block;width:12px;height:12px;flex:none;
  border:2px solid var(--amber);border-right-color:transparent;border-radius:50%;
  animation:spin .8s linear infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@media (max-width:900px){.fac-grid{grid-template-columns:1fr;gap:26px}}

/* --- evidence behind an extracted row --------------------------------- */
.ev-hint .hint-pop{width:min(330px,80vw)}
.ev-hint .hint-pop b{display:block;color:var(--ink);margin-bottom:8px;font-size:11px;
  letter-spacing:.06em;text-transform:uppercase}
/* The excerpt is a quoted sentence of arbitrary length, so it must wrap and be
   allowed to break inside a long token: a scraped URL or an unbroken run of
   digits was pushing the text outside the popup's own box. */
.ev-hint .hint-pop em{display:block;font-style:italic;color:#c8c8d6;margin-bottom:8px;
  border-left:2px solid var(--line);padding-left:11px;
  white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.ev-hint .hint-pop i{display:block;font-style:normal;font-family:var(--mono);
  font-size:10.5px;color:var(--muted);overflow-wrap:anywhere}
/* Anchored inward in the right-hand columns, where it would be clipped. */
td:last-child .ev-hint .hint-pop,td:nth-last-child(2) .ev-hint .hint-pop,
.tgt-price .ev-hint .hint-pop{left:auto;right:0;transform:none}
/* Set by the hover script on a popup that would be cut off at the top edge of
   its scrolling table. Only the rows near the top of the box get it. */
.hint-pop.pop-down{bottom:auto;top:calc(100% + 10px)}

/* --- a section with no data yet --------------------------------------- */
.pending{display:flex;flex-direction:column;gap:5px;padding:6px 0}
.pending b{color:var(--ink);font-weight:600;font-size:14px}
.pending span{color:var(--muted);font-size:13px}
.pending em{font-style:normal;color:var(--amber)}

/* --- settings: order of the blocks on a ticker page ------------------- */
.ord{display:flex;flex-direction:column;gap:9px;margin:14px 0 4px}
.ord-row{display:flex;align-items:center;gap:13px;background:var(--panel-2);
  border:1px solid var(--line);border-radius:9px;padding:12px 15px}
.ord-num{font-family:var(--mono);font-size:11px;color:var(--muted);width:18px;
  flex:none}
.ord-name{flex:1;font-size:14px}
.ord-row select{padding:7px 10px;font-size:12.5px}

/* --- stop watching a ticker ------------------------------------------- */
.rm{margin-top:56px;padding-top:22px;border-top:1px solid var(--line);
  display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.btn-rm{background:transparent;border:1px solid var(--line);color:var(--muted);
  padding:9px 16px;border-radius:8px;font-family:inherit;font-size:12.5px;cursor:pointer}
.btn-rm:hover{color:var(--down);border-color:var(--down)}
.rm span{font-size:11.5px;color:var(--muted)}

/* --- feedback on state changes ---------------------------------------- */
/* Every action here is a form post that goes off and does real work: a
   research run takes tens of seconds. With no feedback the page just sat
   there and the honest reading was that the click had missed. These rules
   are driven by the one script at the end of the shell, which marks a
   submitting form `.is-busy`. */
.btn,.btn-rm{transition:filter .15s,background .15s,color .15s,
  border-color .15s,opacity .15s,transform .08s}
.btn:active,.btn-rm:active{transform:translateY(1px)}
.btn:focus-visible,.btn-rm:focus-visible,.nav a:focus-visible,
input:focus-visible,select:focus-visible,.row:focus-visible{
  outline:2px solid var(--amber);outline-offset:2px}
form.is-busy button{opacity:.75;cursor:progress;pointer-events:none}
/* The spinner is a pseudo-element on the button so no markup has to change
   and the button keeps its own width while it spins. */
form.is-busy button::before{content:"";display:inline-block;width:11px;height:11px;
  margin-right:9px;vertical-align:-1px;border-radius:50%;
  border:2px solid currentColor;border-right-color:transparent;
  animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.row,.sug,.card{transition:border-color .15s,transform .15s}
.row:hover{transform:translateY(-1px)}
input{transition:border-color .15s,background .15s}

/* --- narrow screens --------------------------------------------------- */
/* The app pages overflowed to 554px inside a 390px viewport: the header row
   could not shrink, and the add-ticker form put two inputs and a button on
   one line. Everything below stacks instead of overflowing. */
@media (max-width:720px){
  /* overflow-x:clip, not hidden: `hidden` would make .wrap a scroll container
     and swallow the page's own vertical scrolling on some engines. `clip`
     just stops absolutely-positioned hover popups near the right edge from
     widening the document. */
  .wrap{padding:0 18px 72px;overflow-x:clip}
  .head-in{padding:18px 18px 0;gap:14px}
  /* The nav scrolls sideways in its own strip rather than forcing the page
     to. Momentum scrolling keeps it feeling native. */
  .head-in .nav{margin:0 -18px;padding:2px 18px;overflow-x:auto;
    -webkit-overflow-scrolling:touch;scrollbar-width:none}
  .head-in .nav::-webkit-scrollbar{display:none}
  header{margin-bottom:34px}
  h2{margin:38px 0 14px}
  .card{padding:24px 20px;border-radius:12px}
  /* No `.row` padding here. It used to be flattened to `18px 18px`, which
     predates the ticket styling and pulled the content left of the tear line:
     the perforation ran straight through the flag chips. The stub-aware
     padding lives with the rest of the ticket rules, in the 560px block. */
  /* Two inputs and a button on one line do not fit; each takes a full row. */
  form.add{flex-direction:column;gap:10px}
  /* !important because the ticker input carries an inline width:120px, which
     would otherwise win over this rule and leave it stranded at a third of
     the row while the company field took the rest. */
  form.add input,form.add button{width:100% !important}
  input,select,.btn,.btn-rm{font-size:16px}  /* 16px: stops iOS zooming on focus */
  .tk{font-size:22px} .px{font-size:22px}
  /* Tap targets: these were 15-31px tall, under the ~44px a fingertip needs.
     Padding is what makes them reliably hittable. */
  .back{display:inline-block;padding:12px 4px 12px 0}
  .sug-add,.peer-link,.ask-eg a,.ev-src a,.sub-chip{padding:10px 14px}
  /* The example questions on /ask are the main way in on a phone. Inline
     citation markers are deliberately left alone: they sit inside running
     prose and padding them would break the line rhythm. */
  a.theme{padding:11px 15px}
  .mon a,.ev-tk{display:inline-block;padding:6px 0}
  .stat i .hint,.hint{width:22px;height:22px;font-size:11px}
  .card-top{gap:14px;margin-bottom:20px}
  .stat{flex-basis:140px;padding:16px 15px}
  /* Citation previews hang off a superscript that can sit hard against the
     right margin. Narrowing them and letting the marker's own line box hold
     them keeps them on screen without detaching them from what they explain. */
  .cite-pop{width:min(230px,66vw)}
  /* Fixed 290-312px popups hang off a 390px screen, and the nth-child
     anchoring above is written for the four-column desktop grid so it does
     not survive the reflow. Narrowing them is most of the fix; the rest is
     the overflow-x:clip on .wrap below, which stops a popup near the right
     edge from ever turning into page scroll. */
  .hint-pop,.ev-hint .hint-pop{width:min(230px,64vw)}
  /* Filed leads the filings table, so on a phone the date and the form type
     together take ~250px of a 390px screen and crush the headline into a
     one-word column. They stack into a single leading cell instead: the form
     type is short and belongs with its date anyway. The header cell for Form
     goes with it, or the two rows no longer line up. */
  .fil-table td:nth-child(2),.fil-table th:nth-child(2){display:none}
  .fil-form-sm{display:block;font-family:var(--mono);font-size:12.5px;
    color:var(--ink);font-weight:600;margin-top:4px;text-align:left}
  .fil-table td:first-child,.fil-table th:first-child{padding-right:14px}
  .mon > div:last-child{text-align:left !important}
  footer{margin-top:44px}
}
/* The clip guard is unconditional, not only below 900px. It was written for
   the narrow screens where a citation popup hangs off the margin, but the
   section headings now carry a "?" of their own, and the last heading in the
   main column sits close enough to the right edge that its 290px popup adds a
   few pixels of page scroll at ANY width (measured: scrollWidth 1407 against a
   1400 viewport). The hover nudge still pulls the popup back into view; this
   only stops the resting layout from widening the page in the meantime.

   `clip` and never `hidden`: `hidden` would make .wrap a scroll container,
   which breaks `position:sticky` on the contents rail inside it. */
.wrap{overflow-x:clip}
/* Tablet width: too wide for the narrow-screen rules above, too narrow for the
   filings table's nowrap columns, so /lobby/<ticker> overflowed at 768px. The
   table keeps scrolling inside .tbl-scroll. */

/* A failure the user can read: a bold line saying what broke, then a sentence
   saying what it means, rather than the API's response body. */
.disc-err{text-align:left;padding:26px 28px}
.disc-err b{display:block;color:var(--amber);margin-bottom:8px;font-size:13px;
  text-transform:uppercase;letter-spacing:.1em}
.disc-err span{display:block;color:var(--muted);font-size:13.5px;line-height:1.7}

/* --- Ask ------------------------------------------------------------- */
/* The example questions used to be `.theme` chips (11px, a sentiment-tag
   style) sitting under a `margin:-18px` that pulled them onto the search box.
   They are a primary control on this page, not a passive label, so they get
   their own size and real separation from the input. */
.ask-form{display:flex;gap:11px;flex-wrap:wrap;margin-bottom:22px}
.ask-form input{flex:1;min-width:280px;padding:14px 17px;font-size:15px}
.ask-eg{margin-bottom:34px}
.ask-eg-label{display:block;font-size:10.5px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.12em;margin-bottom:11px}
.ask-chips{display:flex;gap:9px;flex-wrap:wrap}
.ask-chip{font-size:13px;color:var(--muted);border:1px solid var(--line);
  background:var(--panel);padding:9px 15px;border-radius:20px;line-height:1.45;
  transition:color .15s,border-color .15s}
.ask-chip:hover{color:var(--amber);border-color:var(--amber)}
/* The answer card names its question. On a page that can show an answer and a
   set of further links, an unlabelled block of prose left the reader guessing
   what it was answering. */
.ask-head{display:flex;justify-content:space-between;align-items:baseline;
  gap:14px;flex-wrap:wrap;margin-bottom:14px;padding-bottom:14px;
  border-bottom:1px solid var(--line)}
.ask-q{font-size:16.5px;line-height:1.45;margin:0;color:var(--ink);
  font-weight:600;flex:1;min-width:220px}
.ask-by{position:relative;font-family:var(--mono);font-size:11px;
  color:var(--muted);border:1px solid var(--line);border-radius:5px;
  padding:3px 8px;white-space:nowrap;cursor:help}
.ask-by:hover,.ask-by:focus-visible{color:var(--ink);border-color:var(--muted)}
/* Same panel the nav uses, rather than a browser title attribute: a native
   tooltip cannot hold a list, waits a second before appearing, and is styled
   by the OS. Anchored right because the badge sits at the right edge of the
   card and a centred panel would hang off it. */
.ask-tip{position:absolute;top:calc(100% + 9px);right:0;width:max-content;
  max-width:min(370px,84vw);background:#0f0f16;border:1px solid var(--line);
  border-radius:10px;padding:13px 15px;box-shadow:0 12px 34px rgba(0,0,0,.6);
  opacity:0;visibility:hidden;transition:opacity .13s,visibility .13s;z-index:60;
  pointer-events:none;color:var(--muted);font-family:inherit;font-size:12px;
  line-height:1.6;text-align:left;white-space:normal}
.ask-by:hover .ask-tip,.ask-by:focus-visible .ask-tip{opacity:1;visibility:visible}
.ask-tip b{color:var(--ink);display:block;margin-bottom:6px;font-size:12.5px}
.ask-tip i{font-family:var(--mono);font-style:normal;color:var(--amber)}
.tip-tools{margin:11px 0 0;padding:0;list-style:none;border-top:1px solid var(--line)}
.tip-tools li{padding:7px 0 0;font-size:11.5px;line-height:1.5}
.tip-tools li b{display:inline;font-family:var(--mono);color:var(--amber);
  font-size:11px;margin:0 7px 0 0;font-weight:600}
.tip-none{display:block;margin-top:9px;padding-top:9px;
  border-top:1px solid var(--line);font-size:11.5px}
@media (prefers-reduced-motion:reduce){.ask-tip{transition:none}}

/* The price of whatever the question is about. An answer about a stock that
   never says what it costs sends the reader to another tab. */
.ask-price{display:inline-flex;align-items:baseline;gap:11px;margin-bottom:16px;
  padding:9px 14px;border:1px solid var(--line);border-radius:9px;
  background:var(--panel-2)}
.ask-price:hover{border-color:var(--muted)}
.ap-t{font-family:var(--mono);font-size:12px;color:var(--amber);font-weight:600}
.ap-spot{font-size:18px;font-weight:600;color:var(--ink)}
.ap-chg{font-family:var(--mono);font-size:12.5px}
.ap-chg.up{color:var(--up)} .ap-chg.down{color:var(--down)}
.ap-chg.flat{color:var(--muted)}
.ap-when{font-family:var(--mono);font-size:11px;color:var(--muted)}
.ap-when.stale{color:var(--amber)}

/* Proof that the click landed. The agent takes ten to twenty seconds and the
   page was completely still for all of it. */
.ask-working{display:flex;align-items:center;gap:11px;margin:0 0 20px;
  padding:14px 17px;border:1px solid var(--line);border-radius:11px;
  background:var(--panel);font-size:13.5px;color:var(--ink)}
/* `display:flex` beats the `hidden` attribute, which is only `display:none` in
   the UA stylesheet: the banner was showing on every visit, saying the analyst
   was working before anything had been asked. Needs !important to win against
   the rule above it. */
.ask-working[hidden]{display:none!important}
.aw-sub{color:var(--muted);font-size:12.5px}

/* What has been asked before. A list of links, not cards: this is a way back
   to something, not a thing to read. */
/* A stored answer is labelled as one. The link out of it is the only way to
   spend money on this question again, which makes re-asking deliberate. */
.ask-cached{font-family:var(--mono);font-size:11px;color:var(--muted);
  margin:0 0 14px;padding:7px 11px;border:1px dashed var(--line);
  border-radius:7px;display:inline-block}
.ask-cached a{color:var(--amber);border-bottom:1px solid transparent}
.ask-cached a:hover{border-bottom-color:var(--amber)}

.hist-h{margin-top:44px}
.hist{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);
  border-radius:11px;overflow:hidden}
.hist-i{display:flex;align-items:baseline;gap:13px;padding:12px 15px;
  background:var(--panel);min-width:0}
.hist-i:hover{background:var(--panel-2)}
.hist-q{font-size:13.5px;color:#c8c8d4;flex:1;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.hist-i:hover .hist-q{color:var(--ink)}
.hist-m{font-family:var(--mono);font-size:11px;color:var(--muted);flex:none}
.hist-w{font-family:var(--mono);font-size:11px;color:var(--muted);flex:none;
  min-width:64px;text-align:right}
/* On a narrow screen the question keeps the row and the tool count drops:
   "3 tools" is context, the question is the thing being looked for. */
@media (max-width:520px){.hist-m{display:none}}
.aw-dot{width:9px;height:9px;border-radius:50%;background:var(--amber);
  flex:none;animation:awp 1.1s ease-in-out infinite}
@keyframes awp{0%,100%{opacity:.25;transform:scale(.8)}50%{opacity:1;transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.aw-dot{animation:none;opacity:.9}}

/* Further reading, not a second essay. */
.so-head{display:flex;justify-content:space-between;align-items:baseline;
  gap:12px;flex-wrap:wrap;margin-bottom:13px}
.so-head b{font-size:14px;color:var(--ink)}
.so-note{font-family:var(--mono);font-size:11px;color:var(--muted);cursor:help}
.so-note:hover{color:var(--ink)}
.so-links{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);
  border-radius:9px;overflow:hidden}
.so-link{display:flex;align-items:baseline;gap:12px;padding:11px 14px;
  background:var(--panel-2);min-width:0}
.so-link:hover{background:var(--panel)}
.so-host{font-family:var(--mono);font-size:11px;color:var(--amber);
  flex:none;min-width:132px}
.so-title{font-size:13px;color:#b8b8c6;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;flex:1;min-width:0}
.so-date{font-family:var(--mono);font-size:11px;color:var(--muted);flex:none;
  margin-left:auto;padding-left:10px}
/* The host column and the date both shrink before the headline does, and on a
   narrow screen the host drops out entirely: the title is what gets clicked. */
@media (max-width:560px){.so-host{min-width:0;max-width:88px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}}
.ask-step{font-family:var(--mono);font-size:11.5px;color:var(--muted);
  padding:8px 0;border-bottom:1px solid var(--line);
  display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}
.ask-step:last-child{border-bottom:0}
.ask-tool{color:var(--amber);font-weight:600}
.ask-args{overflow-wrap:anywhere;min-width:0}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms !important;
    animation-iteration-count:1 !important;transition-duration:.01ms !important}
}
"""

DISCLAIMER = (
    "The Ticker Room is a research and awareness tool. It is not investment advice "
    "and produces no buy or sell recommendations. Always do your own research."
)


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _updated_badge(last_run: dict | None) -> str:
    """Show when the data was last refreshed, and flag it when it goes stale.

    While a run is in flight this says so instead. A pass takes minutes, and
    with only a "last updated" time the page looked identical the moment after
    the button was pressed: the honest reading was that the click had missed.
    """
    running = (last_run or {}).get("running")
    if running:
        n = running.get("n_tickers") or 0
        what = f"{n} ticker{'s' if n != 1 else ''}" if n else "the watchlist"
        started, _ = _ago(running.get("started_at"))
        return ('<span class="updated running"><b class="live"></b>'
                f'Researching {_esc(what)}<span class="run-since"> &middot; '
                f'started {started}</span></span>')

    when, stale = _ago((last_run or {}).get("finished_at"))

    # An out-of-credit run outranks the timestamp. Without this the page shows
    # a perfectly ordinary "last updated" over figures that stopped moving,
    # which is how the account sat empty for twelve days unnoticed.
    if (last_run or {}).get("error") == "no_credit":
        return ('<span class="updated nocredit" title="Every lookup returned '
                'HTTP 402. Nothing below has been refreshed since.">'
                f'<b>&#9888; Research stopped &middot; out of API credit</b>'
                f'<span class="run-since"> &middot; last good data {when}</span></span>')

    trigger = (last_run or {}).get("trigger", "")
    cls = " stale" if stale else ""
    suffix = f" &middot; {_esc(trigger)}" if trigger else ""
    return (f'<span class="updated">Last updated <b class="{cls.strip()}">{when}</b>'
            f"{suffix}</span>")


# Kept out of the f-string in _shell: JavaScript braces would be read as
# f-string placeholders.
SCRIPT = """<script>
/* Progressive enhancement only: with this script blocked every form still
   posts and every page still renders. All it does is acknowledge the click
   on the actions that take real time, so the page is not silent while the
   agent works. */
document.addEventListener("submit", function (e) {
  var f = e.target;
  if (!(f instanceof HTMLFormElement) || f.classList.contains("is-busy")) return;
  f.classList.add("is-busy");
  var b = f.querySelector("button");
  /* The label is swapped only when the form says what to say, so a plain
     form (Add, Save) keeps its own wording and just gets the spinner. */
  var busy = f.getAttribute("data-busy");
  if (b && busy) { b.dataset.idle = b.textContent; b.textContent = busy; }
  /* A form that failed server-side would otherwise stay spinning forever on
     a back-button restore, so the state is cleared when the page is shown
     again from the bfcache. */
});
/* Hover popups (citations, the "?" hints) are anchored to whatever they
   explain, which on a narrow screen can sit hard against either margin. CSS
   alone cannot know where that is, so the popup is nudged back inside the
   viewport the first time it is shown. Pure enhancement: without it the
   popup is merely clipped, never lost. */
document.addEventListener("mouseover", function (e) {
  var host = e.target.closest
    && e.target.closest(".cite,.hint,.ev-hint,.tgt-dot,.bar,.sorts a");
  if (!host) return;
  var pop = host.querySelector(".cite-pop,.hint-pop,.nav-tip,.bar-pop");
  if (!pop) return;
  /* marginLeft, not transform: the centring transform is what the stylesheet
     uses to anchor the popup over its marker, so it must survive the nudge. */
  pop.style.marginLeft = "0px";
  /* Clamp to whichever box actually cuts the popup off. The viewport is not
     it: .wrap carries overflow-x:clip, so a citation on the first word of a
     paragraph opens a 310px popup that is still well inside the window but
     sliced down its left edge by .wrap. Measuring only the window left that
     case uncorrected, which is what made the first marker in the briefing
     show a half-popup with its title cut in two. */
  var box = pop.closest(".wrap"), pad = 8;
  var lo = pad, hi = window.innerWidth - pad;
  if (box) {
    var bb = box.getBoundingClientRect();
    lo = Math.max(lo, bb.left + pad);
    hi = Math.min(hi, bb.right - pad);
  }
  var r = pop.getBoundingClientRect(), shift = 0;
  /* If the popup is wider than the box that clips it, pin it to the left edge
     rather than fighting both sides: shifting for the right edge would then
     push the start of the text out of view, which is the half that matters. */
  if (r.width > hi - lo) shift = lo - r.left;
  else if (r.right > hi) shift = hi - r.right;
  else if (r.left < lo) shift = lo - r.left;
  if (shift) pop.style.marginLeft = Math.round(shift) + "px";

  /* Vertical, and the reason it is here rather than in the stylesheet: a table
     in .tbl-scroll has overflow-x:auto, which makes it a scroll container on
     BOTH axes, so a popup opening upward is cut off at the top edge of that box
     instead of being painted over it. The header hints are pinned downward in
     CSS because they are always at the top, but a row's "?" can be anywhere:
     flipping every one of them down would clip the last rows the same way.
     So the direction is chosen per popup, against whichever box actually
     clips it. */
  pop.classList.remove("pop-down");
  var pr = pop.getBoundingClientRect();
  /* The sticky header is the other thing that hides an upward popup, and it
     clips anything on the page, not only what is inside a scrolling table: a
     tall coverage bar near the top of the viewport opened its list of articles
     straight underneath the header. It is treated as a top edge like any
     other, and the flip only happens when going down actually clears it. */
  var head = document.querySelector("header");
  var headBottom = head ? head.getBoundingClientRect().bottom : 0;
  if (pr.top < headBottom && pr.height < window.innerHeight - headBottom) {
    pop.classList.add("pop-down");
    return;
  }
  var clip = pop.closest(".tbl-scroll");
  if (!clip) return;
  var cb = clip.getBoundingClientRect();
  /* Only flip if going down actually helps: in a box too short to hold the
     popup either way, leaving it up keeps the first line readable. */
  if (pr.top < cb.top && pr.height < cb.height) pop.classList.add("pop-down");
});

/* The filings table renders every row and hides all but the first ten, so the
   button reveals rows that are already in the DOM. It starts hidden and is
   only shown here: without JS the rows unhide themselves (see the noscript
   rule) and a button that cannot work is never painted. */
/* The button and its fade live in a .more-wrap, so it is the wrapper that is
   shown and hidden: hiding the button alone would leave the fade sitting over
   nothing. `:not([data-more])` keeps the briefing's control out of this — it
   borrows the button's looks but has no rows to reveal, and this handler would
   hide it on the first click while the text stayed clipped. */
document.querySelectorAll(".more-wrap").forEach(function (w) {
  var b = w.querySelector(".fil-show:not([data-more])");
  if (!b) return;
  w.hidden = false;
  b.addEventListener("click", function () {
    w.closest(".card").querySelectorAll("tr.fil-more,tr.tgt-more")
      .forEach(function (tr) { tr.hidden = false; });
    w.hidden = true;
  });
});

/* Links that start real work, not just navigation. A "Peers of ONDS" chip
   holds the browser for several seconds while three FindAll runs are created
   before it can redirect, and a link gives none of the feedback a submitting
   form does. Marked with data-busy so only the slow links opt in. */
document.addEventListener("click", function (e) {
  var a = e.target.closest && e.target.closest("a[data-busy]");
  if (!a || a.classList.contains("is-busy")) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  a.classList.add("is-busy");
  a.dataset.idle = a.textContent;
  a.textContent = a.getAttribute("data-busy");
});

window.addEventListener("pageshow", function () {
  document.querySelectorAll("a.is-busy").forEach(function (a) {
    a.classList.remove("is-busy");
    if (a.dataset.idle) a.textContent = a.dataset.idle;
  });
  document.querySelectorAll("form.is-busy").forEach(function (f) {
    f.classList.remove("is-busy");
    var b = f.querySelector("button");
    if (b && b.dataset.idle) b.textContent = b.dataset.idle;
  });
});

/* Reordering the lobby, in the browser. Every sort runs on numbers already
   stamped on each card, so a click is a DOM reshuffle rather than a round trip
   that re-reads Firestore five times per ticker (about a second for two
   tickers, and it grows with the watchlist).

   The links still point at real `?sort=` URLs and the server still sorts, so
   this is enhancement only: with the script blocked, a click is a normal
   navigation that returns a correctly ordered page. */
(function () {
  var list = document.querySelector(".sorts");
  if (!list || !window.history || !history.pushState) return;
  var box = document.querySelector(".rows");
  if (!box) return;
  var cards = Array.prototype.slice.call(box.querySelectorAll("a.row"));
  if (cards.length < 2) return;

  function apply(key) {
    var by = {
      ticker: function (a, b) {
        return a.dataset.ticker.localeCompare(b.dataset.ticker);
      }
    }[key] || function (a, b) {
      /* Descending on the chosen number, ties broken on ticker so the order
         is stable and cards do not swap places between clicks. */
      var d = parseFloat(b.dataset[key] || 0) - parseFloat(a.dataset[key] || 0);
      return d || a.dataset.ticker.localeCompare(b.dataset.ticker);
    };
    cards.slice().sort(by).forEach(function (c) { box.appendChild(c); });

    list.querySelectorAll("a").forEach(function (a) {
      var on = a.getAttribute("href") === "/lobby?sort=" + key;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
  }

  list.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    var key = (a.getAttribute("href").split("sort=")[1] || "").trim();
    if (!key) return;
    e.preventDefault();
    apply(key);
    /* The URL still changes, so the view is shareable and reload keeps it. */
    history.pushState({sort: key}, "", a.getAttribute("href"));
  });

  /* Back and forward move through orderings rather than leaving the page. */
  window.addEventListener("popstate", function () {
    var m = /[?&]sort=([a-z]+)/.exec(location.search);
    apply(m ? m[1] : "attention");
  });
})();

/* While a run is in flight, reload so the page fills in as tickers land.
   A timer rather than <meta http-equiv="refresh">: the meta tag reloads even
   while someone is typing into the add-ticker box and throws away what they
   wrote. This skips the reload whenever a field is focused, and stops as soon
   as the badge is gone. */
(function () {
  if (!document.querySelector(".updated.running")) return;
  setTimeout(function () {
    var a = document.activeElement;
    if (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) return;
    if (document.visibilityState === "hidden") return;
    location.reload();
  }, 12000);
})();
</script>"""


# The nav is defined once and rendered identically on every page. It used to be
# written out per template, which is how "Watchlist" came to vanish from the
# page you were on and Ask/Settings came to appear only on some: each template
# listed the destinations its author happened to be thinking about. A menu that
# reorders itself is unusable as a map, so this list is fixed and the current
# page is marked rather than dropped.
#
# Each entry carries the sentence that appears on hover. There is no separate
# "Alerts" destination: a combined feed meant seeing your own tickers twice,
# once as a list and once as a stream. The watch, what it caught and the alerts
# it fired all live on the page for the company they belong to.
NAV = [
    ("/lobby", "The Lobby",
     "The companies being tracked, ranked so the one that needs you is first"),
    ("/discover", "Discover",
     "Companies you have not named yet, proposed with the evidence for each"),
    ("/ask", "Ask",
     "A plain-language question, answered from the stored history"),
    ("/how-it-works", "How it works",
     "What the room does, and the wiring underneath it"),
]

# Settings is deliberately not in the nav. The top nav is for the places you
# read; settings is configuration you touch once and then leave alone, and
# sitting alongside them it competed for attention with the pages that carry
# the product. It lives in the footer, which is where a preferences link is
# looked for anyway.
# The sitemap sits between them because it is the map of everything else in
# this row, and the legal set is grouped after it: a reader scanning a footer
# for "privacy" expects to find it next to the other boilerplate, not
# interleaved with the product links.
# "How does it work?" is NOT here: it moved to the top nav, because it is the
# page that explains what the other three destinations are and a first-time
# visitor should not have to reach the bottom of the page to find it. Listing
# it in both rows would mark two links as current at once.
FOOT_NAV = [
    ("/settings", "Settings"),
    ("/sitemap", "Sitemap"),
    ("/privacy", "Privacy"),
    ("/terms", "Terms"),
    ("/legal-notice", "Legal notice"),
    ("/cookies", "Cookies"),
]


# Three amber bulbs on the app's own near-black, drawn at 32px. An SVG favicon
# stays sharp on any display, and inlining it means the tab icon is part of the
# document rather than a second request that has to be routed and cached.
FAVICON = (
    '<link rel="icon" href="data:image/svg+xml,'
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='7' fill='%230b0b0f'/%3E"
    "%3Ccircle cx='8.5' cy='16' r='3.4' fill='%23f0b429'/%3E"
    "%3Ccircle cx='16' cy='16' r='3.4' fill='%23f0b429' opacity='.72'/%3E"
    "%3Ccircle cx='23.5' cy='16' r='3.4' fill='%23f0b429' opacity='.44'/%3E"
    "%3C/svg%3E\">"
)


def _nav(here: str = "") -> str:
    """The menu, with a styled tooltip on each item.

    The tooltip is a child element rather than a `title` attribute: the native
    one takes about a second to appear, cannot be styled, and never shows on a
    touch screen. `aria-label` carries the same sentence for a screen reader,
    which the visual popup cannot do on its own.
    """
    items = []
    for href, label, tip in NAV:
        on = ' class="on" aria-current="page"' if href == here else ""
        items.append(
            f'<a href="{href}"{on} aria-label="{_esc(label)}: {_esc(tip)}">'
            f'{label}<span class="nav-tip">{_esc(tip)}</span></a>'
        )
    return '<nav class="nav">' + "".join(items) + "</nav>"


def _foot_nav(here: str = "") -> str:
    """The footer links, including Settings.

    Marked with aria-current like the main nav, so being on /settings is still
    announced even though the link is no longer in the header.
    """
    items = []
    for href, label in FOOT_NAV:
        # The legal block opens with the sitemap, which is the map of the row.
        if href == "/sitemap":
            items.append('<span class="foot-sep" aria-hidden="true">&middot;</span>')
        on = ' aria-current="page"' if href == here else ""
        items.append(f'<a class="foot-a" href="{href}"{on}>{_esc(label)}</a>')
    return "".join(items)


def _shell(title: str, body: str, last_run: dict | None = None,
           here: str = "", extra_css: str = "", extra_js: str = "") -> str:
    """The page frame. `last_run` is accepted but not drawn here.

    The freshness badge used to sit in the header on every page, which put a
    line about the research pass above screens that have nothing to do with it
    (Settings, the explainer). It now belongs to the watchlist, directly above
    the cards whose figures it dates, and `page_index` draws it there.
    """
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>{FAVICON}<style>{CSS}{extra_css}</style>
<noscript><style>tr.fil-more[hidden],tr.tgt-more[hidden]{{display:table-row}}</style></noscript></head><body>
<header><div class="head-in">
  <a href="/" class="brand">
    <span class="brand-top">
      <span class="bulbs"><i class="bulb"></i><i class="bulb"></i><i class="bulb"></i></span>
      <h1>The Ticker <span>Room</span></h1>
    </span>
    <span class="tag">Now showing &middot; an agent that reads the week</span>
  </a>
  {_nav(here)}
</div></header>
<div class="wrap">{body}</div>
<footer><div>{_esc(DISCLAIMER)}</div>
<div class="foot-nav">{_foot_nav(here)}</div>
<div style="margin-top:10px">Research by Parallel &middot; Briefings by Gemini &middot; AGPL-3.0</div>
</footer>
{SCRIPT}{extra_js}
</body></html>"""


def _price_block(q: dict | None) -> str:
    if not q or q.get("spot") is None:
        return '<div class="px" style="color:var(--muted);font-size:15px">no price</div>'
    chg = q.get("change_pct") or 0
    cls = "up" if chg >= 0 else "down"
    return (f'<div><div class="px">${q["spot"]:,.2f}</div>'
            f'<div class="chg {cls}">{chg:+.2f}%</div></div>')


def _by_day(articles: list[dict]) -> dict[str, list[dict]]:
    """The stored articles, grouped by the day they were found.

    `found_at` is the run timestamp, which is the same key `coverage_daily`
    counts on, so the grouping lines up with the bars by construction rather
    than by a date parsed out of the story itself.
    """
    out: dict[str, list[dict]] = {}
    for a in articles or []:
        day = (a.get("found_at") or "")[:10]
        if day:
            out.setdefault(day, []).append(a)
    return out


def _bar_pop(day: str, n: int, rows: list[dict]) -> str:
    """The stories behind one bar.

    A bar with a number and no way to reach the stories is an assertion. These
    are the same articles the Sources table lists; the chart just never said
    so, which made the count look like it came from somewhere else.
    """
    head = f'<b>{_esc(day)}</b><i>{n} article{"s" if n != 1 else ""} found</i>'
    if not rows:
        # The count is real but the stories fell outside what is kept, so the
        # popup says which rather than showing an empty box.
        return (f'<span class="hint-pop bar-pop">{head}'
                f'<em>Older than the stories still stored for this ticker.</em>'
                f'</span>')
    items = "".join(
        f'<a href="{_esc(r["url"])}" target="_blank" rel="noopener">'
        f'{_esc((r.get("title") or r["url"])[:110])}</a>'
        for r in rows[:6]
    )
    more = (f'<em>and {len(rows) - 6} more, listed under Sources</em>'
            if len(rows) > 6 else "")
    return f'<span class="hint-pop bar-pop">{head}{items}{more}</span>'


def _spark(coverage: list[dict], with_hint: bool = False,
           articles: list[dict] | None = None) -> str:
    """Articles per day. One bar per day; amber marks a day above the baseline.

    Each bar opens the stories it counted. Without that the chart asked to be
    taken on trust while the Sources table listed the very same articles a
    screen below, unconnected.
    """
    if not coverage:
        return ""
    hint = COVERAGE_HINT if with_hint else ""
    vals = [c["articles"] for c in coverage]
    top = max(vals) or 1
    avg = sum(vals) / len(vals)
    grouped = _by_day(articles or [])

    bars = "".join(
        f'<div class="bar{" hot" if v > avg * 1.6 and v > 2 else ""}"'
        f' style="height:{max(8, v / top * 100):.0f}%"'
        f' title="{c["day"]}: {v} article{"s" if v != 1 else ""}">'
        f'{_bar_pop(c["day"], v, grouped.get(c["day"], []))}</div>'
        for c, v in zip(coverage, vals)
    )
    total = sum(vals)
    span = len(coverage)
    # The last bar is dated in the open. A chart that stops days ago looks
    # identical to one that is current, and the honest reading of a flat tail
    # is "nothing has run since", not "the news went quiet".
    last_day = coverage[-1]["day"]
    stale = _days_since(last_day)
    tail = ""
    if stale is not None and stale >= 1:
        tail = (f'<span class="spark-stale">Last counted <b>{_esc(last_day)}</b>, '
                f'{stale} day{"s" if stale != 1 else ""} ago &middot; '
                f'a bar appears only on a day research ran</span>')
    label = (
        '<div class="spark-label">'
        f'<span><b>{total}</b> article{"s" if total != 1 else ""} over '
        f'<b>{span}</b> day{"s" if span != 1 else ""}</span>{hint}</div>'
        + tail
    )
    return f'<div class="spark">{bars}</div>{label}'


def _days_since(day: str) -> int | None:
    """Whole days between a YYYY-MM-DD and today, or None if unparseable."""
    try:
        then = datetime.strptime(day, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc).date() - then).days


def _paras(text: str, sources: list[dict] | None = None) -> str:
    """Briefing paragraphs with [n] markers turned into hoverable citations."""
    return _cite_paragraphs(text, sources or [])


def _ago(iso: str | None) -> tuple[str, bool]:
    """Human 'time since', plus whether the data is stale (over 24h old)."""
    if not iso:
        return "never", True
    try:
        then = datetime.fromisoformat(iso)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except ValueError:
        return "unknown", True
    mins = (datetime.now(timezone.utc) - then).total_seconds() / 60
    if mins < 1:
        return "just now", False
    if mins < 60:
        return f"{int(mins)} min ago", False
    if mins < 1440:
        return f"{int(mins // 60)}h ago", False
    return f"{int(mins // 1440)}d ago", True


METRIC_HINTS = {
    "Spot": "The last traded price.",
    "Change": "Move since the previous close.",
    "MA20": "Average closing price of the last 20 trading days, about a month. "
            "Price above it means the recent trend is up; below, down.",
    "MA50": "Average of the last 50 trading days, about a quarter. Read with "
            "MA20: price under both is a stock that has been falling for a while.",
    "52w low": "The cheapest it traded in the past year.",
    "52w high": "The dearest it traded in the past year. How far below it the "
                "price sits says how much ground it has given up.",
    "Off 52w high": "How far the price is below its one-year peak.",
}


def _stat_hint(label: str) -> str:
    text = METRIC_HINTS.get(label)
    if not text:
        return ""
    return (f'<span class="hint">?<span class="hint-pop"><b>{_esc(label)}</b>'
            f'{_esc(text)}</span></span>')


# The three parts of the Alerts card, each explained where it sits. They were
# described only in the section-level "?" at the top, which meant the answer to
# "why is this box empty when the one below it is full" was three paragraphs
# away behind a hover nobody opens. The distinction they carry is the one
# readers actually miss: the run is a full re-search on a schedule, the monitor
# is an alarm that only speaks when something new happens, and Grafana is a
# rule over what the other two already wrote.
WATCH_HINT = (
    '<span class="hint">?<span class="hint-pop">'
    "<b>The standing watch</b>"
    "Proof this company is being watched, not a feed: it shows the Parallel "
    "Monitor itself, its hourly cadence and its id. A monitor is declared once "
    "and then runs on Parallel's side forever, so this panel looks the same "
    "every day. If the watch ever stopped, the dot would go grey and it would "
    "say so here. <b>Pull events now</b> does not search: it collects what the "
    "monitor has already found, which is how events are seen without waiting "
    "for the webhook."
    "</span></span>"
)

CAUGHT_HINT = (
    '<span class="hint">?<span class="hint-pop">'
    "<b>What it caught</b>"
    "Discrete events the hourly watch spotted between the twice-daily research "
    "passes: a contract win, an insider sale, a rating change, an 8-K. Each "
    "line is the monitor's own wording with a link to the filing or article it "
    "read. This is the fast path: an insider sale filed at 11:00 lands here "
    "within the hour instead of waiting for the evening pass. It only reports "
    "what happens after the watch starts, so a ticker added today shows nothing "
    "until this company next moves, however long that takes."
    "</span></span>"
)

ALERTS_FIRED_HINT = (
    '<span class="hint">?<span class="hint-pop">'
    "<b>Alerts fired</b>"
    "The narrow subset worth interrupting you for. Grafana runs SQL over the "
    "filings and targets these pages already store, so it costs nothing and "
    "adds no new research: it is a rule, not a search. It re-evaluates every "
    "five minutes and fires when one crosses a line, such as an insider sale in "
    "the last seven days or a target cut of more than 15%. The rules aggregate "
    "over the whole watchlist, so a row can be about another holding."
    "</span></span>"
)

COVERAGE_HINT = (
    '<span class="hint">?<span class="hint-pop">'
    "<b>Coverage &middot; articles per day</b>"
    "One bar per day, counting the stories found about this company. "
    "After a single run there is only one bar, so there is nothing to compare it "
    "to yet. Once a baseline builds up, a day that breaks well above it turns "
    "amber: that is a news spike, and it is what the alert fires on."
    '<span class="demo-bars">'
    '<div style="height:22%"></div><div style="height:30%"></div>'
    '<div style="height:18%"></div><div style="height:26%"></div>'
    '<div style="height:34%"></div><div class="hot" style="height:100%"></div>'
    '<div style="height:44%"></div></span>'
    "Example of a spike, once history exists."
    "</span></span>"
)



# Grafana runs alongside the app in local development. The deployed service has
# no Grafana of its own, so panels are replaced by a note rather than by three
# broken iframes pointing at somebody's laptop.
GRAFANA = os.environ.get("GRAFANA_URL", "http://127.0.0.1:3077")
GRAFANA_AVAILABLE = bool(os.environ.get("GRAFANA_URL")) or not os.environ.get("K_SERVICE")


def _panel(panel_id: int, height: int = 300, ticker: str | None = None) -> str:
    """Embed one Grafana panel. Grafana is the metrics layer, not a screenshot."""
    if not GRAFANA_AVAILABLE:
        return ""
    # The dashboard defines a `ticker` template variable; passing it renders
    # the panel for one company instead of the whole watchlist.
    var = f"&var-ticker={_esc(ticker)}" if ticker else "&var-ticker=%25"
    src = (f"{GRAFANA}/d-solo/tickerroom-coverage/_?orgId=1&panelId={panel_id}"
           f"&from=now-30d&to=now&theme=dark{var}")
    return (f'<iframe class="gpanel" src="{src}" height="{height}" '
            f'frameborder="0" loading="lazy"></iframe>')


SENTIMENT_HINT = (
    '<span class="hint">?<span class="hint-pop">'
    "<b>How the score works</b>"
    "Every post found about this company is read and placed on one scale: "
    "<b>-100</b> if the talk is uniformly bearish, <b>0</b> if it is balanced, "
    "<b>+100</b> if it is uniformly bullish. The label is a plain reading of "
    "that number.<br><br>"
    "<b>bullish</b> above +20 &middot; <b>bearish</b> below -20 &middot; "
    "<b>mixed</b> in between &middot; <b>quiet</b> when too few people are "
    "talking to call it.<br><br>"
    "It describes what people are saying. It is not advice, and it says "
    "nothing about where the price is going."
    "</span></span>"
)

LABEL_MEANING = {
    "bullish": "more optimistic than not",
    "bearish": "more pessimistic than not",
    "mixed": "arguments on both sides, no clear lean",
    "quiet": "too little discussion to call",
}


# One line per section of a ticker page, saying what produced it and how often.
# Keyed by the same strings as `settings.SECTIONS`, so a section cannot be
# renamed or added without its explanation being noticed as missing: `_sec_h2`
# builds the heading from this dict and the label list together.
SECTION_HINTS = {
    "alerts": ("Everything that has happened since you last looked, in three "
               "parts. <b>The standing watch</b> is a Parallel Monitor on this "
               "company: it runs on its own every hour, between the twice-daily "
               "research passes, and is what notices something in the hours "
               "when nothing else is looking. <b>What it caught</b> is what "
               "that watch turned up, newest first, each line linking out to "
               "where it was published. <b>Alerts fired</b> is the narrower "
               "set that crossed a threshold worth telling you about: the rules "
               "live in Grafana and read the same metrics these pages do, so a "
               "coverage spike, a sentiment swing or a target cut appears here. "
               "Empty means the watch ran and found nothing, not that it is off. "
               "This section leads the page because it is the one that changes "
               "between visits."),
    "filings": ("What the company filed with the SEC, newest first. The flagged "
                "kinds are the ones worth a look on their own: dilution, "
                "insider buying and selling, and activist stakes."),
    "briefing": ("The written read on this company, from the last research "
                 "pass. Every claim carries a citation you can hover to see the "
                 "sentence it came from, and open to read the source."),
    "targets": ("Published analyst price targets, newest first, with the "
                "revisions folded in so a target that has just moved shows its "
                "old value beside the new one. Several firms report the same "
                "analyst under different spellings, so the names are merged "
                "before the average is taken."),
    "social": ("Two halves of one question. <b>What people are posting</b> is "
               "a score read off the actual Reddit and X posts, which are "
               "listed under it. <b>How much is being written</b> counts the "
               "news stories found per day, so a bar well above the others is "
               "a spike in attention rather than in tone."),
    "sources": ("Every article this research pass found about the company, with "
                "the day it was found. The coverage bars above count these same "
                "stories, so a bar and this table never disagree."),
}


def _sec_h2(key: str, label: str) -> str:
    """A section heading with its explainer.

    The heading text comes from the same `SECTIONS` list the contents rail is
    built from, so the rail and the page can never name a section differently.
    """
    hint = SECTION_HINTS.get(key)
    pop = (f'<span class="hint">?<span class="hint-pop"><b>{_esc(label)}</b>'
           f'{hint}</span></span>') if hint else ""
    return f'<h2 class="sec-h2">{_esc(label)}{pop}</h2>'


def _posts_block(posts: list[dict]) -> str:
    """The posts the score was read from, as links.

    A sentiment score with no posts under it is the one unsourced number the
    page would have carried: every price target links to where it was
    published, every filing to EDGAR. Readings stored before this existed have
    no posts, so the block says so rather than implying none were read.
    """
    if not posts:
        return ('<div class="posts-none">This reading was taken before posts '
                'were kept. The next research pass lists them here.</div>')
    items = "".join(
        f'<a class="post" href="{_esc(pt["url"])}" target="_blank" rel="noopener">'
        f'<span class="post-where {"x" if pt.get("platform") == "x" else "rd"}">'
        f'{_esc(pt.get("where") or "")}</span>'
        f'<span class="post-title">{_esc(pt.get("title") or pt["url"])}</span></a>'
        for pt in posts[:14]
    )
    more = (f'<div class="posts-more">and {len(posts) - 14} more read for this '
            f'score</div>' if len(posts) > 14 else "")
    return (f'<div class="posts-label">Read from these posts</div>'
            f'<div class="posts">{items}</div>{more}')


def _sentiment_block(s: dict | None) -> str:
    """Social sentiment, with enough context to judge whether to trust it.

    A bare score invites the wrong question ("only 5 posts?"). Showing the
    scale, the window, the count and the sources makes the number legible.
    """
    window = (s or {}).get("window_days", 7)

    if s and s.get("label") == "unavailable":
        # The posts still show: the scoring failed, but what it was going to
        # read is the half of the answer that is still worth having.
        found = s.get("posts") or []
        return ('<div class="sent"><span class="sent-lab" style="color:var(--amber)">'
                'Social &middot; unavailable</span>'
                f'<span class="sent-note">{_esc(s.get("summary", ""))}</span>'
                + (_posts_block(found) if found else "") + "</div>")

    if not s or s.get("label") == "quiet":
        return ('<div class="sent">'
                '<span class="sent-lab quiet">Social &middot; quiet</span>'
                f'<span class="sent-note">Nothing was posted about this on '
                f'Reddit or X in the last {window} days.</span></div>')

    score = int(s.get("score", 0))
    pos = (score + 100) / 2
    label = _esc(s.get("label", "mixed"))
    n = s.get("n_threads", 0)
    n_x = s.get("n_x", 0)
    n_reddit = max(0, n - n_x)
    subs = s.get("subreddits") or []

    where = []
    if n_reddit:
        where.append(f"{n_reddit} Reddit thread{'s' if n_reddit != 1 else ''}")
    if n_x:
        where.append(f"{n_x} post{'s' if n_x != 1 else ''} on X")

    sub_list = "".join(
        f'<span class="sub-chip"><b>{"X" if name == "X" else "r/" + _esc(name)}</b>'
        f'{count}</span>'
        for name, count in subs
    )
    themes = "".join(f'<span class="theme">{_esc(t)}</span>' for t in s.get("themes", []))

    return f'''<div class="sent">
  <div class="sent-head">
    <span class="sent-lab {label}">Social sentiment{SENTIMENT_HINT}</span>
  </div>
  <div class="sent-verdict">
    <span class="sent-score {label}">{score:+d}</span>
    <span class="sent-word {label}">{label}</span>
    <span class="sent-gloss">{_esc(LABEL_MEANING.get(label, ""))}</span>
  </div>
  <div class="gauge">
    <i style="left:{pos:.0f}%"></i>
    <span class="gauge-tick" style="left:0">-100</span>
    <span class="gauge-tick" style="left:50%;transform:translateX(-50%)">0</span>
    <span class="gauge-tick" style="right:0">+100</span>
    <span class="gauge-end left">bearish</span>
    <span class="gauge-end right">bullish</span>
  </div>
  <div class="sent-note">Read from <b>{" and ".join(where)}</b>
    from the last {window} days</div>
</div>
<div class="sub-row">{sub_list}</div>
<div class="sent-summary">{_esc(s.get("summary", ""))}</div>
<div class="themes-label">Recurring topics</div>
<div class="themes">{themes}</div>
{_posts_block(s.get("posts") or [])}'''



def _teaser(body: str, limit: int = 190) -> str:
    """First sentence-worth of a briefing, as plain text.

    Headings and bullet markers are dropped, not rendered: this string is
    truncated to fit one line, and cutting inside a tag would ship broken
    markup to the lobby.
    """
    for raw in (body or "").split("\n"):
        line = strip_markdown(raw)
        # A heading reduces to a few words and says nothing on its own; keep
        # looking for the paragraph underneath it.
        if len(line.split()) < 5:
            continue
        if len(line) > limit:
            line = line[:limit].rsplit(" ", 1)[0] + "\u2026"
        return line
    # Every line was too short to be a paragraph (a briefing that is all
    # headings, or a one-line answer). Falling through to "" made the lobby
    # claim there was no briefing at all, which is worse than a short one:
    # take the longest line rather than nothing.
    lines = [strip_markdown(r) for r in (body or "").split("\n")]
    best = max((l for l in lines if l.strip()), key=len, default="")
    if len(best) > limit:
        best = best[:limit].rsplit(" ", 1)[0] + "\u2026"
    return best


# How the lobby can be ordered. The key is what travels in `?sort=`, the label
# is the chip, and the sentence is its tooltip.
#
# "Attention" is the default because it is what the product claims to do: the
# list used to come out alphabetical while the menu promised it was "ranked so
# the one that needs you is first", which was simply untrue. The other three
# are here because each answers a question the score deliberately blurs, and a
# single blended number is not auditable by eye.
SORTS = [
    ("attention", "Needs attention",
     "Insider filings and dilution first, then unusual sentiment, a coverage "
     "spike, and how far the price moved"),
    ("ticker", "A–Z", "Alphabetical by ticker"),
    ("move", "Price move", "Largest move today first, up or down"),
    ("coverage", "Coverage", "Most articles tracked first"),
]
SORT_KEYS = {k for k, _, _ in SORTS}
DEFAULT_SORT = "attention"


def _attention(b: dict) -> float:
    """How loudly one card is asking to be read. Higher sorts first.

    Deliberately a sum of independent signals rather than a model call: it runs
    on data already on the page, so the ordering is reproducible and a judge
    can check it against what the card shows. The weights say that a filed
    document outranks a mood, and a mood outranks a price tick.

    A company with nothing happening scores 0 and sinks, which is the point:
    the top of the list should be short.
    """
    score = 0.0

    # A filing is a fact someone had to sign, so it outranks everything else.
    # Weighted by kind: a sale or a dilution is why you would look today.
    for cls, label in (b.get("flags") or []):
        score += {"Dilution": 40.0, "Insider sold": 35.0,
                  "Activist stake": 30.0, "Insider bought": 25.0}.get(label, 15.0)

    # Sentiment counts by distance from neutral, not by direction: strongly
    # bearish and strongly bullish are both worth knowing. "quiet" and
    # "unavailable" carry no score at all rather than a weak one.
    sent = b.get("sentiment") or {}
    if sent.get("label") not in (None, "", "quiet", "unavailable"):
        score += min(abs(sent.get("score") or 0), 100) * 0.25

    # A coverage spike: today against the mean of the days before it. Being
    # written about twice as much as usual is the signal, not the raw count,
    # so a widely covered mega-cap does not permanently hold the top slot.
    cov = [c.get("articles") or 0 for c in (b.get("coverage") or [])]
    if len(cov) >= 3 and cov[-1]:
        base = sum(cov[:-1]) / len(cov[:-1])
        if base:
            score += max(0.0, min((cov[-1] / base) - 1.0, 3.0)) * 12.0

    # The price move is last and capped: it is the one signal already visible
    # at a glance on every card, and it is an outcome rather than a cause.
    chg = (b.get("quote") or {}).get("change_pct")
    if chg:
        score += min(abs(chg), 15.0) * 1.2

    return score


def sort_briefings(briefings: list[dict], key: str) -> list[dict]:
    """Order the lobby. Unknown keys fall back to the default rather than 500.

    Every sort breaks ties on ticker so the order is stable: without it two
    cards scoring the same swap places between refreshes, which reads as the
    page changing its mind.
    """
    key = key if key in SORT_KEYS else DEFAULT_SORT
    rows = list(briefings)
    if key == "ticker":
        return sorted(rows, key=lambda b: b["ticker"])
    if key == "move":
        return sorted(rows, key=lambda b: (
            -abs((b.get("quote") or {}).get("change_pct") or 0), b["ticker"]))
    if key == "coverage":
        return sorted(rows, key=lambda b: (
            -sum(c.get("articles") or 0 for c in (b.get("coverage") or [])),
            b["ticker"]))
    return sorted(rows, key=lambda b: (-_attention(b), b["ticker"]))


def _sort_chips(active: str) -> str:
    """The order control: one link per sort, the current one marked.

    Links and not a <select>: each ordering gets its own URL, so a view can be
    shared and the back button works. It also means the control needs no
    JavaScript to function.
    """
    out = []
    for key, label, tip in SORTS:
        on = ' class="on" aria-current="true"' if key == active else ""
        out.append(f'<a href="/lobby?sort={key}"{on} '
                   f'aria-label="Sort by {_esc(label)}: {_esc(tip)}">{_esc(label)}'
                   f'<span class="nav-tip">{_esc(tip)}</span></a>')
    return ('<div class="sorts"><span class="sorts-l">Sort</span>'
            + "".join(out) + "</div>")


def page_index(briefings: list[dict], last_run: dict | None = None,
               sort: str = DEFAULT_SORT) -> str:
    """The lobby: one line per ticker, enough to decide where to look.

    The detail lives on the ticker page. Repeating it here made the two pages
    read as the same screen twice, so the lobby keeps only what helps you
    choose: the price, whether anything happened, and the first line of the
    briefing.
    """
    # The freshness badge sits with the cards it dates, not in the header. It
    # is also what the in-flight reload watches for (`.updated.running`), so
    # the watchlist is the page that refreshes itself while a run lands, which
    # is the only page where that filling-in is visible.
    sort = sort if sort in SORT_KEYS else DEFAULT_SORT
    briefings = sort_briefings(briefings, sort)
    head = (f'<div class="list-head">{_sort_chips(sort) if briefings else ""}'
            f'{_updated_badge(last_run)}</div>')

    if not briefings:
        body = ('<div class="empty">Your watchlist is empty. '
                + ('Add a ticker below.' if adds_open()
                   else 'Adding is closed while watchlists are single-user.')
                + '</div>')
    else:
        cards = []
        for b in briefings:
            q = b.get("quote")
            cov = b.get("coverage") or []
            sent = b.get("sentiment") or {}
            flags = b.get("flags") or []

            # The teaser is the first line of real prose. Skipping headings
            # matters: a briefing that opens "## What happened" would otherwise
            # show its own section title as the summary, and markdown syntax is
            # stripped rather than escaped so the lobby never shows asterisks.
            first_line = _teaser(b.get("body") or "")

            chips = "".join(
                f'<span class="row-flag {cls}">{label}</span>' for cls, label in flags[:3]
            )
            label = sent.get("label", "")
            score = sent.get("score")
            sent_chip = (
                f'<span class="row-sent {label}">{label} {score:+d}</span>'
                if label and label not in ("quiet", "unavailable") and score is not None
                else ""
            )
            total = sum(c["articles"] for c in cov)

            # The sort keys travel with the card so the order can be changed
            # in the browser without another request. The server still sorts
            # (below), so the page is correct before any script runs and stays
            # correct if none does.
            cards.append(f"""<a class="row" href="/lobby/{_esc(b['ticker'])}"
  data-ticker="{_esc(b['ticker'])}" data-attention="{_attention(b):.4f}"
  data-move="{abs((q or {}).get('change_pct') or 0):.4f}" data-coverage="{total}">
  <div class="row-main">
    <div class="row-id"><span class="tk">{_esc(b['ticker'])}</span>
      <span class="co">{_esc(b['company_name'])}</span></div>
    <div class="row-flags">{chips}{sent_chip}</div>
    {_price_block(q)}
  </div>
  <div class="row-line">{_esc(first_line) if first_line else
    '<span style="color:var(--muted)">No briefing yet.</span>'}</div>
  <div class="row-meta">{total} article{'s' if total != 1 else ''} tracked
    &middot; {b.get('n_articles') or 0} cited in the briefing</div>
</a>""")
        # The cards get their own container. Without one, reordering in the
        # browser meant appending each card to `.wrap`, which is shared with
        # the "Add to watchlist" form below: every card moved to the end of
        # the page and the form ended up above them.
        body = '<div class="rows">' + "".join(cards) + "</div>"

    # Closed on purpose, and the inputs are disabled with it rather than left
    # live above a dead button: a form you can type into and not submit is
    # worse than one that plainly is not ready. `disabled` also keeps the
    # fields out of the POST, so nothing half-filled can be replayed.
    # When TICKERROOM_ALLOW_ADD=1 the endpoint accepts posts, so the button
    # has to open with it or the UI would hide a working feature.
    if adds_open():
        add = """<h2>Add to watchlist</h2>
<form class="add" method="post" action="/watchlist/add" data-busy="Researching&hellip;">
  <input name="ticker" placeholder="TICKER" style="width:120px" required>
  <input name="company_name" placeholder="Company name"
         style="flex:1;min-width:200px" required>
  <button class="btn">Add and research</button>
</form>
<p class="add-note">Adding starts a full research pass right away: news, Reddit,
analyst targets and filings, plus a standing hourly watch. The page comes back
straight away and fills in as each part lands, which usually takes two to four
minutes: the targets and filings stages are Parallel Task jobs that run for up
to five and six minutes respectively.</p>"""
    else:
        add = """<h2>Add to watchlist</h2>
<form class="add" aria-disabled="true">
  <input placeholder="TICKER" style="width:120px" disabled>
  <input placeholder="Company name" style="flex:1;min-width:200px" disabled>
  <button class="btn btn-ghost" disabled>Coming soon</button>
</form>
<p class="add-note">Watchlists are still single-user, and every add starts a
paid research pass. The form opens when watchlists are per-account.</p>"""
    return _shell("The Lobby \u00b7 The Ticker Room", head + body + add,
                  last_run, here="/lobby")


def _empty(what: str) -> str:
    """Placeholder for a section with no data yet.

    Sections are never hidden when empty. A missing block is indistinguishable
    from a block that found nothing, and a page whose shape changes per ticker
    reads as broken rather than as empty: a newly added ticker showed a bare
    card and no explanation of what was coming.
    """
    return (f'<div class="pending"><b>No {what} yet.</b>'
            f'<span>This fills in on the next scheduled pass, which runs twice '
            f'every weekday.</span></div>')


OVERVIEW_HINT = (
    "Everything worth knowing before you read further, in one card. The chips "
    "at the top are what would have woken you: a filing worth a look, a price "
    "target that has just moved, a consensus far from where the stock trades. "
    "A green wash is a move in the company's favour, a red one against it, "
    "amber a reading that is neither. Under them is the price and where it "
    "sits against its own recent history. Every figure has its own explainer."
)


def _overview_hint_h2() -> str:
    """The overview heading. Not in SECTIONS: it is not a reorderable block."""
    return ('<h2 class="sec-h2">Quick overview'
            f'<span class="hint">?<span class="hint-pop"><b>Quick overview</b>'
            f'{OVERVIEW_HINT}</span></span></h2>')


def _briefing_card(body: str, sources: list | None) -> str:
    """The briefing, clipped, with a control that expands it in place.

    The briefing is several hundred words and at full height it pushed the rest
    of the page below the fold. Clipped, it still answers "what is going on
    here" without displacing everything under it.

    The clip is CSS height plus a fade, not truncated text: the whole briefing
    is in the DOM, so Find-in-page, screen readers and printing all still see
    it, and the control only lifts the clip. There is deliberately no second
    copy of this text anywhere on the page.
    """
    return (
        '<div class="card teaser" data-teaser>'
        f'<div class="body teaser-body">{_paras(body, sources or [])}</div>'
        '<div class="teaser-fade"></div>'
        '<button type="button" class="fil-show teaser-more" data-more>'
        'Read the full briefing</button>'
        '</div>'
    )


def page_ticker(*, ticker, company_name, briefing, quote, articles, coverage,
                sentiment=None, targets=None, revisions=None, filings=None,
                events=None, monitor=None, alerts=None, order=None,
                last_run=None, watch_failed=0, watch_failed_at="") -> str:
    """One ticker page.

    Every section is always present, in the fixed order of `settings.SECTIONS`:
    what changes most often first, the raw sources last. `order` is accepted
    and ignored, kept so existing callers do not break.
    """
    from src.core.settings import SECTION_KEYS, SECTIONS

    q = quote or {}
    b_body = (briefing or {}).get("body")
    b_sources = (briefing or {}).get("sources") or []

    # Revisions are folded into the targets table rather than standing as their
    # own section above it. They were the same firms as the rows below, so the
    # page named each firm twice and left you to match them up by eye to see
    # which of the listed targets was the one that had just moved.
    tblock = _targets_block(targets or [], quote, revisions or [])
    fblock = _filings_block(filings or [])

    labels = dict(SECTIONS)
    targets_section = (_sec_h2("targets", labels["targets"])
                       + f'<div class="card">{tblock or _empty("analyst targets")}</div>')

    rows = "".join(
        f'<tr><td><a href="{_esc(a["url"])}" target="_blank" rel="noopener">'
        f'{_esc(a["title"] or a["url"])}</a></td>'
        f'<td class="date">{_esc((a["found_at"] or "")[:10])}</td></tr>'
        for a in articles
    )

    spark = _spark(coverage, articles=articles)
    gpanel = _panel(1, 260, ticker)
    blocks = {
        # One section, three parts of one question: what is watching, what it
        # found, and what crossed a threshold. They were three headings, so
        # answering "has anything happened" meant reading all three, and the
        # first two were largely furniture describing the third. Sub-heads
        # keep them apart inside one card, the same way Social & coverage
        # holds sentiment and volume. It leads the page because it is the
        # block that changes between visits.
        "alerts": (_sec_h2("alerts", labels["alerts"]) + '<div class="card">'
                   + f'<div class="sub-head">The standing watch'
                     f'{WATCH_HINT}</div>'
                   + _watch_block(monitor, ticker)
                   + f'<div class="sub-head wat-head">What it caught'
                     f'{CAUGHT_HINT}</div>'
                   + _events_block(events or [], ticker=ticker,
                                  failed=watch_failed,
                                  failed_at=watch_failed_at)
                   + f'<div class="sub-head wat-head">Alerts fired'
                     f'{ALERTS_FIRED_HINT}</div>'
                   # Said out loud because the rules aggregate over the whole
                   # watchlist: a row here can be about another holding, and a
                   # reader who assumed otherwise would misread it as this
                   # company's news.
                   + '<div class="help" style="margin:-2px 0 12px">Grafana'
                     ' rules run across the whole watchlist, so an alert here'
                     ' names the rule rather than the company.</div>'
                   + _alerts_fired(alerts or [], ticker=ticker)
                   + "</div>"),
        "filings": (_sec_h2("filings", labels["filings"])
                    + f'<div class="card">{fblock or _empty("filings")}</div>'),
        # No "briefing" here: it is rendered above the contents rail, not in
        # the column the rail indexes. It still has a SECTIONS entry so the
        # rail links to it.
        "targets": targets_section,
        # One section, two halves of one question: what people are saying, and
        # how much is being written. They were two blocks that each answered
        # half and neither said it was half. The old "Reddit sentiment" title
        # was wrong besides: the reading has always included X.
        "social": (_sec_h2("social", labels["social"]) + '<div class="card">'
                   + '<div class="sub-head">What people are posting</div>'
                   + (_sentiment_block(sentiment) if sentiment else _empty("sentiment"))
                   + f'<div class="sub-head cov-head">How much is being written'
                     f'{COVERAGE_HINT}</div>'
                   + (spark if spark else _empty("coverage history"))
                   # Empty when no Grafana is reachable (Cloud Run), so the
                   # spacer goes with it rather than leaving a gap.
                   + (f'<div style="margin-top:16px">{gpanel}</div>' if gpanel else "")
                   + "</div>"),
        "sources": (_sec_h2("sources", labels["sources"]) + '<div class="card">'
                    + (f"<table>{rows}</table>" if rows else _empty("sources"))
                    + "</div>"),
    }

    # The order is fixed in SECTIONS and no longer configurable, so this is
    # just "every block there is, in that order". `blocks` is filtered against
    # rather than trusted: the briefing has a SECTIONS entry for the rail but
    # is rendered above it, so it deliberately has no entry here.
    keys = [k for k in SECTION_KEYS if k in blocks]

    # Built from `keys`, which is the column beside the rail. The briefing is
    # deliberately absent: it is rendered ABOVE the rail, so an entry for it
    # would be a menu item that scrolls you backwards out of the list you are
    # reading, and the observer that highlights the current section can never
    # reach it. It is the first thing on the page and needs no menu entry.
    toc = "".join(
        f'<a href="#sec-{k}" data-sec="sec-{k}">{_esc(labels.get(k, k))}</a>'
        for k in keys
    )
    # "Back to top" is not a section, so it is not in the rail at all: it is a
    # floating control in the bottom-right corner, where it is reachable from
    # any scroll depth without first finding the rail. It also survives the
    # breakpoint that hides the rail, which is the width where a long page
    # needs it most.
    nav = (f'<nav class="toc" aria-label="Sections of this page">'
           f'<div class="toc-lab">{_esc(ticker)}</div>{toc}</nav>')
    sections = "".join(
        f'<section id="sec-{k}">{blocks[k]}</section>' for k in keys
    )

    strip = _alerts_strip(sentiment, targets, revisions, filings, quote)
    stats = ""
    if q.get("spot") is not None:
        cells = [
            ("Spot", f"${q['spot']:,.2f}"),
            ("Change", f"{q.get('change_pct', 0):+.2f}%"),
            ("MA20", f"${q['ma20']:,.2f}" if q.get("ma20") else "—"),
            ("MA50", f"${q['ma50']:,.2f}" if q.get("ma50") else "—"),
            ("52w low", f"${q['low_52w']:,.2f}" if q.get("low_52w") else "—"),
            ("52w high", f"${q['high_52w']:,.2f}" if q.get("high_52w") else "—"),
            ("Off 52w high",
             f"{q['pct_off_52w_high']:+.1f}%" if q.get("pct_off_52w_high") is not None else "—"),
        ]
        # The label is wrapped so it alone can be held on one line: putting
        # `nowrap` on the whole `<i>` leaked into the tooltip nested inside it.
        stats = '<div class="stats">' + "".join(
            f'<div class="stat"><i><span class="stat-label">{k}</span>'
            f'{_stat_hint(k)}</i><b>{v}</b></div>'
            for k, v in cells
        ) + "</div>"
    else:
        stats = f'<div class="pending-wrap">{_empty("price data")}</div>'

    # Price and the flags under one heading. They were two loose blocks above
    # the rail, each doing the same job of "what should I know before reading
    # on", and neither saying so. Full width, above the grid: the overview
    # describes the whole company rather than any one section, so it is not
    # something the contents rail should be running alongside.
    overview = (_overview_hint_h2() + '<div class="card overview">'
                + strip + stats + "</div>")

    # The briefing sits above the grid too, between the overview and the rail.
    # It is prose about the whole company, like the overview, rather than one
    # of the data blocks the rail indexes; and it is what you read first, so
    # it should not be one entry down a list of eight. It keeps its clip, so
    # being above the fold costs the reader nothing.
    briefing_block = (
        '<section id="sec-briefing">'
        + _sec_h2("briefing", "The briefing")
        + (_briefing_card(b_body, b_sources) if b_body
           else f'<div class="card">{_empty("briefing")}</div>')
        + "</section>"
    )

    body = f"""<a href="/" class="back" id="top">&larr; Back to the lobby</a>
<div class="card-top" style="margin:22px 0 20px">
  <div><div class="tk">{_esc(ticker)}</div><div class="co">{_esc(company_name)}</div></div>
  {_price_block(quote)}
</div>
{overview}
{briefing_block}
<div class="tk-body">{nav}<div class="tk-main">
{sections}
<form method="post" action="/watchlist/remove" class="rm">
  <input type="hidden" name="ticker" value="{_esc(ticker)}">
  <button class="btn-rm">Stop watching {_esc(ticker)}</button>
  <span>Cancels its continuous watch. The stored history is kept.</span>
</form>
</div></div>
<a class="to-top" href="#top" data-totop aria-label="Back to top">&uarr;</a>"""
    return _shell(f"{ticker} — The Ticker Room", body, last_run, here="/lobby",
                  extra_js=TOC_JS)


def page_settings(cfg: dict, last_run: dict | None = None, saved: bool = False) -> str:
    on = cfg.get("alerts_enabled") in ("1", "true", "on")
    reddit_on = cfg.get("reddit_enabled") in ("1", "true", "on")
    note = ('<div style="color:var(--up);font-size:12.5px;margin-bottom:16px">'
            "Saved.</div>" if saved else "")
    body = f"""<a href="/" class="back">&larr; Back to the lobby</a>
<h2 style="margin-top:22px">Settings</h2>{note}
<form method="post" action="/settings">
  <div class="card">
    <div class="frow"><label class="sw">
      <input type="checkbox" name="alerts_enabled" value="1"{" checked" if on else ""}>
      <span>Alert me on news coverage spikes</span></label></div>
    <div class="help">A spike is a day whose article count breaks well above this
      ticker's own recent baseline. The rule lives in Grafana, so the thresholds
      below are the ones it evaluates.</div>
    <div class="frow" style="margin-top:16px">
      <label class="sw">Spike when today exceeds baseline by
        <select name="spike_multiplier">
          {"".join(f'<option value="{v}"{" selected" if cfg.get("spike_multiplier") == v else ""}>{v}x</option>' for v in ["1.5", "2.0", "3.0"])}
        </select></label>
      <label class="sw">and is at least
        <select name="spike_floor">
          {"".join(f'<option value="{v}"{" selected" if cfg.get("spike_floor") == v else ""}>{v}</option>' for v in ["3", "5", "10"])}
        </select> articles</label>
    </div>
    <div class="help">The floor stops a quiet ticker going from 1 article to 3
      from counting as news.</div>
  </div>
  <div class="card">
    <div class="frow"><label class="sw">
      <input type="checkbox" name="reddit_enabled" value="1"{" checked" if reddit_on else ""}>
      <span>Read Reddit discussion for sentiment</span></label></div>
    <div class="help">Reddit threads are reached through Parallel, so no Reddit
      account or API credentials are involved.</div>
  </div>
  <div class="card">
    <div class="frow"><span class="sw">Research runs
      <b>twice every weekday</b></span></div>
    <div class="help">Fixed in the scheduler rather than chosen here: the times
      follow the US market, not a preference. Cloud Scheduler calls the run at
      09:45 and 17:45 New York time, Monday to Friday. Companies file most of
      their news in the hour after the close, so the evening run is the one that
      catches it. Set in New York time on purpose, because pinning it to a
      European clock would shift it twice a year.
      <br><br>Between those runs a Parallel Monitor watches each ticker every
      hour and pushes an event by webhook when something actually happens, so a
      filing does not have to wait for the next scheduled sweep. Grafana
      re-evaluates the alert rules every five minutes.</div>
  </div>
  <button class="btn">Save settings</button>
</form>"""
    return _shell("Settings — The Ticker Room", body, last_run, here="/settings")


# The contents rail marks where you are as you scroll. Pure enhancement: the
# links are real fragment anchors, so with the script blocked every one of them
# still jumps to its section.
TOC_JS = """<script>
(function () {
  var rail = document.querySelector(".toc");
  if (!rail || !window.IntersectionObserver) return;
  var links = {};
  rail.querySelectorAll("a[data-sec]").forEach(function (a) {
    links[a.getAttribute("data-sec")] = a;
  });
  var secs = Array.prototype.slice.call(document.querySelectorAll(".tk-main section"));
  if (!secs.length) return;

  /* The header is sticky and two rows tall, so the top of the viewport is not
     the top of the readable area. Measured rather than assumed: a hard-coded
     margin that is too small counts a section as visible while it is still
     behind the header, and the rail then lights the block above the one you
     are looking at. */
  /* The cutoff has to match where an anchor jump actually lands, which is the
     header height plus the scroll-margin the stylesheet adds. Using only the
     header height left a 16px band in which the section you had just jumped to
     was already on screen but not yet "visible" to the observer, so clicking a
     link lit the entry above the one you clicked. */
  var head = document.querySelector("header");
  var top = Math.round((head ? head.getBoundingClientRect().height : 0) + 20);
  /* The measurement is published back to CSS so the rail's sticky offset and
     the anchor scroll-margin use the same number this observer does. The
     stylesheet carries a sane default for the no-JS case, and it is only
     overridden once something real has been measured. */
  var body = document.querySelector(".tk-body");
  if (body && top > 20) body.style.setProperty("--head-h", (top - 20) + "px");

  /* The section you are in is the last one that has started above the reading
     line, not whichever one the observer happens to report as intersecting.
     Picking the topmost intersecting section is what an earlier version did,
     and it lit the block ABOVE the one on screen whenever a tall section was
     still straddling the line: its top is further up, so it kept winning.
     Sections do not overlap, so "the last one that has begun" is unambiguous.

     The observer is only a cheap way to be told the page moved; the decision
     is made from live geometry, so it stays right during smooth scrolling and
     after a resize. */
  /* `best` starts empty, not at the first section. The column now opens with
     the overview and the briefing teaser, which are not sections and have no
     rail entry: defaulting to secs[0] lit an entry for a block still a
     thousand pixels below, so the rail named a section you had not reached
     while you were reading one it did not list. Nothing is lit until the
     first real section crosses the reading line. */
  function mark() {
    var line = top, best = "";
    for (var i = 0; i < secs.length; i++) {
      if (secs[i].getBoundingClientRect().top <= line) best = secs[i].id;
      else break;
    }
    for (var k in links) links[k].classList.toggle("on", k === best);
  }
  var io = new IntersectionObserver(mark, {rootMargin: "-" + top + "px 0px 0px 0px",
    threshold: [0, 1]});
  secs.forEach(function (el) { io.observe(el); });
  /* The observer alone does not fire while scrolling through the middle of one
     long section, so the rail would freeze on it. Scroll drives the marking;
     the observer is what catches a late layout change (a lazy Grafana panel
     resizing a section under the pointer). */
  var queued = false;
  window.addEventListener("scroll", function () {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; mark(); });
  }, {passive: true});
  window.addEventListener("resize", mark, {passive: true});
  mark();
})();

/* The briefing's clip. There is only one copy of the briefing on the page now,
   so this control expands it in place; it never navigates. The clip is applied
   by CSS and lifted by a class, so a browser with the script blocked shows the
   briefing clipped with no control, which is why the whole text stays in the
   DOM: Find-in-page and print reach it either way. */
(function () {
  var card = document.querySelector("[data-teaser]");
  if (!card) return;
  var more = card.querySelector("[data-more]");
  if (!more) return;

  /* A briefing shorter than the clip needs no control: leaving it there
     offers to reveal text that is already fully on screen, and clicking it
     visibly does nothing. Measured rather than guessed from word count,
     because the height depends on the rendered width. */
  var inner = card.querySelector(".teaser-body");
  if (inner && inner.scrollHeight <= inner.clientHeight + 4) {
    more.hidden = true;
    var fade = card.querySelector(".teaser-fade");
    if (fade) fade.hidden = true;
    return;
  }

  more.addEventListener("click", function () {
    card.classList.add("open");
    more.hidden = true;
  });
})();

/* The floating "back to top". It is hidden until there is something to go back
   to, so it does not sit over the page at the very top where it would only be
   pointing at itself. One screenful is the threshold: below that the header is
   still in reach by scrolling normally. */
(function () {
  var b = document.querySelector("[data-totop]");
  if (!b) return;
  var queued = false;
  function show() {
    b.classList.toggle("on", window.scrollY > window.innerHeight * 0.75);
  }
  window.addEventListener("scroll", function () {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; show(); });
  }, {passive: true});
  show();
})();
</script>"""


# Kept out of the f-string in page_ask: JavaScript braces would be read as
# f-string placeholders.
ASK_JS = """<script>
(function () {
  var f = document.getElementById('askf'),
      w = document.getElementById('askw'),
      b = document.getElementById('askb'),
      i = f && f.querySelector('input[name=q]');
  if (!f || !w) return;

  function working() {
    w.hidden = false;
    if (b) { b.disabled = true; b.textContent = 'Asking\u2026'; }
  }

  f.addEventListener('submit', working);

  // A suggestion is a plain link, so the browser navigated first and the box
  // only filled once the new page arrived, ten to twenty seconds later: the
  // question appeared after its own answer. Put the text in the box and show
  // the banner now, then let the navigation happen a tick later.
  // Suggestions and history links both put their question in the box first.
  // A history link is served from storage and comes back in well under a
  // second, so it says "Looking it up" rather than promising twenty seconds.
  document.querySelectorAll('.ask-chip,.hist-i').forEach(function (a) {
    a.addEventListener('click', function (ev) {
      var q = a.getAttribute('data-q');
      if (!q || !i) { working(); return; }
      ev.preventDefault();
      i.value = q;
      if (a.classList.contains('hist-i')) {
        var lbl = w.querySelector('.aw-main');
        if (lbl) lbl.textContent = 'Looking it up\u2026';
        var sub = w.querySelector('.aw-sub');
        if (sub) sub.textContent = 'you have asked this before, so the answer is stored';
      }
      working();
      // A repaint has to land before the browser blocks on the request, or the
      // filled box and the banner are never actually drawn.
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { window.location.href = a.href; });
      });
    });
  });
})();
</script>"""

# What each tool reads, for the tooltip on the answer card. Named exactly as the
# agent's registry names them, so the trace and this list cannot drift apart.
TOOL_BLURBS = {
    "get_price": "the stored quote: spot, moving averages, 52-week range",
    "get_coverage_history": "how much has been written about it, day by day",
    "get_stored_articles": "the reporting already gathered for this ticker",
    "get_sentiment": "what Reddit has been saying, scored",
    "search_web": "the live web, through Parallel Search",
}

SUGGESTIONS = [
    "What's going on with ONDS lately?",
    "Which ticker is getting the most attention right now?",
    "How does Reddit sentiment on RDDT compare with the news coverage?",
    "Has anything unusual happened to AAPL in the last month?",
]


def _ticker_in(question: str, known: list[str]) -> str:
    """The watchlist ticker a question is about, if it names one.

    Matched against the watchlist rather than by pattern, because a bare
    all-caps word is a bad signal on its own: "What is going on with AI?" would
    otherwise be read as a ticker. Company names count too, so "what's up with
    Reddit" finds RDDT.
    """
    import re

    words = set(re.findall(r"[A-Za-z][A-Za-z.\-]*", question.upper()))
    for row in known:
        if (row.get("ticker") or "").upper() in words:
            return row["ticker"].upper()
    for row in known:
        name = (row.get("company_name") or "").upper()
        first = name.split()[0] if name else ""
        if len(first) > 3 and first in words:
            return row["ticker"].upper()
    return ""


def _price_strip(ticker: str) -> str:
    """The current price of the ticker a question is about.

    Shown above every answer that names a company, because an answer about a
    stock that does not say what it costs makes the reader open another tab,
    and the figure is already stored.
    """
    from src.core import repo

    q = repo.latest_quote(ticker) or {}
    spot = q.get("spot")
    if spot is None:
        return ""
    chg = q.get("change_pct")
    when, stale = _ago(q.get("captured_at"))
    cls = "up" if (chg or 0) > 0 else "down" if (chg or 0) < 0 else "flat"
    sign = "+" if (chg or 0) > 0 else ""
    move = (f'<span class="ap-chg {cls}">{sign}{chg:.2f}%</span>'
            if chg is not None else "")
    return (
        f'<a class="ask-price" href="/lobby/{_esc(ticker)}">'
        f'<span class="ap-t">{_esc(ticker)}</span>'
        f'<span class="ap-spot">${spot:,.2f}</span>{move}'
        f'<span class="ap-when{" stale" if stale else ""}">{when}</span></a>'
    )


def _current_search(query: str, peers: str) -> str:
    """The search this page is showing, phrased the way it was stored.

    A peer search has no typed query: it is filed as "Companies like ONDS", so
    matching on `query` alone would leave a peer search listing itself.
    """
    if query.strip():
        return query.strip()
    return f"Companies like {peers.upper()}" if peers.strip() else ""


def _history_block(rows: list[dict], *, kind: str, current: str = "") -> str:
    """Questions already asked, newest first, each a link back to its answer.

    Worth showing for two reasons. A question costs twenty seconds and a paid
    API call, so re-asking one by hand is money spent on an answer already
    given. And a research tool with no record of what was researched makes the
    reader keep that list themselves, which is the work it exists to remove.

    `current` is the question already on the page, and it is excluded: a list of
    "other things you asked" that leads with the thing you are looking at is
    offering to take you where you already are.
    """
    if not rows:
        return ""
    seen: set[str] = {current.strip().lower()} if current.strip() else set()
    items = []
    for row in rows:
        q = (row.get("question") or "").strip()
        # The same question asked twice is one entry: the newest wins, because
        # its answer reflects the newest data.
        key = q.lower()
        if not q or key in seen:
            continue
        seen.add(key)
        when, _ = _ago(row.get("asked_at"))
        if kind == "discover":
            n = row.get("n_results") or 0
            meta = f"{n} found"
            # The stored run ids replay the search Parallel already ran and
            # still holds. Without them the link would start three fresh
            # FindAll runs, which take minutes and are the priciest call here.
            stored = (row.get("answer") or "").strip()
            peers_q = quote_plus(row["ticker"]) if row.get("ticker") else ""
            if stored.startswith("run:"):
                href = f"/discover?run={_esc(quote_plus(stored[4:]))}"
            elif stored:
                href = f"/discover?runs={_esc(quote_plus(stored))}"
            else:
                # Older rows predate the run ids and can only be re-run.
                href = (f"/discover?peers={_esc(peers_q)}" if peers_q
                        else f"/discover?q={_esc(quote_plus(q))}")
            if stored and peers_q:
                href += f"&amp;peers={_esc(peers_q)}"
            elif stored and not row.get("ticker"):
                href += f"&amp;q={_esc(quote_plus(q))}"
        else:
            tools = [t for t in (row.get("tools") or []) if t]
            meta = f"{len(tools)} tool{'s' if len(tools) != 1 else ''}" if tools else "no tools"
            href = f"/ask?q={_esc(quote_plus(q))}"
        items.append(
            f'<a class="hist-i" href="{href}" data-q="{_esc(q)}">'
            f'<span class="hist-q">{_esc(q)}</span>'
            f'<span class="hist-m">{_esc(meta)}</span>'
            f'<span class="hist-w">{when}</span></a>'
        )
    if not items:
        return ""
    noun = "searches" if kind == "discover" else "questions"
    # Says "reads back" and not "asks again" because that is what happens: the
    # stored answer is served, labelled with its age, and "ask again" on the
    # answer itself is the way to pay for a fresh one. Promising a re-run here
    # would misdescribe both the speed and the cost.
    back = ("Opening one reads back the result already paid for."
            if kind == "discover" else
            "Opening one reads back the stored answer, labelled with its age.")
    return (f'<h2 class="hist-h">Asked before</h2>'
            f'<div class="help" style="margin:-6px 0 12px">Your last '
            f'{len(items)} {noun}. {back}</div>'
            f'<div class="hist">{"".join(items)}</div>')


def _further_reading(second: dict | None, ticker: str, want: int = 6) -> list[dict]:
    """Sources to read next: what Parallel just found, then what we hold.

    Two sources because neither is enough alone. Responses returns whatever it
    cited, which is often only two or three URLs and carries no title and no
    date, so a list built from it alone is short and unlabelled. The stored
    articles have both, and are the same reporting the briefing was written
    from. Live citations come first because they are the newest thing on the
    page; stored ones fill the list out to a useful length.
    """
    from src.core import repo

    titled: list[dict] = []      # has a real headline
    bare: list[dict] = []        # a URL and nothing else
    seen: set[str] = set()

    def add(url: str, title: str, when: str) -> None:
        # Compared without scheme or trailing slash: Responses returns http://
        # for pages we stored as https://, and the same article listed twice
        # reads as sloppiness rather than as two sources.
        key = url.split("://", 1)[-1].rstrip("/").lower()
        if not url or key in seen:
            return
        seen.add(key)
        title = " ".join(title.split())
        # A row whose headline is just its own domain gives the reader nothing
        # to choose by, so those are held back and only used to pad the list.
        if len(title) >= 12:
            titled.append({"url": url, "title": title, "when": when})
        else:
            bare.append({"url": url, "title": _host(url), "when": when})

    for src in (second or {}).get("sources") or []:
        add(src.get("url", ""), src.get("title") or "", "just now")

    if ticker:
        try:
            for art in repo.recent_articles(ticker, 25):
                when, _ = _ago(art.get("found_at"))
                add(art.get("url", ""), art.get("title") or "", when)
        except Exception as exc:  # noqa: BLE001 - further reading is optional
            print(f"[ask] further reading: {exc}")

    # Headlines first regardless of where they came from. Responses cites its
    # sources without titles, so ordering by provenance filled the whole list
    # with rows reading "ir.ondas.com" and pushed out every stored article that
    # had an actual headline and a date.
    return (titled + bare)[:want]


def page_ask(question: str, result: dict | None, last_run: dict | None = None,
             *, second: dict | None = None,
             history: list[dict] | None = None, cached_at: str = "") -> str:
    """The analyst agent page.

    Three things the earlier version got wrong, all of them the same mistake in
    different places: the page did not say what it was doing.

    - The answer card opened straight into prose, so on a page that can hold
      two answers there was nothing saying which question either belonged to.
      The question is now the card's heading.
    - Pressing a suggestion looked like nothing had happened. The agent takes
      ten to twenty seconds, and with no spinner the honest reading was that
      the click had missed. The form now shows it is working.
    - An answer about a company never said what that company costs, which is
      the one figure a reader would look up next.
    """
    from src.core import repo

    chips = "".join(
        f'<a class="ask-chip" href="/ask?q={_esc(quote_plus(s))}" '
        f'data-q="{_esc(s)}">{_esc(s)}</a>'
        for s in SUGGESTIONS
    )

    try:
        ticker = _ticker_in(question, repo.get_watchlist("javi")) if question else ""
    except Exception:  # noqa: BLE001 - a missing price must not break the page
        ticker = ""

    block = ""
    if result:
        if result.get("error"):
            # A raw "NoCredit: POST /v1beta/search -> 402: {...}" on screen
            # reads as a broken product rather than an account to top up, which
            # is the same mistake Discover already fixed. The exception text is
            # kept underneath, because it is what makes the failure diagnosable.
            raw = result["error"]
            if "NoCredit" in raw or "402" in raw:
                lead = ("The research APIs are out of credit, so this question "
                        "could not be answered from live sources. Stored "
                        "answers still open instantly from the list below.")
            else:
                lead = "That question could not be answered."
            block = (f'<div class="card"><div style="color:var(--amber)">'
                     f'<b>{_esc(lead)}</b></div>'
                     f'<div class="help" style="margin-top:10px">'
                     f'{_esc(raw)}</div></div>')
        else:
            price = _price_strip(ticker) if ticker else ""

            # The answer is markdown, and it used to be escaped line by line, so
            # "**Price & Market Context**" reached the page as literal asterisks.
            answer = _cite_paragraphs(result.get("answer") or "", [])
            trace = result.get("trace") or []
            n_tools = len(trace)
            tools_note = (
                f'{n_tools} tool{"s" if n_tools != 1 else ""} used'
                if n_tools else "answered without tools")
            # The tools it actually chose, in the order it chose them, each with
            # what it reads. A count alone said the agent did something without
            # saying what, which is the part worth showing.
            steps = "".join(
                f'<li><b>{_esc(t.get("tool", ""))}</b>'
                f'{_esc(TOOL_BLURBS.get(t.get("tool", ""), ""))}</li>'
                for t in trace
            )
            # A stored answer says so, and offers the way to a fresh one.
            # Presenting an answer from an hour ago as if it had just been
            # worked out is the same lie the stale-price badge exists to stop.
            when_asked, _stale = _ago(cached_at) if cached_at else ("", False)
            stamp = (
                f'<div class="ask-cached">Answered {when_asked}, shown from '
                f'your history &middot; '
                f'<a href="/ask?q={_esc(quote_plus(question))}&amp;again=1">'
                f'ask again</a></div>' if cached_at else "")
            block = f"""<div class="card ask-answer">
  <div class="ask-head">
    <h3 class="ask-q">{_esc(question)}</h3>
    <span class="ask-by" tabindex="0">Gemini agent &middot; {tools_note}
      <span class="ask-tip">
        <b>How this was answered</b>
        A Gemini agent picked its own tools for this question. Four read what
        this service has stored; <i>search_web</i> goes to the live web through
        Parallel Search. It never states a figure it did not get from a tool.
        {f'<ul class="tip-tools">{steps}</ul>' if steps
         else '<span class="tip-none">It answered without calling a tool.</span>'}
      </span>
    </span>
  </div>
  {price}
  {stamp}
  <div class="body">{answer}</div>
</div>"""

    # The second opinion. Links only, not a second essay: two full answers to
    # the same question left the reader arbitrating between them, which is work
    # the page was supposed to save. What Responses is genuinely good for here
    # is showing what the open web has right now, so it contributes its sources.
    srcs = _further_reading(second, ticker if result and not result.get("error") else "")
    if srcs:
        links = "".join(
            f'<a class="so-link" href="{_esc(src["url"])}" target="_blank" '
            f'rel="noopener"><span class="so-host">{_esc(_host(src["url"]))}</span>'
            f'<span class="so-title">{_esc(src["title"])}</span>'
            f'<span class="so-date">{_esc(src["when"])}</span></a>'
            for src in srcs
        )
        if links:
            block += f"""
<div class="card so">
  <div class="so-head">
    <b>Read more</b>
    <span class="so-note" tabindex="0">where to check this
      <span class="ask-tip">
        <b>Where these come from</b>
        The ones marked <i>just now</i> are what Parallel&#8217;s Responses API
        cited when asked this same question against the open web, seconds ago.
        The rest are the reporting this service already gathered, newest first,
        with the age of each. Nothing here has been summarised: they are the
        pages themselves, so the answer above can be checked against them.
      </span>
    </span>
  </div>
  <div class="so-links">{links}</div>
</div>"""

    # No "Back to the lobby" link: this page is in the main nav, so the header
    # already says where it sits and offers every other destination.
    body = f"""<h2 style="margin-top:0">Ask the analyst</h2>
<p class="help" style="margin:-6px 0 18px;max-width:640px">An agent with tools over
  your stored history and the live web. It decides what to look up.</p>
<form class="ask-form" method="get" action="/ask" id="askf">
  <input name="q" value="{_esc(question)}" placeholder="Ask about a ticker&hellip;" autofocus>
  <button class="btn" id="askb">Ask</button>
</form>
<div class="ask-eg">
  <span class="ask-eg-label">Try</span>
  <div class="ask-chips">{chips}</div>
</div>
<div class="ask-working" id="askw" hidden>
  <span class="aw-dot"></span>
  <span><span class="aw-main">Asking the analyst&hellip;</span>
    <span class="aw-sub">it reads the stored
    history and the live web, which takes ten to twenty seconds</span></span>
</div>
{block}
{_history_block(history or [], kind="ask", current=question)}"""
    return _shell("Ask \u2014 The Ticker Room", body, last_run, here="/ask",
                  extra_js=ASK_JS)


def _evidence_hint(row: dict) -> str:
    """A hover card showing where an extracted row came from.

    Targets and filings are not reported facts, they are extractions: a model
    read a page and wrote down a number. This product once badged an insider
    *sale* as a purchase, and the reader had no way to tell. Showing the source
    sentence and Parallel's own confidence turns "trust it" into "check it".
    """
    from src.core import evidence as ev

    cite = row.get("evidence")
    if isinstance(cite, str):
        cite = ev.loads(cite)
    if isinstance(cite, list):
        cite = cite[0] if cite else None
    confidence = (row.get("confidence") or "").lower()
    if not cite and not confidence:
        return ""

    cite = cite or {}
    # Cleaned on the way out as well as on the way in: rows stored before the
    # excerpt cleaner existed still carry raw markdown, and re-running every
    # extraction to repair them would cost more than rendering them properly.
    excerpt = ev.clean_excerpt(cite.get("excerpt") or "")
    reasoning = ev.clean_excerpt(cite.get("reasoning") or "")
    host = _host(cite.get("url", "")) if cite.get("url") else ""

    inner = ""
    if confidence:
        inner += f'<b>Parallel confidence: {_esc(confidence)}</b>'
    # The quote first, then where it came from: the source is a footnote to the
    # sentence, not a heading for it.
    if excerpt:
        inner += f'<em>&ldquo;{_esc(excerpt[:240])}&rdquo;</em>'
    elif reasoning:
        inner += f'<em>{_esc(reasoning[:240])}</em>'
    if host:
        inner += f'<i>{_esc(host)}</i>'
    if not inner:
        return ""
    return f'<span class="hint ev-hint">?<span class="hint-pop">{inner}</span></span>'


# How many target rows show before the "show more" button, matching the
# filings table. The rest are rendered hidden, not dropped.
TARGETS_SHOWN = 10


def _target_pop(t: dict, rev: dict | None = None) -> str:
    """What one dot on the scale is: which firm put that price there.

    The dots used to carry a `title`, which is a native tooltip: it appears
    after a delay the browser chooses, cannot be styled, and cannot hold a
    link. A real popup can say the firm, the call, the date and where it was
    published, which is the whole question the dot raises.
    """
    inner = f'<b>{_esc(t["firm"])}</b>'
    line = f'${t["target_price"]:,.2f}'
    if t.get("rating"):
        line += f' &middot; {_esc(t["rating"])}'
    inner += f'<em>{line}</em>'
    if rev:
        cls = "up" if rev["change_pct"] > 0 else "down"
        arrow = "&uarr;" if rev["change_pct"] > 0 else "&darr;"
        inner += (f'<em class="{cls}">Revised from ${rev["old_price"]:,.2f} '
                  f'{arrow} {rev["change_pct"]:+.0f}%</em>')
    if t.get("analyst"):
        inner += f'<em>{_esc(t["analyst"])}</em>'
    if t.get("date"):
        inner += f'<i>{_esc(t["date"])}</i>'
    # The source is the answer to "says who", so it is a real link, not a
    # hostname in grey. pointer-events are off on the popup by default or the
    # link could never be reached, so this one turns them back on.
    #
    # And it is labelled as the reporter, not as the firm. Research notes are
    # sold, not published: Goldman does not put its target on a public page, so
    # what is web-reachable is always somebody reporting it. A bare
    # "stockanalysis.com" under a Goldman target invited the reading that the
    # site was the analyst, which is the wrong question to leave open.
    if t.get("source_url"):
        inner += (f'<a href="{_esc(t["source_url"])}" target="_blank" '
                  f'rel="noopener">Reported by {_esc(_host(t["source_url"]))} '
                  f'&rarr;</a>')
    return inner


def _targets_block(targets: list[dict], quote: dict | None,
                   revisions: list[dict] | None = None) -> str:
    """Analyst price targets against the live price.

    A target is only meaningful next to the current price: "$270" says little,
    "$270, which is 76% above today" says what the analyst is actually claiming.

    One row per firm. `latest_targets` returns the raw rows, so a firm that
    published four times was four rows, four dots stacked on the same spot and
    four votes in what the page called "the average of 30 analyst targets".
    Bernstein counted four times and the consensus was not the consensus.
    """
    if not targets:
        return ""
    from src.core.targets import canonical_firm, latest_per_firm

    targets = latest_per_firm(targets)
    spot = (quote or {}).get("spot")
    prices = [t["target_price"] for t in targets]
    low, high = min(prices), max(prices)
    avg = sum(prices) / len(prices)
    span = (high - low) or 1

    # A revision belongs to the firm that made it, and both sides are keyed
    # the same way `latest_per_firm` groups, so the two line up by firm.
    by_firm = {canonical_firm(r["firm"]): r for r in (revisions or [])}

    def pos(v: float) -> float:
        return max(0.0, min(100.0, (v - low) / span * 100))

    spot_marker = ""
    if spot and low <= spot <= high:
        # The "now" marker and the two end labels share the strip below the
        # rail. When the price sits near either end they print on top of each
        # other ("$142.00" under "$154.46"), so the end label it collides with
        # is dropped: the marker carries a price of its own and is the more
        # useful of the two.
        p = pos(spot)
        hide = " hide-left" if p < 18 else (" hide-right" if p > 82 else "")
        spot_marker = (f'<span class="tgt-spot{hide}" style="left:{p:.1f}%">'
                       f'<b>${spot:,.2f}</b><i>now</i></span>')

    dots = []
    for t in targets:
        rev = by_firm.get(canonical_firm(t["firm"]))
        cls = ""
        if rev:
            cls = " raised" if rev["change_pct"] > 0 else " cut"
        dots.append(
            f'<span class="tgt-dot{cls}" style="left:{pos(t["target_price"]):.1f}%">'
            f'<span class="hint-pop tgt-pop">{_target_pop(t, rev)}</span></span>'
        )

    headline = ""
    if spot:
        gap = (avg - spot) / spot * 100
        cls = "up" if gap >= 0 else "down"
        headline = (f'<span class="tgt-gap {cls}">{gap:+.0f}%</span>'
                    f'<span class="tgt-gap-note">between today and the average target</span>')

    rows = []
    for i, t in enumerate(targets):
        rev = by_firm.get(canonical_firm(t["firm"]))
        # A firm that just moved its own target says more than its level does,
        # so the move rides in the same row rather than in a separate table
        # that repeats the firm name and makes you match them up by eye.
        move = ""
        pcls = ""
        if rev:
            pcls = " up" if rev["change_pct"] > 0 else " down"
            arrow = "&uarr;" if rev["change_pct"] > 0 else "&darr;"
            move = (f'<span class="rev-move"><span class="rev-old">'
                    f'${rev["old_price"]:,.2f}</span> {arrow} '
                    f'<b class="rev-pct{pcls}">{rev["change_pct"]:+.0f}%</b></span>')
        extra = ' class="tgt-more" hidden' if i >= TARGETS_SHOWN else ""
        rows.append(
            f'<tr{extra}><td>{_link(t.get("source_url"), _esc(t["firm"]))}'
            + (f'<span class="tgt-analyst">{_esc(t["analyst"])}</span>'
               if t.get("analyst") else "")
            + f'</td><td class="tgt-rating">{_esc(t.get("rating", ""))}</td>'
            f'<td class="tgt-price{pcls}">${t["target_price"]:,.2f}'
            f'{_evidence_hint(t)}</td>'
            # A column only exists when something can fill it: with no
            # revisions the header stood over an empty strip the whole way
            # down, which reads as data that failed to load.
            + (f'<td class="tgt-rev">{move}</td>' if by_firm else "")
            + f'<td class="date">{_esc(t.get("date", ""))}</td></tr>'
        )

    head = ('<tr class="fil-head"><th>Firm</th><th>Rating</th>'
            '<th>Price target</th>'
            + ('<th>Recent change</th>' if by_firm else '')
            + '<th style="text-align:right">Dated</th></tr>')

    hidden = max(0, len(rows) - TARGETS_SHOWN)
    # Wrapped in .more-wrap so the button centres under a fade, the same shape
    # the briefing uses: all three are the one gesture of "there is more of
    # this below". The fade is a sibling of the button rather than part of the
    # table, because the table's own rows must stay untinted.
    more = (f'<div class="more-wrap" hidden><div class="more-fade"></div>'
            f'<button type="button" class="fil-show">Show {hidden} more '
            f'{"firm" if hidden == 1 else "firms"}</button></div>') if hidden else ""

    n_rev = len(by_firm)
    rev_note = ""
    if n_rev:
        rev_note = (f' Firms that moved their own target are marked in the '
                    f'<b>Recent change</b> column: {n_rev} of them here.')

    return f"""<div class="tgt-head">
  <div><span class="tgt-avg">${avg:,.2f}</span>
    <span class="tgt-avg-note">average of {len(targets)} analyst targets</span></div>
  <div class="tgt-gap-wrap">{headline}</div>
</div>
<div class="tgt-scale">
  {"".join(dots)}{spot_marker}
  <span class="tgt-end left">${low:,.2f}</span>
  <span class="tgt-end right">${high:,.2f}</span>
</div>
<div class="tbl-scroll"><table class="tgt-table tgt-list">{head}{"".join(rows)}</table></div>{more}
<div class="help">One row per firm, its most recent published target, extracted
  with Parallel's Task API. Hover a dot on the scale for the firm behind that
  price and a link to where it was reported, or the <b>?</b> next to a price
  for the sentence it was read from and Parallel's confidence in it.{rev_note}
  <b>The link is to whoever reported the target, not to the firm.</b> Sell-side
  research is sold to clients rather than published, so a firm's own note is
  not on the open web: what is reachable is the aggregator or news outlet that
  carried it, and that is what is cited, since citing a page nobody can open
  would be worse. They are what analysts said, not a forecast of ours, and a
  target is not a recommendation.</div>"""


KIND_STYLE = {
    "insider-sell": ("down", "Sold"),
    "insider-buy": ("up", "Bought"),
    "grant": ("", "Grant"),
    "dilution": ("down", "Dilution"),
    "activist": ("amber", "Activist stake"),
}

# How many filings the table shows before the "show more" button. Ten is about
# a screen; the rest are rendered hidden, not dropped.
FILINGS_SHOWN = 10

FILING_HINTS = {
    "shares": "Number of shares in the transaction. \"sh\" is short for shares.",
    "date": "The date the filing was submitted to the SEC. Insiders must file a "
            "Form 4 within two business days of the trade, so the trade itself "
            "happened on or shortly before this date.",
    "form": "The type of SEC document. Form 4 reports an insider's trade; S-3, "
            "S-1 and 424B5 register or price new shares, which dilutes existing "
            "holders; 8-K reports a material event.",
}


def _filing_hint(key: str, label: str) -> str:
    text = FILING_HINTS.get(key)
    if not text:
        return ""
    return (f'<span class="hint">?<span class="hint-pop"><b>{_esc(label)}</b>'
            f'{_esc(text)}</span></span>')


def _filings_block(filings: list[dict]) -> str:
    """SEC filings: the hardest information on the page.

    A Form 4 is a filed document with a date, not an interpretation, so it is
    shown plainly: who, what they did, how much, and when.
    """
    if not filings:
        return ""

    from src.core.filings import classify

    rows = []
    for i, f in enumerate(filings[:FILINGS_SHOWN * 3]):
        kind = classify(f)
        cls, badge = KIND_STYLE.get(kind, ("", ""))
        who = f.get("insider_name") or ""
        if who.lower() in ("n/a", "-", "none"):
            who = ""
        role = f.get("insider_role") or ""
        value = f.get("value_usd")
        shares = f.get("shares")

        amount = ""
        if value:
            amount = f"${value:,.0f}"
        elif shares:
            amount = f"{shares:,.0f} sh"

        # Everything past the first ten is in the table but hidden, so the
        # button reveals what is already there rather than fetching anything.
        extra = ' class="fil-more" hidden' if i >= FILINGS_SHOWN else ""
        rows.append(
            f'<tr{extra}><td class="date">{_esc(f.get("filed_date", ""))}'
            f'<span class="fil-form-sm">{_esc(f["form_type"])}</span></td>'
            f'<td class="fil-form"><b>{_esc(f["form_type"])}</b></td>'
            f'<td>{_link(f.get("source_url"), _esc(f.get("headline", ""))[:170])}'
            + (f'<span class="fil-who">{_esc(who)}'
               + (f' &middot; {_esc(role)}' if role else "") + "</span>" if who else "")
            + "</td>"
            + (f'<td><span class="fil-badge {cls}">{badge}</span>'
               f'{_evidence_hint(f)}</td>'
               if badge else "<td></td>")
            + f'<td class="fil-amount {cls}">{amount}</td></tr>'
        )

    # Filed date leads: on a list of filings the question is always "how recent
    # is this", and the form type only means something once you know the date.
    head = (f'<tr class="fil-head"><th>Filed{_filing_hint("date", "Filed date")}</th>'
            f'<th>Form{_filing_hint("form", "Form type")}</th>'
            f'<th>What was filed</th><th></th>'
            f'<th style="text-align:right">Size{_filing_hint("shares", "Size")}</th></tr>')

    hidden = max(0, len(rows) - FILINGS_SHOWN)
    # Without JS the button never appears and every row stays hidden, which
    # would lose filings silently, so the rows are revealed by a <noscript>
    # rule and the button is only shown once the script has run.
    more = (f'<div class="more-wrap" hidden><div class="more-fade"></div>'
            f'<button type="button" class="fil-show" data-count="{hidden}">'
            f'Show {hidden} more '
            f'{"filing" if hidden == 1 else "filings"}</button></div>') if hidden else ""

    # The filings table has columns that must not wrap (form type, size, date),
    # so below about 430px it cannot compress any further. It scrolls inside its
    # own box rather than taking the page with it.
    return (f'<div class="tbl-scroll"><table class="tgt-table fil-table">'
            f'{head}{"".join(rows)}</table></div>{more}'
            '<div class="help">Filings with the U.S. Securities and Exchange '
            'Commission, extracted with Parallel\'s Task API. Hover the <b>?</b> '
            'beside a badge for the source sentence behind a buy or sell call '
            'and Parallel\'s confidence in it. Reported as filed: executives '
            'sell for many reasons, including scheduled plans and tax on vesting '
            'shares, so a sale is not a signal on its own.</div>')


def _alerts_strip(sentiment, targets, revisions, filings, quote) -> str:
    """What would have woken you, gathered in one row at the top of the page."""
    from src.core.filings import notable

    items = []
    for e in notable(filings or [])[:3]:
        cls, badge = KIND_STYLE.get(e["kind"], ("", e["kind"]))
        who = e.get("insider_name") or ""
        label = {"insider-sell": "Insider sold", "insider-buy": "Insider bought",
                 "dilution": "Dilution filed",
                 "activist": "Activist stake"}.get(e["kind"], badge)
        # `insider_name` and `headline` are model output read off scraped
        # pages, so they are escaped here rather than trusted. The separator
        # stays a literal entity: escaping it would print "&middot;".
        items.append((cls,
                      label,
                      f"{_esc(who)} &middot; {_esc(e.get('filed_date', ''))}" if who
                      else _esc(e.get("headline", "")[:60])))

    for r in (revisions or [])[:2]:
        up = r["change_pct"] > 0
        items.append(("up" if up else "down",
                      "Target raised" if up else "Target cut",
                      f'{_esc(r["firm"])} ${r["old_price"]:,.0f} '
                      f'&rarr; ${r["new_price"]:,.0f}'))

    spot = (quote or {}).get("spot")
    if targets and spot:
        prices = [t["target_price"] for t in targets]
        avg = sum(prices) / len(prices)
        gap = (avg - spot) / spot * 100
        if abs(gap) > 30:
            items.append(("up" if gap > 0 else "down", "Consensus gap",
                          f"{gap:+.0f}% vs average target"))

    if not items:
        return ""
    chips = "".join(
        f'<div class="alert-chip {cls}"><b>{badge}</b><span>{text}</span></div>'
        for cls, badge, text in items[:5]
    )
    return f'<div class="alert-strip">{chips}</div>'


def _link(url: str | None, text: str) -> str:
    """Wrap text in a link when there is somewhere to go."""
    if not url:
        return text
    return (f'<a href="{_esc(url)}" target="_blank" rel="noopener" '
            f'class="src-link">{text}</a>')


def _when(iso: str) -> str:
    """A short, human date for an event. Falls back to the raw string."""
    raw = (iso or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return _esc(raw[:16])
    return dt.strftime("%d %b %H:%M")


def _events_block(events: list[dict], ticker: str = "",
                  failed: int = 0, failed_at: str = "") -> str:
    """A timeline of what the continuous watch caught between runs.

    `ticker` scopes the block to one company: it adjusts the empty copy and
    drops the per-row symbol badge, because on a company's own page every row
    is that company and repeating the symbol is noise.

    `failed` is how many of the watch's recent runs could not run at all.
    Parallel reports those inside the events list rather than as a failed call,
    so without this an account that has been out of credit for days shows the
    same empty box as a quiet week. Measured: 19 consecutive hourly failures on
    ONDS read as silence.
    """
    if not events and failed:
        when = f" The most recent was {_esc(failed_at[:16])}." if failed_at else ""
        return ('<div class="empty" style="border-color:var(--down);'
                'color:var(--down)"><b>The watch could not run.</b><br>'
                f'{failed} recent hourly runs failed rather than finding '
                f'nothing.{when} This is usually an exhausted Parallel '
                'balance; the box stays empty until the watch can run again.'
                '</div>')
    if not events:
        who = f"{ticker} " if ticker else "a watched company "
        # Says what fills this box AND what does not: the two blocks below it
        # were being read as the same thing, so an empty watch next to a
        # populated "Alerts fired" looked like a fault rather than two
        # different systems reporting different things.
        return ('<div class="empty">Nothing caught yet. Parallel checks hourly '
                f'and posts here when {who}actually moves. This box only fills '
                'from that watch, so it stays empty on a quiet day even while '
                'the Grafana rules below are firing.</div>')
    out = []
    for e in events:
        sources = "".join(
            f'<a href="{_esc(c.get("url", ""))}" target="_blank" rel="noopener">'
            f'{_esc(_host(c.get("url", "")))}</a>'
            for c in (e.get("citations") or [])[:4] if c.get("url")
        )
        badge = "" if ticker else (
            f'<a class="ev-tk" href="/lobby/{_esc(e["ticker"])}">{_esc(e["ticker"])}</a>')
        out.append(
            f'<div class="ev"><div class="ev-top">{badge}'
            f'<span class="ev-when">{_when(e.get("event_date") or e.get("received_at", ""))}</span>'
            f'</div><div class="ev-text">{_esc(e.get("text", "")[:600])}</div>'
            + (f'<div class="ev-src">{sources}</div>' if sources else "")
            + "</div>"
        )
    return "".join(out)


def _host(url: str) -> str:
    import re

    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else "source"


def _watch_block(monitor: dict | None, ticker: str) -> str:
    """The standing Parallel watch for one ticker, and the manual pull.

    This was a table of every monitor on its own page. One row per ticker on a
    screen that already listed every ticker was the same list twice, so it now
    sits on the page for the company it watches, where "is this one being
    watched, and when did it last look" is the question actually being asked.
    """
    if not monitor:
        return ('<div class="empty">No watch yet for ' + _esc(ticker)
                + '. One is created on the next run.</div>')

    active = monitor.get("status") == "active"
    right = (f'<div>every {_esc(monitor.get("frequency", "?"))} &middot; '
             f'{_esc(monitor.get("processor", ""))}</div>'
             if active
             else '<div style="color:var(--muted)">no longer watched</div>')
    rows = (f'<div class="mon"><div>'
            f'<span class="dot {"live" if active else "off"}"></span>'
            f'<b>{_esc(ticker)}</b>'
            f'<span style="color:var(--muted)"> &middot; '
            f'{_esc(monitor.get("company_name", ""))}</span>'
            f'</div><div style="text-align:right">{right}'
            # Labelled and shortened: a bare 26-character hash reads as debug
            # output left on screen. Prefixed, it reads as what it is, the
            # Parallel-side id of this watch, which is the thing that proves
            # the watch is a real declared monitor and not a label.
            f'<div class="mon-id">Parallel monitor '
            f'{_esc(monitor.get("monitor_id", "")[:18])}&hellip;</div>'
            f"</div></div>")

    return f"""<div class="body" style="font-size:14px;margin-bottom:22px">
    Watched continuously by Parallel. The watch is declared once and runs
    between scheduled runs, so a contract award or an insider filing arrives
    when it happens rather than at the next sweep.
  </div>
  {rows}
  <div class="pull-row">
    <form method="post" action="/watch/refresh" data-busy="Fetching&hellip;">
      <input type="hidden" name="ticker" value="{_esc(ticker)}">
      <button class="btn btn-ghost">Fetch what the watch found</button></form>
    <span style="font-size:11.5px;color:var(--muted)">
      Collects events the monitor has already found; it does not start a new
      search, so nothing appears if the watch has seen nothing yet. Events
      normally arrive on their own by webhook.</span>
  </div>"""


def _alerts_fired(alerts: list[dict], ticker: str = "") -> str:
    """Alerts Grafana actually sent, newest first.

    The rules always evaluated. What this shows is that one of them fired and
    reached somewhere: an alert whose only trace is a red panel in Grafana is
    invisible the moment nobody is looking at Grafana.

    `ticker` says the list is already scoped to one company, which drops the
    redundant ticker link from every row.
    """
    if not alerts:
        return ('<div class="empty">No alerts yet. Grafana evaluates the '
                'rules every five minutes and posts here when one trips.</div>')
    rows = []
    for a in alerts:
        firing = (a.get("status") or "firing") == "firing"
        sev = (a.get("severity") or "").lower()
        cls = "down" if sev == "warning" and firing else ("up" if not firing else "")
        # An alert whose rule aggregates over the whole watchlist arrives with
        # no ticker label. On a scoped page that is still this company's alert,
        # so the row shows the kind rather than a link back to where it is.
        tk = "" if ticker else (a.get("ticker") or "")
        # A webhook can arrive with an empty rule or summary (a test post, or a
        # Grafana rule with no annotations). Rendering those raw produced a row
        # reading just "alert" over the bare rule name, which looks like a bug
        # in the product rather than a thin payload. Say what is missing.
        rule = _esc(a.get("rule", "")) or "<em style='font-style:normal;color:var(--muted)'>Unnamed rule</em>"
        summary = _esc(a.get("summary", "")) or (
            "<span style='color:var(--muted)'>No summary was sent with this alert.</span>")
        rows.append(
            f'<div class="ev"><div class="ev-top">'
            + (f'<a class="ev-tk" href="/lobby/{_esc(tk)}">{_esc(tk)}</a>' if tk
               else f'<span class="ev-tk">{_esc(a.get("kind") or "alert")}</span>')
            + f'<span class="ev-when">{_when(a.get("received_at", ""))}</span>'
            f'</div><div class="ev-text"><b class="{cls}">{rule}</b>'
            + (" &middot; resolved" if not firing else "")
            + (f"<br>{summary}" if summary else "")
            + "</div>"
            + (f'<div class="ev-src">{_esc(a.get("value", ""))}</div>'
               if a.get("value") else "")
            + "</div>"
        )
    return "".join(rows)


# Discovery talks to a paid API, and its failures are things the user can act
# on (or at least understand) rather than stack traces. The raw body was being
# printed into the page: a judge searching "US defence agencies" got a wall of
# JSON with a billing URL in it, which reads as a broken product rather than an
# account that needs topping up.
DISCOVERY_ERRORS = {
    402: ("Discovery is out of credit. Company discovery runs on Parallel's "
          "FindAll API, which is billed per run and is currently exhausted on "
          "this account. Everything else on the site (research, briefings, "
          "alerts, Ask) uses the Search API and is unaffected."),
    429: ("Parallel is rate limiting us. Discovery makes a burst of calls; "
          "wait a minute and run it again."),
    401: "The Parallel credentials were rejected. Check the API key.",
    403: "This Parallel account is not allowed to use FindAll.",
}


def _discovery_error(error: str, status: int | None = None) -> str:
    """A sentence a person can act on, instead of an API body.

    Falls back to the raw text when the status is not one we have words for:
    an unrecognised failure is still better shown than swallowed.
    """
    known = DISCOVERY_ERRORS.get(status or 0)
    if known:
        return (f'<div class="empty disc-err"><b>Discovery unavailable</b>'
                f'<span>{_esc(known)}</span></div>')
    return (f'<div class="empty disc-err"><b>Discovery failed</b>'
            f'<span>{_esc(error)}</span></div>')


def _profile_line(profile: dict) -> str:
    """The axes the three columns were built on, in the reader's view.

    Printed rather than kept internal on purpose: the columns only make sense
    if you can see what the agent decided the company *is*. A reader who
    disagrees with "defense / counter-UAS systems" can see immediately why a
    name they expected is missing, instead of concluding the search is broken.
    """
    if not profile:
        return ""
    bits = []
    for key, label in (("sector", "Sector"), ("product", "Product"),
                       ("country", "Country")):
        if profile.get(key):
            bits.append(f'<span class="pf"><i>{label}</i>'
                        f'{_esc(profile[key])}</span>')
    if not bits:
        return ""
    return (f'<div class="fac-prof">{"".join(bits)}'
            f'<span class="pf-src">profiled by Parallel</span></div>')


def _sug_card(r: dict) -> str:
    """One suggested company: what it is, why it was matched, and the source."""
    conf = (r.get("confidence") or "").lower()
    return f"""<div class="sug">
  <div class="sug-top">
    <span class="sug-tk">{_esc(r["ticker"])}</span>
    <span>{_esc(r["company_name"])}</span>
    <span class="sug-ex">{_esc(r.get("exchange", ""))}</span>
    {f'<span class="conf {conf}">{_esc(conf)} confidence</span>' if conf else ''}
  </div>
  {f'<div class="sug-what">{_esc(r["what_it_does"])}</div>' if r.get("what_it_does") else ''}
  {f'<div class="sug-why">{_esc(r["reason"])}</div>' if r.get("reason") else ''}
  <div class="sug-act">
    <form method="post" action="/watchlist/add" data-busy="Adding&hellip;">
      <input type="hidden" name="ticker" value="{_esc(r["ticker"])}">
      <input type="hidden" name="company_name" value="{_esc(r["company_name"])}">
      {'<button class="btn btn-ghost">Add and research</button>'
       if adds_open() else
       '<button class="btn btn-ghost" disabled>Coming soon</button>'}
    </form>
    {_link(r.get("source_url"), "Source") if r.get("source_url") else ''}
  </div>
</div>"""


def _facet_column(f: dict) -> str:
    """One axis of a peer search, filling in on its own schedule.

    A column that is still working says so in its own right. Three columns
    sharing one page-level spinner is what made a search that was running
    normally look like a search that had returned nothing.
    """
    st = f.get("state") or {}
    rows = f.get("results") or []
    running = bool(st.get("running"))

    if rows:
        body = "".join(_sug_card(r) for r in rows)
    elif running:
        # The counters are the proof of work: a candidate is generated first
        # and confirmed only after every condition has been tested against it,
        # so "8 found, 0 confirmed" is a normal mid-run state and not a
        # failure. Saying that here is the difference between a reader who
        # waits and a reader who thinks the page is broken.
        body = (f'<div class="fac-wait"><span class="spin"></span>'
                f'<div><b>{st.get("generated", 0)}</b> found, '
                f'<b>{st.get("matched", 0)}</b> confirmed'
                f'<div class="fac-note">Each candidate is checked against '
                f'every condition.</div></div></div>')
    else:
        body = ('<div class="fac-none">Nothing met every condition on this '
                'axis.</div>')

    count = (f'<span class="fac-n">{len(rows)}</span>' if rows
             else '<span class="fac-n working"></span>' if running else '')
    return (f'<section class="fac{" working" if running else ""}">'
            f'<h3>{_esc(f.get("label", ""))}{count}</h3>'
            f'<div class="fac-cap">{_esc(f.get("caption", ""))}</div>'
            f'{body}</section>')



def page_discover(*, query: str, peers: str, objective: str, results: list[dict],
                  watchlist: list[dict], error: str = "", state: dict | None = None,
                  run_id: str = "", last_run: dict | None = None,
                  status: int | None = None, facets: list[dict] | None = None,
                  profile: dict | None = None, running: bool = False,
                  history: list[dict] | None = None) -> str:
    """Companies the watchlist does not have yet.

    Every other page answers a question about a ticker the user already typed.
    This one proposes names they did not, which is the only part of the product
    that can widen what they are looking at rather than deepen it.

    Suggestions are never added automatically: an app that grew someone's
    watchlist on its own would be making a decision that belongs to them.
    """
    # quote_plus for the URL, _esc for the HTML: two different jobs, in that
    # order. Escaping first puts `&#x27;` inside the href and the browser cuts
    # the query at the `&`.
    chips = "".join(
        f'<a href="/discover?peers={_esc(quote_plus(r["ticker"]))}" '
        f'data-busy="Searching&hellip;">Peers of {_esc(r["ticker"])}</a>'
        for r in watchlist
    )

    state = state or {}
    facets = facets or []
    profile = profile or {}
    running = running or bool(state.get("running"))

    if error:
        found = _discovery_error(error, status)
    elif run_id and not results and not running:
        found = ('<div class="empty">No companies matched every condition. '
                 'The conditions are tested strictly, so a more specific '
                 'objective usually returns more matches, not fewer.</div>')
    elif results:
        found = (f'<h2>{len(results)} suggestion{"s" if len(results) != 1 else ""}'
                 f'</h2>' + "".join(_sug_card(r) for r in results))
    else:
        found = ""

    if facets and not error:
        done = sum(1 for f in facets if not (f["state"] or {}).get("running"))
        head = (f'<div class="fac-head"><h2>Peers of {_esc(peers.upper())}</h2>'
                f'{_profile_line(profile)}</div>')
        if running:
            head += (f'<div class="fac-bar"><span class="spin"></span>'
                     f'Searching three ways at once &middot; '
                     f'<b>{done} of {len(facets)}</b> finished. '
                     f'Columns fill in as they land.</div>')
        found = head + f'<div class="fac-grid">' + "".join(
            _facet_column(f) for f in facets) + '</div>'

    # While a run is in flight the page refreshes itself: a discovery takes
    # minutes, and the counters moving are what shows it is working. A timer,
    # not <meta refresh>: the meta tag reloads while someone is typing into the
    # objective box and throws away what they wrote.
    if running:
        progress = ('<script>setTimeout(function(){'
                    'var a=document.activeElement;'
                    'if(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))return;'
                    'if(document.visibilityState==="hidden")return;'
                    'location.reload();},12000);</script>')
    else:
        progress = ""

    body = f"""<h2>Discover</h2>
<div class="card">
  <div class="body" style="font-size:14px;margin-bottom:20px">
    Describe what you want to follow and Parallel finds the companies that match,
    with the evidence for each. Nothing is added to your watchlist unless you add it.
  </div>
  <form class="disc-form" method="get" action="/discover">
    <input name="q" value="{_esc(query)}" placeholder="US-listed companies supplying counter-drone systems to defence agencies">
    <button class="btn">Find companies</button>
  </form>
  <div class="chips">{chips}</div>
  <div class="disc-cost">Each search bills Parallel&#39;s FindAll API, which
    charges per query plus per match. A peer search runs three of them, one per
    axis.</div>
</div>
{found}
{progress}
{_history_block(history or [], kind="discover", current=_current_search(query, peers))}"""
    return _shell("Discover \u00b7 The Ticker Room", body, last_run, here="/discover")
