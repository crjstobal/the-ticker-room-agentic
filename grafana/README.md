# Grafana

Coverage and sentiment panels, provisioned as code.

## Run locally

```bash
brew install grafana
grafana cli --homepath /opt/homebrew/opt/grafana/share/grafana \
  --pluginsDir /opt/homebrew/var/lib/grafana/plugins \
  plugins install frser-sqlite-datasource
scripts/serve.sh
```

App on **:8077**, Grafana on **:3077** with the datasource and dashboard already
provisioned. The app embeds the coverage panel on each ticker page, scoped to
that company; the full dashboard is Grafana's own.

## How Grafana gets its data

It reads `data/metrics.db`, a small SQLite projection written by
`src/core/metrics_export.py` after every research run.

That indirection exists because the history lives in **SQLite locally and
Firestore in the cloud**, and one dashboard has to work against both. Exporting
a projection is simpler than teaching Grafana about two backends, and it keeps
the charting concern out of the storage layer.

The obvious alternative, a JSON API datasource pointed at `/api/metrics`, does
not work: `marcusolsson-json-datasource` installs, registers and reports a valid
signature, but ships **no backend binary**, so every query fails with
`plugin.unavailable`. That endpoint still exists and is useful on its own.

## Panels

| Panel | Reads | Shows |
|---|---|---|
| Articles per day by ticker | `coverage` | Baseline and spikes |
| Reddit sentiment | `sentiment_now` | -100 to +100 per ticker |
| Latest quotes | `quotes_now` | Spot and daily change |
| Sentiment detail | `sentiment_now` | Label, score, thread count |

## In the deployed service

Cloud Run has no Grafana attached, so the embedded panel is dropped rather than
left as an iframe pointing at a laptop: the ticker page keeps its own inline
sparkline, which carries the same series. Set `GRAFANA_URL` to a reachable
Grafana to re-enable the embed there.

## Alerting

`provisioning/alerting/spike.yml` fires when a ticker's daily article count
exceeds twice its trailing baseline and clears a floor of 5. It ships **paused**:
it needs a few days of history before the baseline means anything.
