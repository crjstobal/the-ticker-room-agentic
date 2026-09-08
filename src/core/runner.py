"""One research pass over a user's watchlist.

Design rule inherited from the previous system: the run always completes.
No secondary source is allowed to abort it. A failing search yields no news,
a failing quote yields no price context, a failing model yields no briefing,
and everything else still gets stored.
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

# A watchlist is small and every stage is network-bound, so one thread per
# ticker is enough. The cap keeps a long list from opening a burst of
# connections to Parallel at once.
MAX_PARALLEL_TICKERS = 6

from .parallel_api import NoCredit
from . import (filings, monitors, quotes, repo, research, sentiment,
               summarize, targets)


@dataclass
class TickerResult:
    ticker: str
    company_name: str
    quote: dict | None = None
    articles: list[dict] = field(default_factory=list)
    new_articles: int = 0
    reddit: dict | None = None
    targets: list[dict] = field(default_factory=list)
    filings: list[dict] = field(default_factory=list)
    briefing: str = ""
    errors: list[str] = field(default_factory=list)


def ensure_monitor(ticker: str, company_name: str) -> dict | None:
    """Make sure this ticker has an active Parallel monitor, creating one if not.

    Idempotent: a monitor already recorded for the ticker is left alone, so a
    run every four hours does not create a new watch every four hours.
    """
    existing = repo.monitor_for_ticker(ticker)
    if existing:
        return existing
    created = monitors.create(ticker, company_name)
    record = {
        "monitor_id": created["monitor_id"],
        "ticker": ticker.upper(),
        "company_name": company_name,
        "frequency": created.get("frequency", ""),
        "processor": created.get("processor", ""),
        "status": created.get("status", "active"),
        "created_at": created.get("created_at", ""),
    }
    repo.save_monitor(record)
    print(f"[runner] watching {ticker} via {record['monitor_id']}")
    return record


def run_for_ticker(ticker: str, company: str, run_id: str, *, mode: str = "") -> TickerResult:
    """Research one ticker. Never raises: every stage degrades on its own.

    Split out of the watchlist loop so a single ticker can be refreshed on its
    own, which is what a newly added one needs: waiting for the next scheduled
    sweep to see anything at all made adding a ticker feel broken.
    """
    res = TickerResult(ticker=ticker, company_name=company)

    # A watch is declared once and then runs on Parallel's side between
    # runs. This is the interrupt path; the run itself is the periodic one.
    try:
        ensure_monitor(ticker, company)
    except Exception as exc:
        res.errors.append(f"monitor failed: {exc}")

    res.quote = quotes.fetch_quote(ticker)
    if res.quote:
        repo.save_quote(res.quote)
    else:
        res.errors.append("no price data")

    news_mode = mode or research.NEWS_MODE
    social_mode = mode or research.SOCIAL_MODE

    # NoCredit is deliberately not caught anywhere below: with an empty account
    # every lookup fails, and a run that "succeeds" with nothing to show is a
    # quiet week the product never had. Let it abort the ticker and be seen.
    res.articles = research.search_news(ticker, company, mode=news_mode)
    if res.articles:
        res.new_articles = repo.save_articles(ticker, res.articles, run_id)

    threads = research.search_reddit(ticker, company, mode=social_mode)
    x_posts = research.search_x(ticker, company, mode=social_mode)
    res.reddit = sentiment.analyze(ticker, company, threads, x_posts=x_posts)
    repo.save_sentiment(ticker, res.reddit, run_id)

    # Analyst targets change slowly, so this runs but never blocks the rest.
    try:
        res.targets = targets.fetch_targets(ticker, company)
        repo.save_targets(ticker, res.targets, run_id)
    except NoCredit:
        raise  # out of credit is a stopped run, not a thin one
    except Exception as exc:
        res.errors.append(f"targets failed: {exc}")

    try:
        res.filings = filings.fetch_filings(ticker, company)
        repo.save_filings(ticker, res.filings, run_id)
    except NoCredit:
        raise  # out of credit is a stopped run, not a thin one
    except Exception as exc:
        res.errors.append(f"filings failed: {exc}")

    try:
        out = summarize.summarize(ticker, company, res.quote, res.articles)
        res.briefing = out["text"]
        repo.save_briefing(ticker, res.briefing, out["model"], res.articles, run_id)
    except summarize.TruncatedResponse as exc:
        res.errors.append(f"truncated: {exc}")
    except NoCredit:
        raise  # out of credit is a stopped run, not a thin one
    except Exception as exc:
        res.errors.append(f"summary failed: {exc}")

    return res


def run_tickers(watchlist: list[dict], *, mode: str = "",
                trigger: str = "manual", metrics_user: str = "") -> list[TickerResult]:
    """Research the given tickers, all of them at once.

    Takes a list of tickers rather than a user, because research is per ticker
    and not per subscriber: the articles, filings and targets stored for ONDS
    are the same rows whoever asked for them. Callers that mean "everything
    anybody follows" pass repo.all_tickers(), which is deduplicated, so twenty
    users watching ONDS cost one research pass rather than twenty. That is the
    difference between a bill that grows with tickers and one that grows with
    users times tickers.

    `mode` overrides Parallel's search preset for every search. Left empty,
    each search picks its own: the news feeding the briefing runs at the
    highest-quality preset, the social sweeps run fast across many queries.

    Tickers are researched concurrently. Each one makes two Task calls that
    take one to three minutes each and spend that time waiting on the network,
    so running them in sequence made a run take as long as the sum of its parts
    for no reason. A watchlist is small, so a thread per ticker is the whole
    scheduling story, capped so a long list cannot open an unbounded number of
    connections at once.
    """
    run_id = uuid.uuid4().hex[:12]
    repo.start_run(run_id, len(watchlist), trigger)

    results: list[TickerResult] = []
    out_of_credit = False
    if watchlist:
        with ThreadPoolExecutor(max_workers=min(len(watchlist), MAX_PARALLEL_TICKERS)) as pool:
            futures = {
                pool.submit(run_for_ticker, row["ticker"], row["company_name"],
                            run_id, mode=mode): row
                for row in watchlist
            }
            for fut in as_completed(futures):
                row = futures[fut]
                try:
                    results.append(fut.result())
                except NoCredit as exc:
                    # Flagged rather than re-raised: the run still needs to be
                    # finished and stamped, so the UI can say why it stopped.
                    out_of_credit = True
                    results.append(TickerResult(
                        ticker=row["ticker"], company_name=row["company_name"],
                        errors=[f"out of credit: {exc}"]))
                except Exception as exc:
                    # A ticker that fails outright must not take the run with it.
                    results.append(TickerResult(
                        ticker=row["ticker"], company_name=row["company_name"],
                        errors=[f"run failed: {exc}"]))
    results.sort(key=lambda r: r.ticker)

    repo.finish_run(run_id)
    if out_of_credit:
        # Recorded on the run, not merely printed, so the pages can say why the
        # numbers stopped moving instead of showing a week that was never quiet.
        repo.set_run_error(run_id, "no_credit")
        print("[runner] STOPPED: the Parallel account is out of credit")

    # Refresh the Grafana projection so the dashboard never lags a run behind.
    try:
        from . import metrics_export

        metrics_export.export(metrics_user)
    except Exception as exc:
        print(f"[runner] metrics export failed: {exc}")

    return results


def run_for_user(user_id: str, *, mode: str = "", trigger: str = "manual") -> list[TickerResult]:
    """Research one user's watchlist. Kept for the manual /run button.

    The scheduled sweep does not come through here: it walks every ticker
    anybody follows, once each, via run_tickers(repo.all_tickers()).
    """
    return run_tickers(repo.get_watchlist(user_id), mode=mode, trigger=trigger,
                       metrics_user=user_id)


def run_all(*, mode: str = "", trigger: str = "scheduled") -> list[TickerResult]:
    """Research every ticker anybody follows, once each.

    This is what the scheduler calls. The saving is the whole point: research
    is stored per ticker, so a ticker on ten watchlists is researched once and
    all ten readers see the same fresh rows.
    """
    return run_tickers(repo.all_tickers(), mode=mode, trigger=trigger)
