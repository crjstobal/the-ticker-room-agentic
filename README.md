# The Ticker Room

An agentic stock news radar. You bring a watchlist, it watches the web for you.

**Live:** https://ticker-room-372773300560.europe-west1.run.app

**Status:** work in progress. Built for the Agentic Cinema hackathon (deadline 2026-09-09).

## What it does

You add the tickers you care about. On your schedule, an agent researches each one
across the open web, summarizes what actually moved, and stores it. Over time the
history becomes the product: coverage spikes, sentiment drift, and how the stock
reacted to past events.

Between those runs it keeps watching: each ticker has a standing Parallel monitor
that reports material events as they happen rather than at the next sweep. And it
can widen the watchlist as well as deepen it, proposing companies you have not
named yet with the evidence for each.

## How Parallel is used

All six of Parallel's APIs, each for the thing it is actually good at.
Six and not nine: the product page lists nine cards, but Interactions,
Deep Research and Enrichment are all labelled Task API, so they are use
cases of one endpoint rather than separate ones.

| API | Used for |
|---|---|
| **Search** | News, Reddit threads and X posts, on `/v1beta/search`. `one-shot` for the news feeding the briefing (about 3x the excerpt text of the older endpoint, at half the latency), `fast` for the social sweeps |
| **Task** | Analyst price targets and SEC filings, extracted against a JSON schema so they arrive as rows |
| **Monitor** | A standing hourly watch per ticker, delivering events by webhook between scheduled runs. A caught event is read back through Task against the same schemas, so it becomes a target or filing row rather than stopping at prose |
| **FindAll** | Discovering companies not on the watchlist: peers of a held ticker, or anything matching a plain-language theme. The watchlist goes in `exclude_list`, so the match budget is spent on names that could actually be new |
| **Extract** | Repairing citation previews whose indexed excerpt is nav bars and cookie banners |
| **Responses** | A second answer on the Ask page, read live from the open web and shown beside the agent's own, so a stored answer can be checked against a different corpus. OpenAI-compatible, so it takes `Authorization: Bearer` rather than `x-api-key` |

Every Task extraction keeps Parallel's **basis**: the source sentence behind each
field, the reasoning, and a confidence level. Hover the `?` beside a price target
or an insider badge to see where the figure came from.

## Stack

| Layer | Service |
|---|---|
| Agent platform | Google Cloud: Gemini Enterprise Agent Platform, Cloud IAM, Cloud Run |
| Web research | Parallel (Search, Task, Monitor, FindAll, Extract) |
| Storage | Firestore in production, SQLite locally |
| Metrics and alerting | Grafana |

## Running it

Needs Python 3.12+ and a Parallel API key. Google Cloud credentials are only
required for the deployed configuration: locally the app stores its history in
SQLite and calls Gemini through your own `gcloud` login.

```bash
pip install -r requirements.txt

# No key is ever committed or written to disk. The simplest way to run is to
# export it; the app reads the environment before it reaches anything else:
export PARALLEL_API_KEY=your-key

# The author's setup instead pulls it at runtime from AWS SSM Parameter Store,
# where each parameter holds a whole .env file. Point it at your own store with
# TICKERROOM_SSM_PROFILE, TICKERROOM_SSM_REGION and TICKERROOM_SSM_PREFIX.

gcloud auth application-default login   # for the Gemini calls

uvicorn src.web.app:app --reload --port 8077
```

Then open http://127.0.0.1:8077, add a ticker, and press **Run research**. The
first run takes a few minutes: it searches, extracts targets and filings
against a schema, and writes the briefing.

`scripts/serve.sh` brings up the app on 8077 and a provisioned Grafana on 3077
together, with the datasource and alert webhook pointed at the repo.

### Configuration

| Variable | Purpose |
|---|---|
| `PARALLEL_API_KEY` | Parallel access, if not using SSM |
| `TICKERROOM_BACKEND` | `firestore` in production; SQLite when unset |
| `GOOGLE_CLOUD_PROJECT` | Project for Firestore and Gemini |
| `TICKERROOM_PUBLIC_URL` | Where Parallel should deliver monitor webhooks. Without it, monitors are created without one and events are pulled by hand with the "Pull events now" button on a ticker page |
| `TICKERROOM_ALERT_TOKEN` | Shared secret for `/hooks/grafana`. Unset means the endpoint is open, which is fine locally |
| `TICKERROOM_METRICS_DB` | Where the Grafana projection is written |
| `TICKERROOM_ALLOW_ADD` | `1` opens the "Add to watchlist" form and its endpoint. Closed by default: the watchlist is single-user and every add starts a paid research pass, so on a public URL a stranger would be spending this account's credit |

### Endpoints worth knowing

| Path | What it is |
|---|---|
| `/` | The front door |
| `/lobby` | The watchlist |
| `/lobby/{ticker}` | One company: briefing, targets, filings, sentiment, price |
| `/ask` | A plain-language question, answered by an agent over the stored history and the live web |
| `/how-it-works` | The product and its architecture, in plain words and diagrams |
| `/discover` | Companies not on the watchlist yet |
| `/hooks/parallel` | Monitor events, pushed by Parallel |
| `/hooks/grafana` | Alerts, pushed by Grafana |
| `/health` | Liveness, plus the dependency versions the container resolved |

## Disclaimer

The Ticker Room is a research and awareness tool. It is **not** investment advice,
and it does not produce buy or sell recommendations. Nothing it outputs should be
treated as a financial recommendation. Always do your own research.

## License

AGPL-3.0. See [LICENSE](LICENSE).
