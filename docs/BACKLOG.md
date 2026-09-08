# Backlog

## Phase 1 — Watchlist news radar (current focus)

The product for the hackathon submission. Per-user watchlists, agentic web research
over Parallel, history in ClickHouse, spike detection and push alerts via Grafana.

- [ ] Replace Brave + Tavily with Parallel (Search + Task)
- [ ] Multi-user watchlists (today WATCHLIST/WATCHLIST_NAMES are source literals)
- [ ] Real price context passed to the LLM (port `fetch_watchlist_quote` logic)
- [ ] Relevance filter on word boundaries (port `_result_mentions` — "ONDS" matches
      "seconds" and "bonds" as a substring)
- [ ] ClickHouse schema: articles, coverage counts, sentiment, price snapshots
- [ ] Grafana: coverage-spike panels + alert rule + push notification
- [ ] Parallel Monitor for continuous change detection
- [ ] Google Cloud: Gemini Enterprise Agent Platform, Agent Builder, Cloud IAM
- [ ] Deployed web app (a deliverable: "URL of deployed project")
- [ ] Check `finish_reason == "length"` and warn instead of shipping a silent
      truncated report (known mute failure)
- [ ] Cache a demo dataset so the 3-minute video never depends on a live upstream

## Phase 2 — Earnings calendar (deferred, do not lose)

Deliberately out of scope for the first pass. The two domains share only email and
the LLM call; their data sources and logic have nothing in common.

- [ ] Nasdaq earnings calendar ingestion
- [ ] Implied move / ATM IV / put-call skew (the quantitative core)
- [ ] Budget filter (`spot * 100 <= capital`, one contract covers 100 shares)
- [ ] Expiry selection: first strictly AFTER the earnings date (this was a real v1 bug —
      using the nearest generic expiry picked options expiring BEFORE the announcement)
- [ ] Parallelize the options fetch (44 sequential tickers, 13.5 min worst case → <2 min)

## Known upstream risks

- Nasdaq calendar endpoint: undocumented, no contract, can break without notice.
- yfinance: unofficial library scraping a private API, breaks periodically.
- Both are why a paid market-data provider is under evaluation.

## Notes from the first working run (2026-08-22)

- Parallel returned 10 relevant results for ONDS in 1.6s. The previous stack's
  Brave -> Tavily ladder existed because Tavily returned zero for this exact
  ticker; Parallel alone replaces both providers.
- `gemini-2.5-flash` is retired for new API keys (404 with an explicit message).
  Now on `gemini-3.6-flash`.
- The Gemini key currently in SSM (`gemini.env`) is an **AI Studio** key. The
  submission requires **Gemini Enterprise Agent Platform / Vertex AI**, which is
  a different surface. Migrating it is still to do.

## Automation (decided 2026-08-22)

"Run research" stays as a manual trigger — it is what makes the demo filmable —
but it is not the intended path. The scheduled run is the product.

- [ ] Scheduled runs (Cloud Scheduler -> Cloud Run), per-user frequency
- [ ] `runs.trigger` already distinguishes `manual` from `scheduled`
- [ ] Header shows "Last updated"; it turns amber past 24h

## Reddit sentiment (evaluating)

Reference: swaggystocks.com. Their method is undocumented on the site.

Reddit's own API changed the calculus: free is **non-commercial only**, and since
the Responsible Builder Policy closed self-service registration in late 2025,
every new OAuth client needs a manually reviewed ticket with no published
turnaround and a real chance of rejection. Commercial use is $0.24/1k calls under
a hand-reviewed contract. For a project that plans to monetize and has an 18-day
deadline, that approval queue is the blocker, not the price.

Alternative worth testing first: reach Reddit discussion **through Parallel**,
which already indexes reddit.com threads. No Reddit credentials, no approval
queue, and it uses more of the partner's surface rather than less.

## Fixed 2026-08-22 (second pass)

- **Sources were quote pages, not journalism.** The first queries returned
  `/quotes/ONDS`, `/stocks/aapl-stock`, finviz quote screens: a live price and no
  reporting. Fixed with a Parallel `source_policy` excluding quote terminals plus
  a URL-shape filter, since publishers like Yahoo serve both. Now returns press
  releases (`ir.ondas.com`), CBS News, blockonomi, asktraders.
- **Sentiment always read "quiet".** `_extract_json` stripped code fences with a
  MULTILINE regex that mangled valid JSON, so every reading silently fell back to
  the default. The model had been returning correct JSON all along.

## Still to do

- [ ] Wire settings to the Grafana alert rule (today the rule ships paused and
      the thresholds in Settings are not yet pushed into it)
- [ ] Notification channel for the spike alert (push/email)
- [ ] Scheduled runs (`run_frequency` is stored but nothing consumes it)
- [ ] Google Cloud: migrate off the AI Studio key to Gemini Enterprise / Vertex

## Sentiment was not trustworthy (found and fixed 2026-08-23)

Three real defects, all found by checking the stored data rather than the code:

1. **No time window.** Threads from 2024 and 2025 were being scored as today's
   mood. Fixed with Parallel's `source_policy.after_date`, plus a second filter
   that estimates a post's date from its base36 id (Reddit ids increase
   monotonically; calibrated against two posts of known date, accurate to about
   a month). `after_date` alone still let old threads through.
2. **No control over where.** Search hit whatever reddit.com pages ranked, mostly
   r/wallstreetbets listings. Now targets finance subs by name and discovers
   per-ticker subs (r/ONDS, r/redditstock), each weighted by the kind of
   reasoning it rewards: r/ValueInvesting 1.4, r/wallstreetbets 0.8.
3. **Stale cache.** Added `fetch_policy.max_age_seconds = 3600` to force a live
   fetch for anything older than an hour.

Effect: ONDS moved from +72 "bullish" to -15 "mixed" once old threads stopped
counting. The +72 was inflated by 2024-2025 optimism.

The same `after_date` fix was applied to news search, which had the identical
flaw.

## Alert latency

Grafana now re-evaluates the spike rule every minute (was 5). But the real floor
is the research cadence: a spike cannot be seen before the run that finds the
articles. Settings now offers 15m / 1h / 4h alongside daily and weekly, and says
so plainly. Nothing consumes `run_frequency` yet.

## Why AAPL returned no Reddit threads (found 2026-08-23)

`source_policy.after_date` is applied by the index against its own record of a
page's publication date. For Reddit that record is often missing or wrong, so a
narrow window silently drops threads that are genuinely recent — and how badly
it does so varies by ticker, which is why only AAPL looked broken:

| Window | AAPL | ONDS | RDDT |
|---|---|---|---|
| none | 18 | 19 | 20 |
| 90d | 13 | 12 | 20 |
| 30d | 11 | 4 | 20 |
| 7d | **3** | 17 | 20 |

Note ONDS at 30d (4) vs 7d (17): the filter is not even monotonic, which
confirms it is not really filtering by date.

Fix: request a deliberately wide window from the index and enforce real recency
locally from the post id, which is reliable. When a ticker genuinely has little
recent discussion the window widens once and the result is labelled with the
window actually used, rather than reporting a false "quiet".

AAPL went from 0 threads to 9, all from the last few weeks.

A second defect surfaced while fixing this: when the Gemini call failed, the
result was stored as `quiet` with score 0 — indistinguishable from a genuine
reading of "nobody is talking about this". That is how AAPL showed 8 threads
and score 0. Failures now store `label = "unavailable"` and say why.

## Google Cloud (done 2026-08-23)

Project `ticker-room` created, billing linked, 50 EUR budget with alerts set
BEFORE enabling any API. Model calls now go through Gemini Enterprise Agent
Platform with a least-privilege service account. The AI Studio key is no longer
referenced anywhere in `src/`. See `docs/GOOGLE_CLOUD.md`.

Still to do on the platform:
- [x] Agent Builder — analyst agent at /ask with five tools and a visible trace
- [x] Cloud Run deployment — live at https://ticker-room-372773300560.europe-west1.run.app
- [x] Cloud Scheduler — every 4h, hitting /tasks/run
- [ ] Make the Settings frequency actually update the scheduler job
- [x] Secrets split documented: SSM locally, Secret Manager in Cloud Run

## Reddit was under-reporting threads (found 2026-08-23)

r/ONDS showed 2 threads, which was not credible for a ticker's own subreddit.
Three compounding causes:

1. **The recency cutoff was tighter than the heuristic's precision.** The post-id
   estimate is accurate to roughly a month, but `days/365*1.5` for a 7-day
   window cut at ~10 days, discarding genuinely recent threads. A raw search
   found 11 recent ONDS threads where the app kept 3. Tolerance is now the
   window plus six weeks of slack, since dropping real discussion is the worse
   error.
2. **Too few query angles.** One phrasing reaches one pocket of the index.
   Now four: the ticker's own subreddit, the week's discussion, the bull/bear
   framing, and general retail talk.
3. **No retry on the sentiment call.** An unparseable response stored
   `unavailable` for a ticker people were actively discussing. It now retries
   once at temperature 0 with a larger output cap.

ONDS went from 2 threads to 5 from r/ONDS alone.

## X added as a second sentiment source (2026-08-23)

Reddit alone was thin: five threads is an anecdote, not a reading. X carries the
cashtag conversation ($ONDS) that Reddit does not, and Parallel indexes it. The
post text arrives in the result *title* ("Author on X: \"...\""), since X renders
the body behind a login wall the index only partly sees.

ONDS went from 5 sources to 25 (7 Reddit + 18 X).

Profile and search pages are filtered out; only `/status/` URLs are real posts.

## On real-time, and why Parallel is not F5Bot

F5Bot downloads Reddit wholesale: post ids are base36 counters, so it walks them
backwards and batches ~100 per call to `api.reddit.com/api/info.json`. That no
longer works from a server — `/r/all/comments/.json`, `api.reddit.com` and
`oauth.reddit.com` all return 403 from datacenter IPs, browser user-agent or not.
F5Bot survives on years of standing, not on a technique a new project can copy.

Parallel does not poll Reddit either. It serves a **crawled index**, so its
freshest Reddit content for a given ticker is weeks old, not minutes:
asking for the last 48 hours returned nothing newer than 31 days.

This matters less than it sounds. F5Bot answers "did anyone say ONDS?" — one
mention is the whole product. This answers "what is the mood?", which needs
enough posts to average. A per-mention alert would be noisier, not faster.

## Analyst price targets (added 2026-08-23)

Uses Parallel's **Task API** rather than Search: Search returns pages, Task
returns structured records against a JSON schema. Asking for firm, analyst,
target price, rating and date gives back rows that can be charted against the
live price.

First run: 63 targets from named firms — AAPL 28 (avg $330.70), RDDT 26
($214.54), ONDS 9 ($17.97 against an $8.71 quote).

Task runs are asynchronous and take one to three minutes, so this is polled and
never blocks the rest of the pipeline. Targets are de-duplicated by firm,
keeping the newest, since the same target appears on several aggregator pages
and would otherwise let one bank count five times toward the average.

## The X sample was a ceiling, not a measurement

"17 posts for a company as big as Reddit" was the right thing to distrust: the
code asked for `max_results: 20` across 3 queries and kept whatever survived.
Now 5 queries and a cap of 40 — and posts whose text is empty or just "X" are
dropped, since they inflate the apparent sample without contributing anything.
RDDT went from 17 posts (several empty) to 14 with real text.

## Target revisions and alerting (2026-08-23)

The first version of `_clean()` kept only the newest target per firm, which
silently destroyed the thing worth alerting on: a firm moving from $18 to $10
is only visible if both figures survive. Now de-duplication is by
(firm, date, price), `latest_per_firm()` gives the current view, and
`find_revisions()` compares a firm against its own previous number.

Three Grafana rules, provisioned in `alerting/alerts.yml`:

| Rule | Fires when | Active |
|---|---|---|
| Analyst cut a price target | a firm lowers its own target >15% | yes |
| Analyst raised a price target | a firm lifts its own target >15% | yes |
| Price far below consensus | a ticker trades >50% under the average | paused |

Verified firing: seeding a Needham cut from $18 to $10 (-44%) moved the rule to
`state: firing` and Grafana logged "Sending alerts to local notifier".

Revisions need two observations of the same firm to exist, so they appear once
the scheduler has run across a few days.

## Still to do

- [ ] A notification channel (the alerts fire but reach nobody yet)
- [ ] Multi-user watchlists
- [ ] Settings frequency should drive the Cloud Scheduler job

## SEC filings, and Grafana per ticker (2026-08-23)

**Grafana was a second interface competing with the app.** The dashboard mixed
all tickers and the embedded panels passed `var-ticker` to a dashboard that had
no such variable, so the filter was ignored. The dashboard now defines a
`ticker` template variable and every panel filters on it, so a panel embedded in
`/t/ONDS` shows ONDS.

**SEC filings** via the Task API: Form 4 insider trades with the person's name
and role, dilution (S-3, S-1, 424B5) and material 8-K events. First run returned
37 filings across three tickers, including the Jennifer L. Wong and Steve
Huffman Form 4 sales.

Two alert rules added, both active: `insider-sell` and `dilution`. These are
discrete dated facts rather than drifting trends, which is what makes them worth
firing on the moment they appear.

Each ticker page now opens with an alert strip: insider sales, target revisions
and a consensus gap over 30%, in one row.

### `transaction` is a reserved word in SQLite

The filings table silently failed to create inside `executescript`, leaving no
table at all and no error. Renamed to `txn_type`, aliased back on read.

## RDDT was getting one article (found 2026-08-23)

Three compounding bugs, all visible in one screenshot: a briefing citing `[1]`
over and over, hovering it showing scraped nav links, and the cited piece being
months old.

1. **`search_news` never set `max_results`.** The API returns a small default,
   so RDDT got 2 raw results where an explicit cap of 30 returns 15. The Reddit
   and X searches had the cap; news did not.
2. **Quote pages passed the filter when the URL looked like an article.**
   Aggregators serve "Stock Price | Quote" screens on article-shaped paths, so
   the filter now checks the title too.
3. **Citation previews rendered raw scraped text** — nav bars, cookie banners,
   markdown link soup. Previews now require prose and show nothing otherwise.

Also: when a tight window returns fewer than five articles, the search widens
once rather than building a briefing on a single source.

RDDT went from 1 article cited as `[1]` throughout, to 17 articles cited as
`[1] [2] [5] [8]`.

### Two API details worth remembering

- `exclude_domains` rejects a domain carrying a path (`site.com/x`) with a bare
  422 naming no field.
- `transaction` is reserved in SQLite; `CREATE TABLE` fails silently inside
  `executescript`.

## Filings and metrics now explain themselves

Price stats carry a `?` explaining what MA20/MA50 and the 52-week range mean and
how to read them together, plus an "Off 52w high" figure. Filing headlines link
to their source document.

## A sale was being shown as a purchase (found 2026-08-23)

The worst bug so far: Form 4 rows where Jennifer Wong and Steve Huffman **sold**
shares were badged "INSIDER BUY" in green. Two causes:

1. The page re-derived each row's kind by rebuilding a lookup key from
   `(form_type, filed_date, insider_name)` and matching it against `notable()`'s
   output. Any difference in those fields left the row unclassified.
2. `transaction` is frequently "n/a" even when the headline says "sold", so
   rows fell through to whatever the default badge was.

Now `classify()` decides once, on the row itself, reading the headline when the
transaction field is unhelpful. Grants and vesting are separated from decisions:
receiving RSUs is compensation, not a view on the company.

Labels are now explicit — "Insider sold" rather than a bare "Insider" — because
a colour alone is not enough to carry that distinction.

## Other fixes from the same review

- **Tooltips were clipped** by the stat cell they lived in. The grid no longer
  hides overflow and popups near an edge anchor inward.
- **Filings table has a header row** explaining what "sh" means and that the
  date is the SEC filing date, which for a Form 4 is within two business days
  of the trade.
- **Analyst targets link** to their source, as filings already did.
- **The lobby was a second copy of the ticker page.** It is now one row per
  ticker: price, event flags, sentiment and the first line of the briefing.

## Four more Parallel APIs (2026-08-24)

The README claimed "Search, Task, Monitor, FindAll"; only Search and Task were
wired. Monitor, FindAll and Extract are now real, and Task keeps its evidence.

### Monitor: the product stops being a cron job

The scheduled run is a pull every four hours. `ensure_monitor()` declares one
standing watch per ticker (`event_stream`, hourly, `lite`), and Parallel reports
when something actually changes. Events arrive at `POST /hooks/parallel`, which
re-fetches them rather than trusting the webhook body, and `/watch` shows what
is being watched and what it caught.

The webhook is only registered when `TICKERROOM_PUBLIC_URL` is an https URL: the
API rejects one it cannot reach. Locally, "Pull events now" collects by hand.

- `POST /v1/monitors/{id}/cancel` cancels. `DELETE` returns 401, which reads as
  an auth failure rather than a wrong method.

### Task basis: the evidence was being discarded

Both extractors did `output.get("content")` and dropped `output.basis`, which
carries per-field citations, the source excerpt, reasoning, and a confidence
level. Now stored on every target and filing row and shown as a `?` hover.

For filings the surfaced citation is the `transaction` field deliberately: the
buy/sell direction is what this module has actually got wrong before.

`overall_confidence()` takes the *weakest* field, since a row is only as good as
its least certain part.

### FindAll: the watchlist can now widen, not just deepen

`/discover` proposes companies not on the watchlist: peers of a held ticker, or
anything matching a plain-language objective. Nothing is added automatically.

Four things the docs do not say, all found by running it:

1. **`match_limit` has a minimum of 5.** Below that, a 422 that does name the bound.
2. **`enrichments` in the create body is silently ignored.** Enrichment is a
   separate `POST /v1beta/findall/runs/{id}/enrich` call taking an `output_schema`.
   Passing it at creation looks exactly like the model refusing to fill fields in.
3. **Status is nested and `is_active` is the real terminator**:
   `{"status": {"status": "running", "is_active": true, "metrics": {...}}}`.
   Reading `.get("status").lower()` raises on a dict.
4. **A partial snapshot reads as "no matches".** Candidates sit at
   `match_status: "generated"` until validated, so an early read reports zero
   matches for a run that had simply not finished. Runs take four to six minutes.

`plan()`'s auto-generated conditions are too literal for peers: asked for
"comparable size" it wrote a market-cap-within-50% screen that rejected
AeroVironment as a peer of Ondas purely on size. `peers_conditions()` is written
by hand instead; `plan()` is still used for open-ended themes.

Because a run takes minutes, the page starts it and redirects to itself with the
run id, then refreshes every 15s showing candidates found and confirmed.

ONDS peers, verified: AVAV, RCAT, DPRO, LHX, MSI, NOK, INSG.

### Extract: previews that were showing nothing

The prose test in `citations.readable()` correctly rejected nav bars and cookie
banners, but the result was an empty hover card. Broken previews are now
re-fetched through Extract. Only the failing URLs are sent.

- The request body accepts **only** `urls` and `objective`. Anything else is
  rejected outright, and `excerpts` is a *response* field, not a request one.
- Strip markdown **before** the frontmatter regex: a metadata line arrives as
  `# title: ...`, so the key only sits at line start once the `#` is gone.

### Also

- **One HTTP client.** `parallel_api.py` replaces three copies of `_post`/`_get`
  and two identical polling loops. That duplication is why news search shipped
  without `max_results` while Reddit and X had it.
- **Search mode per job.** Was `fast` everywhere. News, which feeds the briefing
  and gets cited, is now `advanced`; the social sweeps stay `fast`. The valid
  set is turbo / fast / basic / advanced.
- **353 dead lines removed from `render.py`.** `page_index` and `page_ticker`
  were each defined three times identically; only the last took effect. Verified
  byte-identical HTML across every page before and after.

### Still to do

- [ ] Set `TICKERROOM_PUBLIC_URL` on Cloud Run so monitors register their webhook
- [ ] Grafana alert rule on `monitor_events` (the events land but fire nothing)
- [ ] A notification channel (alerts still reach nobody)
- [ ] Multi-user watchlists

## Ticker pages, and what a new ticker gets (2026-08-25)

### The page had no fixed shape

Sections were omitted when they had no data, so a ticker page looked different
per ticker and a newly added one was a bare card with no explanation. A missing
block is indistinguishable from a block that found nothing. Every section now
always renders, with "Press Run research and this fills in on the next pass".

Their order is a Settings preference (`section_order`), since what matters first
is taste: filings are hard dated facts, sentiment is what people say about them.
A rank select per section rather than drag handles, so no JavaScript is needed.
`settings.section_order()` repairs a stale or half-filled order against the
known set, so a typo in the database cannot make a section vanish.

### The stats grid

Seven metrics is prime, so `auto-fit` always left an orphan cell with dead space
beside it, and "Off 52w high ?" wrapped its marker onto a second line. Now a
fixed 4-column grid wrapping 4 + 3 with the last cell spanning the gap.

The tooltip on the last metric overflowed the page: the anchoring rules keyed
off position in the whole list, which only worked while the stats were a single
row. They now key off column position (`nth-child(4n)`), so a popup is pulled
inward at either edge of every row.

### The CSS for /watch and /discover was never in the file

Two earlier appends matched an anchor that a later edit had already consumed,
so `.replace()` silently no-opped and both pages had been rendering unstyled
since they were added. Worth remembering: a `str.replace` that does not match
is not an error, it is a no-op, and nothing downstream notices.

Guard used to find it, worth re-running after CSS edits:

```python
defined = set(re.findall(r'\.([a-zA-Z][\w-]*)', CSS_BLOCK))
used = {c for g in re.findall(r'class="([^"{]+)"', src) for c in g.split()}
missing = used - defined
```

### Runs are concurrent, and adding a ticker researches it

A run was a sequential loop, and each ticker makes two Task calls of one to
three minutes that spend the whole time waiting on the network. Tickers now run
in a thread pool (capped at 6), so a run takes about as long as its slowest
ticker rather than the sum of all of them.

Measured: 2 tickers concurrently in 486s, against 23 minutes for the last
3-ticker sequential run. Per ticker that is roughly 4 minutes either way, which
is the point: the wall clock is now set by the slowest ticker, not by how many
there are.

That means several threads write to SQLite at once. Each repo call already
opened its own connection, so nothing is shared across threads, but two pragmas
were needed to make it safe rather than merely likely to work: `busy_timeout`
so a writer waits for the lock instead of raising "database is locked", and WAL
so the web pages can still read while a run is writing.

Adding a ticker now kicks off its research as a FastAPI background task, so a
name accepted from /discover fills itself in instead of sitting empty until
someone presses the button.

### Removing a ticker

There was no way to remove one, only to add. Removing now also cancels the
ticker's Parallel monitor: a watch left running after its ticker is gone keeps
checking hourly forever and nothing in the app would ever surface it. The
stored history is kept, so re-adding does not start from nothing.

Watchlist reduced to ONDS and RDDT.


## Parity, verified (2026-08-25)

Both tickers now carry every feature, checked against stored data rather than
the run's return values:

| | quote | articles | briefing | sentiment | targets (ev) | filings (ev) | monitor |
|---|---|---|---|---|---|---|---|
| ONDS | Y | 33 | Y | bullish | 13 (8) | 30 (26) | Y |
| RDDT | Y | 41 | Y | bullish | 56 (35) | 32 (8) | Y |

The stored totals exceed what the run itself returned, which is the backfill
working: evidence attached to rows recorded by earlier runs as well as to new
ones. Filings carried evidence for the first time here; before this run the
column existed but was empty everywhere.

**Target revisions is deliberately still conditional.** It is a sub-block of
the targets section rather than one of the six orderable ones: a revision needs
two observations of the same firm to exist at all, so an empty "Target
revisions" heading would appear on almost every ticker and say nothing. RDDT
has 4, ONDS has 0, and that difference is real data rather than a parity gap.

## Still to do

- [ ] Monitor events feed nothing. A caught event ("Redburn raised its Apple
      target from $260 to $400", with sources) lands in `monitor_events` and
      appears only on /watch: it does not become a target row, does not reach
      /api/metrics, and fires no Grafana alert. The interrupt path dead-ends.
- [ ] `TICKERROOM_PUBLIC_URL` on Cloud Run, so deployed monitors register a
      webhook instead of needing "Pull events now"
- [ ] ClickHouse: the README claims it in the stack table and it does not exist
- [ ] A notification channel (alerts still reach nobody)
- [ ] Multi-user watchlists

## Two data bugs found by looking at the finished page (2026-08-25)

**"Off 52w high" was permanently a dash.** `fetch_quote` computed it, but the
`quotes` table has no column for it, so it was dropped on the way in and the
page rendered "—" for a stat it had both inputs for. Derived on read instead of
migrated in, since it is a pure function of `spot` and `high_52w`. Applied to
the Firestore path too, where old documents predate the field.

**The extractor reported absences as filings.** Asked for share-offering
filings, the model answers honestly when there are none: "No S-3 or 424B5
share-offering filing was identified in the reviewed Reddit SEC filings". True,
and useful, but not a filing, and listing it in a table with a form type and a
date asserts a document exists that does not. Six such rows were stored across
the watchlist, and one had been classified `dilution`, so it would have fired a
false dilution alert.

`is_negative_finding()` drops them at `_clean`. It matches the absence phrasing
rather than the word "no", so an 8-K that genuinely announces no dividend
survives.

This is the failure mode to expect from schema extraction generally: the model
fills the shape it was given even when the honest answer is "nothing here", and
an empty result and a stated absence are not the same row.

## The deploy broke on a dependency nobody changed (2026-08-25)

First deploy of this week's work returned 500 on every route. The traceback was
in `firestore_store.get_watchlist`, code untouched since 2026-08-23:

```
INVALID_ARGUMENT: Invalid database id %28default%29
```

`%28default%29` is `(default)` URL-encoded.

**The first diagnosis was wrong.** `requirements.txt` said
`google-cloud-firestore>=2.16`, so the obvious suspect was the Firestore client
picking up a new release. Pinning it to 2.28.1 changed nothing: the redeploy
failed identically. Pinning the plausible culprit is not the same as finding it.

What actually broke it is **`google-api-core` 2.35.0**, a transitive dependency
nothing in `requirements.txt` even named. Found by reproducing the failure in a
clean virtualenv (the local environment could not reproduce it, because it
still had the older api-core) and then bisecting against the real database with
the firestore client and protobuf held constant:

| google-api-core | result |
|---|---|
| 2.31.0 – 2.34.0 | reads fine |
| **2.35.0** | `Invalid database id %28default%29` |

Pinned to `==2.34.0`. Verified by installing the whole of `requirements.txt`
into a clean virtualenv and serving every route against the real Firestore
before deploying, rather than deploying to find out.

**The lesson is the floating pin, not the library.** Every dependency here was
`>=`, which means the deployed artefact is not the one that was tested: two
builds of the same commit can differ, and the difference surfaces only in
production. The remaining `>=` pins are a live risk for the same reason, and
the submission has a deadline.

- [ ] Pin the rest of `requirements.txt`, or add a lockfile

Worth knowing for the demo: this failure was invisible locally **twice over**.
Local runs use SQLite and never construct a Firestore client, and even when
pointed at Firestore this machine still had the older api-core, so it kept
working while the container did not. Reproducing it needed a clean virtualenv,
which is the closest thing to the container available without Docker.

`/healthz` now reports the running container's Python and resolved package
versions, so the next time a deploy fails on a dependency the answer is one
request away rather than a rebuild.

### Firestore needs a composite index for the monitor lookup

`monitor_for_ticker` filters on `ticker` **and** `status`, two equality filters
on different fields, which Firestore cannot serve without a composite index.
Added to `firestore.indexes.json` and created in the project. Without it
`ensure_monitor` would have failed on every deployed run, and only on the
deployed one: SQLite has no such requirement.

## Deployed (2026-08-25)

Revision `ticker-room-00018-szd`, after two failed attempts on the api-core
issue above. Every route serves 200 and the UI matches local: the 4 + 3 stats
grid, "Off 52w high" populated, Watch and Discover in the nav.

`/healthz` returns 404 through Google's edge even though the route exists and
answers locally. Worth knowing before it is mistaken for the app being down: it
is what made the very first check of the old deployment look broken when the
service was merely stale.

### The deployed service has no history of its own yet

Local development uses SQLite, the deployed service uses Firestore, and nothing
syncs between them. So everything from this week — monitors, and every row with
Parallel's evidence — exists only on this machine:

| | local SQLite | Firestore (deployed) |
|---|---|---|
| watchlist | ONDS, RDDT | ONDS, RDDT |
| monitors | 2 active | **none** |
| targets with evidence | 43 | **0** |
| filings with evidence | 34 | **0** |

The live pages therefore render correctly but thinly: `/watch` says "No watches
yet" and no evidence hovers appear. One run against the deployed service fixes
it, and creates the monitors with a webhook now that `TICKERROOM_PUBLIC_URL` is
set. That is real Parallel spend, so it is a decision rather than a step.

- [ ] Run `/tasks/run` against the deployed service to populate Firestore

## The absence filter deleted a real filing (2026-08-25)

Purging the phantom rows from Firestore removed 17, and one of them was real:

> Prospectus supplement filed under Rule 424(b)(7) for resale of the 581,732
> Cyberhawk consideration shares; **no offering dollar value was stated**.

That is a genuine ONDS 424B7. The pattern matched `no ... offering` anywhere in
the headline, and here the phrase describes a *detail of a filing that exists*
rather than its absence.

The rule now requires the absence to be the subject of the sentence, anchored
at the start where a report of nothing-found puts it, with a carve-out for
"no <value|price|dollar|amount|consideration>" and a separate pattern for the
extractor's own "was not identified" phrasing. Checked against ten headlines
including the ones that caused each bug, and against all 64 stored local
filings: no false positives.

The deleted row comes back on the next run, since the source document exists.

**The general shape of the mistake:** a filter written from four examples of
the thing to remove, and none of the thing to keep. The examples that matter
are the near misses.

## /tasks/run is a request, and that is the wrong shape

The endpoint researches the whole watchlist inside a single HTTP request and
returns when it is done. Two tickers took 486s locally, against a Cloud Run
timeout of 600s, so the margin was 114 seconds: a slower run, or a third
ticker, gets cut off mid-write and leaves the history half populated with
nothing to show for it. Raised to 1800s, which buys room rather than fixing the
shape.

The fix is the same one `add_ticker` already uses: start the work as a
background task and return immediately, with the run's progress readable from
the `runs` table. Cloud Scheduler does not need the response, and nor does
anything else.

- [ ] `/tasks/run` should return immediately and run in the background
- [ ] Surface in-flight runs in the UI, so "nothing has appeared yet" is
      distinguishable from "the run failed"

## The deployed service has its own history now (2026-08-25)

`/tasks/run` against the live service: 200, 2 tickers, no errors, **623s** —
past the old 600s timeout, so raising it first was not precautionary.

| | quote | articles | briefing | sentiment | targets (ev) | filings (ev) | monitor |
|---|---|---|---|---|---|---|---|
| ONDS | Y | 28 | Y | mixed | 14 (7) | 95 (19) | Y |
| RDDT | Y | 47 | Y | bullish | 76 (19) | 84 (20) | Y |

Both monitors registered a webhook at
`https://ticker-room-.../hooks/parallel`, so the interrupt path now runs
unattended in production rather than needing "Pull events now".

Evidence counts are lower than local because only rows this run touched get a
basis; older rows keep theirs filled in by the backfill as they are re-seen.

The ONDS 424B7 deleted by the over-broad absence filter is back, as expected:
the document is real, so the extractor found it again.

Note the sentiment divergence: ONDS reads `mixed` live against `bullish`
locally. Different run, different window, genuinely different threads — not a
bug, but a reminder that the two stores are independent histories rather than
copies, and the live one is the one being judged.


## Judge-ready pass (2026-08-25)

Everything below was found by opening the deployed URL and reading the page,
then measuring the API rather than trusting its documentation.

### What a first-time visitor saw

**The lobby printed `**What Happened**`.** The briefing is markdown and the
renderer escaped it verbatim, so the model's own section heading arrived on the
card with its asterisks. It now renders bold, italic, headings and bullets and
nothing else: the text is escaped first, so a model that emits HTML gets it
shown rather than executed. The lobby teaser also skips heading lines, since
the first line of a briefing is often a title that summarises nothing.

**Three spellings of one insider read as three people.** RDDT listed "Huffman
Steve Ladd", "Steve Ladd Huffman" and "Steven Ladd Huffman" because the dedup
key was the raw name string. Names are now keyed on sorted, nickname-folded
tokens, so filing order and middle initials stop mattering, and duplicates
merge rather than being dropped: a share count on one copy and a dollar value
on the other both survive.

**One row's headline named a different director than its own filer.** A
sentence about Patricia Fili-Krushel sat beside an insider of FARRELL SARAH E,
because both were named on the same page and the schema has one slot per row.
A headline naming somebody who is not the row's filer is now replaced with a
line built from that row's own fields. Rejected rather than repaired: the
trade is true, the sentence was not.

**`"Not stated"` was being stored as a date.** The same failure mode as the
absence filings: asked for a date it cannot find, the model answers in words.
Stored, it sorts above every real ISO date, so it won "most recent target" for
its firm and quietly corrupted revision detection. Both targets and filings now
parse a date or store nothing.

### The interrupt path dead-ended

A caught monitor event landed in `monitor_events`, appeared on /watch as prose,
and stopped. `src/core/ingest.py` closes it: the event text goes back through
Task against the same schemas the scheduled run uses, so a caught target change
becomes a target row that moves the consensus and can trip an alert.

Classification is asked of the model rather than matched on keywords, since
"raised its target" and "initiated coverage at $400" are the same fact written
two ways. The event's own date stands in when the prose states a change without
restating its date, otherwise the row cannot take part in revision detection.

Verified live: a target change stored one row carrying its evidence, an insider
sale stored a filing, and an executive change correctly stored nothing.

### Alerts reached nobody

The Grafana rules evaluated correctly and notified no one: there was no contact
point, so every alert routed to a default receiver that did not exist. There is
now a webhook contact point, a notification policy, and `/hooks/grafana`, so a
fired alert is recorded and shown on /watch instead of being visible only to
whoever was looking at Grafana at that second.

The datasource also pointed at an absolute path on one laptop, so the dashboard
came up empty on any clone. Both it and the webhook URL now come from the
environment, set by `serve.sh` from the repo root.

### Parallel, measured rather than read

- **`freshness_start_date` is silently ignored.** It is the documented key for
  bounding search results by date. Against the same query it behaves exactly
  like a misspelled key: 20 results reaching back to 2023, identical to a
  deliberately bogus key sent as a control. Only `after_date` filters. The code
  already used `after_date`, so nothing was broken, but following the
  documentation here would ship 2023 coverage summarized as this week's news.
- **`excerpts.max_chars_per_result` is a ceiling, not a target.** Uncapped
  `one-shot` averages ~3000 characters per result; asking for 2500 returns
  ~1050. News therefore sets no cap. The social sweeps keep one on purpose: a
  thread's excerpt is mostly other people's replies.
- **`after_date` shrinks excerpts as well as the result count**, because
  recently indexed pages carry less text. Fresh beats long, deliberately.
- **FindAll `exclude_list` entries require both `name` and `url`.** A bare
  `{"name": ...}` is a 422 naming the missing `url`.

Search moved to `/v1beta/search` with `one-shot`: about three times the excerpt
text at half the latency, and excerpt text is what the briefing is written
from. FindAll now sends the watchlist as `exclude_list` rather than filtering
matches out afterwards, so `match_limit` is spent on names that could be new.

### Deployment

- **Cold start was 11.96s**, and a judge makes exactly one cold request.
  `--min-instances=1` took the first request to 2.76s and subsequent ones under
  a second.
- **`/healthz` returned Google's own 404 page** while every other route served
  fine, which reads as a broken deploy. The front end answers that path before
  the request reaches the container: the response carries Google's error HTML
  and none of this app's headers, and `/healthz/` with a trailing slash reaches
  the app. The check now also answers on `/health`.
- **ClickHouse was claimed in the README stack table and does not exist.**
  Removed. Storage is Firestore in production and SQLite locally.

### A front door

The deployed URL opened straight onto somebody else's watchlist. The watchlist
moved to `/app` and `/` is now a page that names the problem: a filing is
public on Monday and reaches its holder on Thursday, via a price move they
cannot explain.

Everything it shows is read from stored history, including the reel of real
findings and the briefing card beside the headline. Where there is nothing
stored, each element says so rather than showing a mock-up.

### Still to do

- [ ] Multi-user watchlists
- [ ] Per-ticker alert labels. The Grafana rules aggregate across the whole
      watchlist (`MIN(change_pct)`, `COUNT(*)`), so a notification can say a
      target was cut without naming the company. Making them multi-dimensional
      means reworking each query to group by ticker.
- [ ] Settings frequency should drive the Cloud Scheduler job
- [ ] Cache a demo dataset so the 3-minute video never depends on a live
      upstream

## SEO: turning queries into indexable pages (future, not scoped yet)

Discussed 2026-09-08. Nothing here is built. The idea: a question typed into
Discover or Ask produces a real URL, so the site can rank for the thing people
actually search ("stocks similar to ONDS", "US defense stocks"). The value is
real, but three separate problems hide inside it and they have different
answers.

### The shape of the query space, which is not what it looks like

The split is not Discover versus Ask. Both take free text: `/discover?q=` is a
box, not a menu, and the same intent arrives as "rddt peers", "other stocks
similar to RDDT" and "who competes with Reddit". The chips are the only
templated part of Discover, and they are a small minority of what gets typed.

So there are two populations, and they cut across both pages:

- **Templated.** Ticker plus a fixed frame, generated by us: the "Peers of X"
  chips. The URL space is finite (one per ticker), known ahead of time, and
  nobody's words are in it.
- **Free text.** Everything typed into either box. Unbounded, duplicated by
  nature, and containing whatever the visitor felt like writing.

Only the first is safe to publish as-is. Publishing the second one URL per
query is the "search results inside search results" pattern Google names in its
own quality guidance: a hundred thin near-duplicate pages competing for one
intent, and the damage is not that they fail to rank, it is that they drag the
whole domain's quality signal down with them.

### Clustering: right direction, backwards implementation

The proposal was to publish everything and then redirect the duplicates onto
the winner. Do it the other way around: cluster first, publish once, and never
create the losers as pages at all.

1. Every query keeps being stored (`recent_questions` already does this), but
   `noindex`, out of the sitemap. Storage is not publication.
2. A batch job (weekly, offline, never in the request path) embeds the stored
   queries and clusters them by intent.
3. Each cluster with enough demand gets **one** canonical page, at a clean URL,
   with a title we wrote. The rest of the cluster never becomes a URL.

Mass 301s are themselves a low-quality signal, and they are painful to rewrite
when a cluster's centre moves. Publishing only the canonical has neither
problem.

The step missing from the original plan: **which formulation wins is not
decided by our own traffic.** Internal frequency says what visitors here typed;
it says nothing about what is searched on Google. That number comes from
Keyword Planner or DataForSEO (the MCP is already configured on this machine),
and it is the one that picks the canonical.

### The privacy line, which is not optional

A ticker plus a frame identifies nobody. Free text does: "should I sell my 4000
ONDS shares before earnings" is personal financial information, and indexing it
would be a real problem rather than a matter of taste.

Therefore free-text queries are never published verbatim, ever. What gets
published is the **rewritten canonical** for a cluster, a sentence we author.
The stored original stays unindexed. Note this cuts against the current privacy
page, which tells visitors their questions are stored and shared with other
visitors: shared inside the product is not the same promise as indexed by
Google under a permanent URL, and publishing would need that page revisited
first.

### The paywall is allowed, and has a name

Letting Google read the whole page while a visitor sees one result is
**flexible sampling / metered paywall**, and it is explicitly supported: mark
the page with schema.org `isAccessibleForFree: false` plus `hasPart` naming the
gated block. What gets penalised as cloaking is serving different HTML by
user-agent *without* that markup. The product already splits along a natural
line: confirmed peers with their evidence are the hook, briefings and alerts
are the paid side.

### Order to do it in

1. **Cheapest and first: `noindex` on `/ask` and `/discover` when they carry
   a query.** Today `robots.txt` only disallows `/hooks/`, `/tasks/` and
   `/api/`, so every free-text result URL is crawlable right now. This is one
   line and it is the only item here worth doing before any of the rest.
2. Programmatic per-ticker pages (`/similar-to/<TICKER>`) built from the
   templated axis, independent of anything a user typed. This is most of the
   SEO value and carries none of the duplication or privacy risk.
3. The offline clusterer, publishing rewritten canonicals validated against
   real search volume.
4. The metered paywall, once there is something worth charging for.

### The cost trap that governs all of it

Every one of those pages is a FindAll, and FindAll is the one API here priced
per query plus per match: about $1.47 per ticker at `base` across the three
facets. A thousand tickers is roughly $1,500, and it cannot be regenerated
casually. These pages have to be generated once, cached as stored data, and
refreshed in controlled batches. Generating on request is how a single Google
crawl empties the account in an afternoon, and unlike a human visitor a crawler
will happily request every URL in the sitemap back to back.
