# Google Cloud setup

The Ticker Room runs its model calls on **Gemini Enterprise Agent Platform**
(the platform formerly named Vertex AI; renamed at Cloud Next 2026).

## Project

| | |
|---|---|
| Project ID | `ticker-room` |
| Project number | `372773300560` |
| Region | `global` for the model, `europe-west1` for services |
| Budget | 50 EUR, alerts at 50% / 90% / 100% |

## Enabled APIs

`aiplatform` · `run` · `cloudscheduler` · `secretmanager` · `iam` ·
`discoveryengine`

## Service account and IAM

`ticker-room-agent@ticker-room.iam.gserviceaccount.com`, granted only:

| Role | Why |
|---|---|
| `roles/aiplatform.user` | Call Gemini |
| `roles/secretmanager.secretAccessor` | Read secrets, no write |
| `roles/logging.logWriter` | Write logs, no read |

No `roles/editor` and no `roles/owner`: the agent can do its job and nothing else.

## Local development

```bash
gcloud auth application-default login
```

The adapter falls back to the gcloud user credential when ADC is absent, so a
developer who has run `gcloud auth login` can work without extra setup.

## Model location

`gemini-3.6-flash` is served from the **`global`** location. Regional endpoints
(`us-central1`, `europe-west1`) return 404 for this model, which is worth knowing
before debugging a "model not found" that is really a location mismatch.

## Note on the currency

The billing account is denominated in **EUR**. `gcloud billing budgets create`
rejects a budget in a different currency with a bare `INVALID_ARGUMENT`, naming
neither the currency nor the field.

## Cloud Run

```bash
gcloud run deploy ticker-room --source . --project=ticker-room \
  --region=europe-west1 --allow-unauthenticated \
  --service-account=ticker-room-agent@ticker-room.iam.gserviceaccount.com \
  --set-env-vars="TICKERROOM_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=ticker-room,TICKERROOM_METRICS_DB=/tmp/metrics.db,TICKERROOM_PUBLIC_URL=https://ticker-room-372773300560.europe-west1.run.app" \
  --set-secrets="PARALLEL_ENV=parallel-env:latest" \
  --memory=1Gi --cpu=1 --timeout=1800 --max-instances=3 --min-instances=1
```

Live at **https://ticker-room-372773300560.europe-west1.run.app**

`--set-env-vars` **replaces** the whole set rather than adding to it, so every
variable the service needs has to be listed on every deploy. Omitting one
silently drops it: leaving out `TICKERROOM_BACKEND` would send the deployed
service back to SQLite on an ephemeral disk, losing the history on each restart.

`--min-instances=1` has the same trap and has to be repeated for the same
reason: a deploy that omits it sets the minimum back to zero, which brings back
the twelve-second cold start on a service whose first visitor is a judge making
exactly one cold request. It is invisible in the deploy output, so check with
`gcloud run services describe ticker-room --region=europe-west1` and look for
`autoscaling.knative.dev/minScale=1`.

`--timeout=1800` because `/tasks/run` researches the whole watchlist inside one
request. Two tickers concurrently took 486s locally, and the default 600s left
no room: a slower run would be cut off mid-write, leaving the history half
populated with no error to show for it. The real fix is to run the research as a
background task and return immediately, which is on the backlog; the raised
timeout is what makes the current shape safe.

`TICKERROOM_PUBLIC_URL` is what lets a monitor register a webhook. Parallel
rejects a webhook URL it cannot reach, so monitors are created without one when
the variable is absent, and events then only arrive when somebody presses
"Pull events now" on /watch. With it set, the interrupt path works unattended,
which is the whole point of Monitor.

### Two things the container needed

**The database path.** Cloud Run's filesystem is ephemeral and read-only outside
`/tmp`, so `TICKERROOM_DB` moves the SQLite file there. A restart loses history;
acceptable for the demo, and the reason persistent storage is on the backlog.

**Secrets without AWS credentials.** Locally secrets can come from AWS SSM via a
named profile, which does not exist in the container. `_load()` now prefers an
environment variable (`PARALLEL_ENV`) and falls back to SSM, so the same code
works in both places. The Parallel key is mirrored into Google Secret
Manager and injected by Cloud Run.

### Build permissions

A first deploy fails with `PERMISSION_DENIED` because the default compute
service account cannot read the uploaded source. It needs
`cloudbuild.builds.builder`, `storage.objectViewer`, `artifactregistry.writer`
and `logging.logWriter`, and the deploying user needs `iam.serviceAccountUser`
on the runtime service account.

## Firestore

Cloud Run restarts lose anything on disk, so the deployed service stores its
history in Firestore (`eur3`). Local development keeps SQLite: no network, no
credentials. `src/core/repo.py` picks the backend, and everything above it is
written against one interface.

Two things Firestore required:

**No nested arrays.** `subreddits` arrives as `[("ONDS", 5)]` and is rejected
outright. Stored as `[{"name": ..., "count": ...}]` and converted back on read.

**Composite indexes.** Every `where(...) + order_by(...)` needs one, or the query
fails with `FAILED_PRECONDITION`. They are declared in `firestore.indexes.json`
and take a few minutes to build.

## Cloud Scheduler

```
job:      ticker-room-research      schedule: 45 17 * * 1-5  (America/New_York)
job:      ticker-room-research-am   schedule: 45 9  * * 1-5  (America/New_York)
target:   POST /tasks/run
auth:     OIDC as ticker-room-scheduler@, which holds only run.invoker
```

`/tasks/run` is separate from `/run` so the two are distinguishable in the
history: a run stamped `scheduled` is the product working on its own.

**Why those two times, and why New York.** The filings come from EDGAR, which
accepts submissions from 06:00 to 22:00 ET, and anything filed after 17:30 ET
carries the *next* business day as its official date. So issuers cluster in the
window between the 16:00 close and that 17:30 cutoff: bad news lands with the
market shut but still counts as today. The 17:45 job runs just after that
window shuts and takes the whole peak in one pass. The 09:45 job runs a quarter
hour into the next session and picks up what was filed overnight plus the
analyst reaction to it. Weekdays only, because EDGAR does not accept weekend
filings, and a run then would spend money to rediscover Friday.

Both are in New York time on purpose: the filing calendar is American, so a
schedule pinned to Madrid would drift an hour away from the peak twice a year
when the two zones change clocks on different dates.

## Agent Builder — the analyst agent

`/ask` is a real agent loop on Gemini Enterprise Agent Platform: five tools are
declared, and the model picks which to call and in what order for the question
asked. The page shows the trace, so the reasoning is auditable.

| Tool | Reads |
|---|---|
| `get_price` | Stored quote, falling back to a live fetch |
| `get_coverage_history` | Articles per day over 60 days, with average and peak |
| `get_stored_articles` | Headlines already collected |
| `get_sentiment` | Latest Reddit reading with its provenance |
| `search_web` | Parallel, only when history does not answer |

Asked "which ticker is getting the most attention", it called
`get_coverage_history` once per watchlist ticker and compared the results — a
decision, not a fixed script.

**The research pipeline stays deterministic on purpose.** A scheduled briefing
should always do the same four things; an agent that "decides" to skip Reddit
would leave holes in the sentiment series. Choosing helps for open questions,
not for a nightly report.

### Local development needs ADC

The Vertex SDK requires Application Default Credentials and does not fall back
to the gcloud user credential:

```bash
gcloud auth application-default login
```

On Cloud Run the attached service account provides them, so only local runs
need this.
