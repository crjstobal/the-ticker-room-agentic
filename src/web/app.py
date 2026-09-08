"""The Ticker Room — web front end.

Single-user for now: no auth, no accounts. The watchlist lives in SQLite and
the pages read the stored history.
"""
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse, Response)

from src.core import discovery
from src.core import repo
from src.core import runner
from src.core.parallel_api import NoCredit
from src.core.runner import run_for_user
from src.core import filings as filings_mod
from src.web.explain import render as page_explain
from src.web.legal import (page_cookies, page_legal_notice, page_privacy,
                          page_sitemap, page_terms, robots_txt, sitemap_xml)
from src.web.home import build_frames, page_home
from src.web.render import (page_ask, page_discover, page_index,
                            page_settings, page_ticker)

USER = "javi"

app = FastAPI(title="The Ticker Room")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """The front door, for someone who does not use this yet.

    The watchlist moved to /lobby when this page took the root: a first-time
    visitor landing on somebody else's tickers had no way to tell what the
    product was for, and the deployed URL is a judged deliverable as well as a
    product entrance.
    """
    # The reel draws on everything the agent has found, not only on events
    # caught between runs: a quiet day would otherwise leave the page's main
    # element empty while hundreds of extracted rows sat unshown.
    tickers = [r["ticker"] for r in repo.get_watchlist(USER)]
    revisions, filings = [], []
    for tk in tickers:
        revisions.extend(repo.target_revisions(tk))
        filings.extend(filings_mod.notable(repo.latest_filings(tk, limit=12)))
    revisions.sort(key=lambda r: r.get("date", ""), reverse=True)
    filings.sort(key=lambda f: f.get("filed_date", ""), reverse=True)

    # The proof card shows a real briefing rather than describing one. The
    # most-covered ticker is used, since that is the one whose briefing has
    # the most citations to point at.
    briefings = [b for b in repo.latest_briefings(USER) if b.get("body")]
    sample = None
    if briefings:
        sample = max(briefings, key=lambda b: b.get("n_articles") or 0)
        sample = {**sample, "quote": repo.latest_quote(sample["ticker"])}

    return page_home(
        build_frames(repo.recent_events(limit=6), revisions[:5], filings[:8]),
        repo.corpus_stats(),
        sample,
        repo.last_run(),
    )


@app.get("/lobby", response_class=HTMLResponse)
def index(sort: str = "") -> str:
    """The lobby. `sort` picks the ordering; an unknown value falls back."""
    briefings = repo.latest_briefings(USER)
    for b in briefings:
        b["quote"] = repo.latest_quote(b["ticker"])
        b["coverage"] = repo.coverage_series(b["ticker"])
        b["sentiment"] = repo.latest_sentiment(b["ticker"])
        # Only the headline flags reach the lobby; the detail is one click away.
        from src.core.filings import notable
        from src.web.render import KIND_STYLE

        seen = set()
        flags = []
        for e in notable(repo.latest_filings(b["ticker"], limit=30)):
            cls, label = KIND_STYLE.get(e["kind"], ("", ""))
            if label and label not in seen:
                seen.add(label)
                flags.append((cls, {"Sold": "Insider sold", "Bought": "Insider bought",
                                    "Dilution": "Dilution"}.get(label, label)))
        b["flags"] = flags
    return page_index(briefings, repo.last_run(), sort=sort)


@app.get("/lobby/{ticker}", response_class=HTMLResponse)
def ticker_detail(ticker: str) -> str:
    ticker = ticker.upper()
    rows = [t for t in repo.all_tickers() if t["ticker"] == ticker]
    name = rows[0]["company_name"] if rows else ticker
    briefings = [b for b in repo.latest_briefings(USER) if b["ticker"] == ticker]
    briefing = briefings[0] if briefings else None

    # Citation previews whose stored excerpt is page furniture are re-fetched
    # through Parallel's Extract API, so a hover shows a sentence rather than
    # an empty card. Best effort: the page renders either way.
    if briefing and briefing.get("sources"):
        try:
            briefing = {**briefing, "sources": repo.repair_previews(
                briefing["sources"], objective=f"{name} ({ticker}) news")}
        except Exception as exc:
            print(f"[web] preview repair failed for {ticker}: {exc}")

    from src.core.settings import section_order

    ticker_events = repo.recent_events(ticker, limit=10)
    monitor = repo.monitor_for_ticker(ticker)

    # Only when the box would otherwise be empty: Parallel reports a run it
    # could not perform as an entry inside the events list, so "no events" and
    # "the watch has been broken for days" are the same response. Asking costs
    # one call and only happens on the pages where the distinction matters.
    watch_failed, watch_failed_at = 0, ""
    if monitor and not ticker_events:
        try:
            from src.core import monitors as _mon

            errs = _mon.error_events(monitor["monitor_id"])
            watch_failed = len(errs)
            watch_failed_at = errs[0].get("timestamp", "") if errs else ""
        except Exception as exc:
            print(f"[web] watch health check failed for {ticker}: {exc}")

    return page_ticker(
        events=ticker_events,
        monitor=monitor,
        watch_failed=watch_failed,
        watch_failed_at=watch_failed_at,
        alerts=_alerts_for(ticker),
        ticker=ticker,
        company_name=name,
        briefing=briefing,
        order=section_order(repo.all_settings()),
        quote=repo.latest_quote(ticker),
        # More than the lobby's dozen: the coverage chart cites the articles
        # behind each bar, so a day whose stories fell outside the limit would
        # show a bar with nothing to open.
        articles=repo.recent_articles(ticker, limit=200),
        coverage=repo.coverage_series(ticker),
        sentiment=repo.latest_sentiment(ticker),
        targets=repo.latest_targets(ticker),
        revisions=repo.target_revisions(ticker),
        filings=repo.latest_filings(ticker),
        last_run=repo.last_run(),
    )


@app.get("/how-it-works", response_class=HTMLResponse)
def how_it_works() -> str:
    """The explainer: what the room is, and how it is wired."""
    return page_explain(repo.last_run())


# The sitemap and the legal set. They carry no logic of their own, which is the
# point: the pages are static prose and the only thing the route does is hand
# them the last run so their shell matches every other page.
@app.get("/sitemap", response_class=HTMLResponse)
def sitemap_page() -> str:
    """Every route in one place, including the ones nothing links to."""
    return page_sitemap(repo.last_run())


@app.get("/sitemap.xml")
def sitemap_file(request: Request) -> Response:
    """The crawler's copy.

    The base URL comes from the request rather than a constant, so the file is
    correct on localhost, on the Cloud Run URL and on any domain put in front
    of it later. A hardcoded host would publish absolute URLs pointing at the
    wrong deployment, which is worse than publishing none.
    """
    base = str(request.base_url).rstrip("/")
    return Response(sitemap_xml(base), media_type="application/xml")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request) -> str:
    return robots_txt(str(request.base_url).rstrip("/"))


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page() -> str:
    return page_privacy(repo.last_run())


@app.get("/terms", response_class=HTMLResponse)
def terms_page() -> str:
    return page_terms(repo.last_run())


@app.get("/legal-notice", response_class=HTMLResponse)
def legal_notice_page() -> str:
    return page_legal_notice(repo.last_run())


@app.get("/cookies", response_class=HTMLResponse)
def cookies_page() -> str:
    return page_cookies(repo.last_run())


@app.get("/settings", response_class=HTMLResponse)
def settings_page(saved: int = 0) -> str:
    return page_settings(repo.all_settings(), repo.last_run(), bool(saved))


@app.post("/settings")
async def save_settings(request: Request):
    # No `section_order`: the order of the blocks on a ticker page is fixed in
    # `settings.SECTIONS` now. A stored value left over from when this was
    # configurable is simply ignored rather than migrated.
    form = await request.form()
    repo.set_settings({
        "alerts_enabled": "1" if form.get("alerts_enabled") else "0",
        "reddit_enabled": "1" if form.get("reddit_enabled") else "0",
        "spike_multiplier": form.get("spike_multiplier", "2.0"),
        "spike_floor": form.get("spike_floor", "5"),
        "run_frequency": form.get("run_frequency", "weekly"),
    })
    return RedirectResponse("/settings?saved=1", status_code=303)


@app.get("/ask", response_class=HTMLResponse)
def ask_page(q: str = "", again: str = "") -> str:
    """The analyst agent: an open question answered from the stored history.

    A question already answered is served from storage rather than asked again.
    Following a link in "Asked before" was re-running the whole agent loop plus
    Responses, twenty seconds and two paid calls, to arrive at an answer that
    was already sitting in Firestore. `again=1` forces a fresh run, which is
    what the "Ask again" button on a stored answer does.
    """
    result = second = None
    cached_at = ""

    if q.strip() and not again:
        try:
            prev = repo.find_question(USER, q.strip())
        except Exception as exc:  # noqa: BLE001 - a cache miss is not a failure
            print(f"[ask] lookup: {exc}")
            prev = None
        if prev and prev.get("answer"):
            result = {
                "answer": prev["answer"],
                # The trace is stored as tool names only, which is all the
                # tooltip renders.
                "trace": [{"tool": t, "args": {}} for t in (prev.get("tools") or [])],
            }
            cached_at = prev.get("asked_at") or ""

    if q.strip() and result is None:
        from concurrent.futures import ThreadPoolExecutor

        from src.core import responses

        def primary() -> dict:
            try:
                from src.adapters.agent_builder import ask as agent_ask

                return agent_ask(q.strip())
            except Exception as exc:
                return {"answer": "", "trace": [],
                        "error": f"{type(exc).__name__}: {exc}"}

        def secondary() -> dict:
            # Never allowed to break the page: the Gemini answer is the product,
            # this is a cross-check beside it.
            try:
                return responses.ask(q.strip())
            except Exception as exc:
                print(f"[ask] second opinion unavailable: {exc}")
                return {}

        # Run together rather than in sequence. Both spend their time waiting on
        # the network, and asking one after the other would add the whole of the
        # second one to a page a person is watching load.
        with ThreadPoolExecutor(max_workers=2) as pool:
            fa, fb = pool.submit(primary), pool.submit(secondary)
            result, second = fa.result(), fb.result()

        # Recorded once the answer exists. A question costs twenty seconds and
        # a paid call, and it used to vanish with the tab: the same one asked
        # twice was paid for twice and nobody could see what they had asked.
        if result and not result.get("error"):
            try:
                repo.save_question(USER, {
                    "kind": "ask",
                    "question": q.strip(),
                    "answer": result.get("answer") or "",
                    "tools": [t.get("tool", "") for t in (result.get("trace") or [])],
                })
            except Exception as exc:  # noqa: BLE001 - history must not break the page
                print(f"[ask] not recorded: {exc}")

    return page_ask(q, result, repo.last_run(), second=second,
                    history=_history("ask"), cached_at=cached_at)


def _alerts_for(ticker: str, limit: int = 15) -> list[dict]:
    """Alerts to show on one company's page.

    Every Grafana rule here aggregates over the whole watchlist, so the webhook
    arrives with no `ticker` label and a query scoped to one company matched
    nothing: the section said "No alerts for ONDS yet" on a product whose rules
    were firing all week, which reads as "nothing happened" rather than "this
    can never fill". Unlabelled alerts are watchlist-wide and belong on every
    ticker page; a labelled one is only shown on the company it names.
    """
    try:
        rows = repo.recent_alerts("", limit * 3)
    except Exception as exc:  # noqa: BLE001 - the page works without alerts
        print(f"[alerts] {ticker}: {exc}")
        return []
    want = ticker.upper()
    return [a for a in rows
            if not (a.get("ticker") or "").strip()
            or (a.get("ticker") or "").upper() == want][:limit]


def _history(kind: str, limit: int = 12) -> list[dict]:
    """Past questions of one kind. Never raises: an empty list just hides it."""
    try:
        return repo.recent_questions(USER, kind, limit)
    except Exception as exc:  # noqa: BLE001 - the page works without history
        print(f"[history] {kind}: {exc}")
        return []


@app.post("/tasks/run")
def scheduled_run():
    """Entry point for Cloud Scheduler.

    Separate from /run so the two are distinguishable in the history: a run
    stamped `scheduled` is the product working on its own, a `manual` one is
    somebody pressing the button.

    This sweeps every ticker anybody follows, deduplicated, rather than looping
    over watchlists: a ticker on ten of them is researched once and all ten
    readers get the same fresh rows.
    """
    results = runner.run_all(trigger="scheduled")
    return {
        "status": "ok",
        "tickers": len(results),
        "errors": [e for r in results for e in r.errors],
    }


@app.get("/api/metrics")
def api_metrics():
    """Metrics as JSON, for Grafana.

    Grafana reads this rather than the database directly, so the same panels
    work against SQLite locally and Firestore in the cloud without knowing
    which is behind it.
    """
    out = {"coverage": [], "sentiment": [], "quotes": []}
    for row in repo.get_watchlist(USER):
        ticker = row["ticker"]
        for point in repo.coverage_series(ticker, days=60):
            out["coverage"].append(
                {"ticker": ticker, "day": point["day"], "articles": point["articles"]}
            )
        s = repo.latest_sentiment(ticker)
        if s:
            out["sentiment"].append({
                "ticker": ticker, "score": s.get("score", 0),
                "label": s.get("label", ""), "n_threads": s.get("n_threads", 0),
                "captured_at": s.get("captured_at", ""),
            })
        q = repo.latest_quote(ticker)
        if q:
            out["quotes"].append({
                "ticker": ticker, "spot": q.get("spot"),
                "change_pct": q.get("change_pct"),
                "captured_at": q.get("captured_at", ""),
            })
    return out


# `/healthz` never reaches the container on Cloud Run: Google's front end
# answers it with its own 404 page before the request is proxied, which reads
# exactly like a broken deploy while every other route is fine (verified by the
# response carrying Google's error HTML and none of this app's headers, and by
# `/healthz/` with a trailing slash reaching the app and returning a redirect).
# The check lives at `/health` and `/healthz` is kept as an alias for anything
# already pointed at it locally.
@app.get("/health")
@app.get("/healthz")
def healthz():
    """Liveness, and what the running container actually resolved.

    The deployed service once failed on every route with an error from a
    dependency nobody had changed, and there was no way to see which version
    the container had installed short of rebuilding it. The versions are here
    so a deploy can be compared against a working local environment directly.
    """
    from importlib.metadata import PackageNotFoundError, version

    packages = {}
    for name in ("google-cloud-firestore", "google-api-core", "grpcio",
                 "protobuf", "googleapis-common-protos"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "absent"

    return {"status": "ok", "backend": repo.backend_name(),
            "python": sys.version.split()[0], "packages": packages}


# Adding a ticker is switched off. Every add kicks off an immediate research
# pass (Search plus two Task calls per ticker), so an open form on a public URL
# is a stranger spending this account's Parallel credit. There are no users yet
# and no per-user watchlists, so there is nothing to lose by closing it and a
# drained account to lose by leaving it open.
#
# The check is here and not only on the button: a disabled button is a picture
# of a closed door. `curl -d ticker=X` reaches this endpoint either way.
ADDS_OPEN = os.getenv("TICKERROOM_ALLOW_ADD") == "1"


@app.post("/watchlist/add")
def add_ticker(background: BackgroundTasks, ticker: str = Form(...),
               company_name: str = Form(...)):
    """Add a ticker and start researching it straight away.

    Without this the card sat empty until the scheduler came round, which for a
    ticker just accepted from /discover is the first thing the user sees and
    reads as broken. The research runs in the background so the redirect is
    immediate; the page shows each section with its placeholder until the pass
    lands.

    Closed unless TICKERROOM_ALLOW_ADD=1. See ADDS_OPEN above.
    """
    if not ADDS_OPEN:
        return JSONResponse(
            {"error": "adding_disabled",
             "detail": "Adding tickers is not open yet. Each add starts a paid "
                       "research pass, so the form is closed until watchlists "
                       "are per-user."},
            status_code=403)
    ticker = ticker.strip().upper()
    company = company_name.strip()
    repo.add_to_watchlist(USER, ticker, company)
    background.add_task(_research_one, ticker, company)
    return RedirectResponse("/lobby", status_code=303)


def _research_one(ticker: str, company: str) -> None:
    """Research a single newly added ticker, off the request path."""
    import uuid

    from src.core.runner import run_for_ticker

    run_id = uuid.uuid4().hex[:12]
    repo.start_run(run_id, 1, "added")
    try:
        res = run_for_ticker(ticker, company, run_id)
        if res.errors:
            print(f"[web] {ticker} added with errors: {res.errors}")
    except Exception as exc:
        print(f"[web] research failed for {ticker}: {exc}")
    finally:
        repo.finish_run(run_id)


@app.post("/watchlist/remove")
def remove_ticker(ticker: str = Form(...)):
    """Stop watching a ticker, and stop paying to watch it.

    The Parallel monitor is cancelled too: a watch left running after its
    ticker is gone keeps checking hourly forever, and nothing in the app would
    ever show it again.
    """
    ticker = ticker.strip().upper()
    row = repo.monitor_for_ticker(ticker)
    if row:
        from src.core import monitors as mon

        try:
            mon.cancel(row["monitor_id"])
        except Exception as exc:
            print(f"[web] could not cancel monitor for {ticker}: {exc}")
        repo.set_monitor_status(row["monitor_id"], "cancelled")

    repo.remove_from_watchlist(USER, ticker)
    return RedirectResponse("/lobby", status_code=303)


@app.post("/run")
def trigger_run():
    run_for_user(USER)
    return RedirectResponse("/lobby", status_code=303)


# --- Parallel monitors -------------------------------------------------

@app.post("/hooks/parallel")
async def parallel_webhook(request: Request, background: BackgroundTasks):
    """Events pushed by Parallel when a watched ticker changes.

    This is the interrupt path. The scheduled run is a pull twice a weekday;
    this arrives when something actually happened, which is the difference
    between a report that is half a day stale and one that is not.

    The payload carries only an identifier, so the event itself is fetched
    back: a webhook body is not a trustworthy source of record.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "unreadable body"}

    data = (payload or {}).get("data") or {}
    monitor_id = data.get("monitor_id", "")
    if not monitor_id:
        return {"status": "ignored", "reason": "no monitor_id"}

    known = {m["monitor_id"]: m for m in repo.get_monitors(active_only=False)}
    row = known.get(monitor_id)
    if not row:
        # Not one of ours: another environment sharing the API key.
        return {"status": "ignored", "reason": "unknown monitor"}

    from src.core import monitors as mon

    group = ((data.get("event") or {}).get("event_group_id")) or ""
    try:
        events = mon.events(monitor_id, event_group_id=group)
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

    stored = [e for e in events
              if repo.save_monitor_event(monitor_id, row["ticker"], e)]

    # Promote what the event contains into rows the rest of the product reads.
    # Only new events: re-promoting one already ingested would double-count a
    # target every time Parallel redelivered the same webhook.
    #
    # Deliberately after the response rather than inside it. Promotion runs two
    # Task extractions and can take minutes, and a webhook that holds its
    # connection open that long is one the sender times out and retries, which
    # would run the same extractions again. The event is durable the moment it
    # is stored above, so acknowledging first loses nothing.
    background.add_task(_promote, stored, row["ticker"],
                        row.get("company_name") or row["ticker"])

    return {"status": "ok", "ticker": row["ticker"], "events": len(events),
            "new": len(stored), "promoting": len(stored)}


def _promote(events: list[dict], ticker: str, company: str) -> dict:
    """Turn caught events into targets and filings. Never raises.

    A webhook that 500s gets retried by Parallel, and retrying an event whose
    prose was already stored would be the wrong fix for a failed extraction.
    """
    from src.core import ingest

    totals = {"targets": 0, "filings": 0}
    for e in events:
        try:
            got = ingest.from_event(
                e, ticker, company,
                save_targets=repo.save_targets,
                save_filings=repo.save_filings,
            )
        except Exception as exc:
            print(f"[hooks] promote failed for {ticker}: {exc}")
            continue
        totals["targets"] += got.get("targets", 0)
        totals["filings"] += got.get("filings", 0)
    return totals


@app.post("/hooks/grafana")
async def grafana_webhook(request: Request):
    """Alerts Grafana fired, recorded so they outlive the moment.

    The rules have always evaluated; what was missing was a receiver. An alert
    that only turns a panel red is visible to whoever is looking at Grafana at
    that second and to nobody else, which for a product whose whole promise is
    "you do not have to watch" is the wrong way round.

    Grafana posts a batch. Each alert carries its own fingerprint, so a repeat
    notification about a still-firing condition updates rather than duplicates.
    """
    # This endpoint is public, and unlike the Parallel hook it cannot verify
    # what it is sent: it writes the posted alert rather than fetching it back
    # from anywhere. A shared secret keeps a stranger from posting invented
    # alerts into the history.
    #
    # Enforced only when the secret is configured. Locally there is none and
    # the endpoint stays open, which is what makes it testable with curl; on
    # Cloud Run TICKERROOM_ALERT_TOKEN is set and the check is live.
    expected = os.environ.get("TICKERROOM_ALERT_TOKEN", "")
    if expected and not hmac.compare_digest(
            request.headers.get("x-tickerroom-token", ""), expected):
        return JSONResponse({"status": "denied"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "unreadable body"}

    stored = 0
    for a in (payload or {}).get("alerts") or []:
        labels = a.get("labels") or {}
        annotations = a.get("annotations") or {}
        fingerprint = a.get("fingerprint") or ""
        if not fingerprint:
            continue
        # `values` maps each expression refId to what it evaluated to. The
        # number that tripped the rule is more useful in the record than the
        # fact that something tripped it.
        values = a.get("values") or {}
        value = ", ".join(f"{k}={v}" for k, v in values.items()) if values else ""
        stored += repo.save_alert({
            "fingerprint": fingerprint,
            "ticker": (labels.get("ticker") or "").upper(),
            "rule": labels.get("alertname") or annotations.get("summary", "")[:80],
            "kind": labels.get("kind", ""),
            "severity": labels.get("severity", ""),
            "status": a.get("status") or payload.get("status") or "firing",
            "summary": annotations.get("summary", ""),
            "value": value,
            "started_at": a.get("startsAt", ""),
        })
    return {"status": "ok", "new": stored}


@app.post("/watch/refresh")
def watch_refresh(ticker: str = Form("")):
    """Pull events without waiting for a webhook.

    Locally there is no public URL for Parallel to call, so the monitors are
    created without a webhook and this is how their events are collected. In
    the demo it also makes the interrupt path filmable on demand.

    Scoped to one ticker, because that is the page the button lives on now.
    Without a ticker it still sweeps every watch, which is what the scheduled
    path and a bare curl expect.
    """
    from src.core import monitors as mon

    ticker = (ticker or "").upper()
    rows = repo.get_monitors(active_only=True)
    if ticker:
        rows = [m for m in rows if m["ticker"] == ticker]

    for m in rows:
        try:
            # Parallel records a failed run as an entry in the events list
            # rather than failing the call, so a monitor that has been unable
            # to run for days returns "no events" and reads as a quiet week.
            # Surfaced here because this button is where somebody goes when
            # they expected something and got nothing.
            errs = mon.error_events(m["monitor_id"])
            if errs:
                first = (errs[0].get("error_message") or "").strip()
                print(f"[watch] {m['ticker']}: {len(errs)} failed runs, "
                      f"latest {errs[0].get('timestamp','')}: {first[:120]}")
            fresh = [e for e in mon.events(m["monitor_id"])
                     if repo.save_monitor_event(m["monitor_id"], m["ticker"], e)]
            # The same promotion the webhook does, so the pull path and the
            # push path produce identical state. Without this, a demo recorded
            # locally would behave differently from the deployed service.
            _promote(fresh, m["ticker"], m.get("company_name") or m["ticker"])
        except Exception as exc:
            print(f"[watch] {m['ticker']}: {exc}")
    return RedirectResponse(f"/lobby/{ticker}" if ticker else "/lobby", status_code=303)


# --- discovery ---------------------------------------------------------

# The three run ids travel in one query parameter as `facet:id` pairs. A
# separate parameter per facet would make the URL depend on the facet list,
# so adding a fourth axis later would mean touching every link that builds one.
def _parse_runs(runs: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (runs or "").split(","):
        facet, _, rid = part.partition(":")
        if facet in discovery.FACETS and rid:
            out[facet] = rid
    return out


def _start_facets(row: dict, skip: list[dict], peers: str) -> str:
    """Start every facet of a peer search and return the URL that polls them.

    Started in parallel: each run takes minutes, and three sequential starts
    would have the reader watching the first column finish before the third
    had begun. Without a profile there are no axes to relax, so this falls
    back to the original single peer search.
    """
    from src.core import profile as company_profile

    prof = company_profile.of(row["ticker"], row["company_name"])
    if not prof:
        rid = discovery.start_peers(row["ticker"], row["company_name"],
                                    exclude=skip)
        return f"/discover?run={rid}&peers={quote_plus(peers)}"

    started: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(discovery.FACETS)) as pool:
        futures = {
            pool.submit(discovery.start_facet, f, prof, exclude=skip): f
            for f in discovery.FACETS
        }
        for fut in futures:
            facet = futures[fut]
            try:
                started[facet] = fut.result()
            except NoCredit:
                raise
            except Exception as exc:  # noqa: BLE001 - one facet may fail alone
                print(f"[discover] facet {facet} did not start: {exc}")

    if not started:
        raise RuntimeError("no facet of the peer search could be started")
    pairs = ",".join(f"{f}:{started[f]}" for f in discovery.FACETS if f in started)
    return f"/discover?runs={quote_plus(pairs)}&peers={quote_plus(peers)}"


@app.get("/discover", response_class=HTMLResponse)
def discover_page(q: str = "", peers: str = "", run: str = "", runs: str = ""):
    """Tickers the watchlist does not have yet.

    A discovery takes minutes: candidates are generated from the web, then each
    is checked against every condition. So the page starts a run and redirects
    to itself carrying the run id, then polls. Holding an HTTP request open for
    five minutes would time out in front of the user.

    Nothing here adds anything on its own: a research tool that quietly grew
    someone's watchlist would be making a decision that is not its to make.
    Each suggestion is a proposal with a reason and a source.
    """
    from src.core import profile as company_profile

    watchlist = repo.get_watchlist(USER)
    known = {r["ticker"].upper() for r in watchlist}
    results: list[dict] = []
    objective, error = "", ""
    status: int | None = None
    state: dict = {}
    facets: list[dict] = []
    profile: dict = {}
    running = False
    rows: list[dict] = []

    if peers:
        rows = [r for r in watchlist if r["ticker"].upper() == peers.upper()]
        if rows:
            # The profile names the axes the facets are built on, and the page
            # prints it: a reader who disagrees with "defense / counter-UAS"
            # can see why the three columns hold what they hold.
            try:
                profile = company_profile.of(rows[0]["ticker"],
                                             rows[0]["company_name"])
            except Exception as exc:  # noqa: BLE001 - a profile is optional
                print(f"[discover] no profile for {peers}: {exc}")
            objective = discovery.peers_objective(
                rows[0]["ticker"], rows[0]["company_name"])
            known = known | {rows[0]["ticker"].upper()}
    elif q.strip():
        objective = q.strip()

    if runs:
        # A faceted peer search is three independent runs, each finishing on
        # its own schedule. They are polled together so the page can fill in
        # one column at a time instead of waiting for the slowest.
        for facet, rid in _parse_runs(runs).items():
            st = discovery.progress(rid)
            facets.append({
                "facet": facet,
                "label": discovery.FACET_LABELS.get(facet, facet),
                "caption": discovery.facet_caption(facet, profile),
                "state": st,
                "results": discovery.collect(rid, exclude=known),
            })
            # One facet out of credit is the whole account out of credit, and
            # the page says so once rather than three times.
            error = error or st.get("error", "")
            status = status or st.get("status")
        running = any(f["state"].get("running") for f in facets)
    elif run:
        state = discovery.progress(run)
        error = state.get("error", "")
        status = state.get("status")
        results = discovery.collect(run, exclude=known)
    elif objective:
        try:
            # The watchlist is excluded by the API rather than filtered out
            # of the result, so match_limit is spent on candidates that could
            # actually be new.
            skip = discovery.exclude_list(watchlist)
            if peers and rows:
                return RedirectResponse(
                    _start_facets(rows[0], skip, peers), status_code=303)
            new_run = discovery.start(objective, exclude=skip)
            target = f"/discover?run={new_run}&q={quote_plus(q.strip())}"
            return RedirectResponse(target, status_code=303)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            # The HTTP code is what tells a spent account from a rate limit
            # from a bad key, and the page renders a different sentence for
            # each. Without it every failure looked the same to the user.
            status = getattr(exc, "status", None)

    # Recorded only once a search has actually finished. The page polls itself
    # every few seconds while a run is in flight, and recording on each poll
    # would write the same search a dozen times.
    n_found = len(results) + sum(len(f["results"]) for f in facets)
    if (run or runs) and not running and not error and n_found:
        asked = q.strip() or (f"Companies like {peers.upper()}" if peers else "")
        if asked:
            try:
                # Revisiting a stored search renders the same run ids again, so
                # without this check it would file itself on every visit.
                if not repo.find_question(USER, asked, kind="discover"):
                    repo.save_question(USER, {
                        "kind": "discover", "question": asked,
                        "ticker": peers.upper(), "n_results": n_found,
                        # The run ids are what make this replayable. A finished
                        # FindAll keeps its result on Parallel's side, so going
                        # back to a past search reads something already paid
                        # for; without them the only way back is three fresh
                        # runs, minutes long and the priciest call here.
                        "answer": runs if runs else f"run:{run}",
                    })
            except Exception as exc:  # noqa: BLE001 - history is not the product
                print(f"[discover] not recorded: {exc}")

    return HTMLResponse(page_discover(
        query=q, peers=peers, objective=objective, results=results,
        watchlist=watchlist, error=error, state=state, run_id=run,
        last_run=repo.last_run(), status=status, facets=facets,
        profile=profile, running=running, history=_history("discover", 8),
    ))
