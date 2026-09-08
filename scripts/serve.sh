#!/usr/bin/env bash
# Bring up The Ticker Room locally: web on 8077, Grafana on 3077.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON_BIN:-/Users/javi/PythonEnv/bin/python}"
GRAFANA_HOME="${GRAFANA_HOME:-/opt/homebrew/opt/grafana/share/grafana}"
GRAFANA_BIN="${GRAFANA_BIN:-/opt/homebrew/opt/grafana/bin/grafana}"
CFG_DIR="${TMPDIR:-/tmp}/grafana-tickerroom"

mkdir -p "$CFG_DIR/data" "$CFG_DIR/logs"
cat > "$CFG_DIR/grafana.ini" <<INI
[paths]
data = $CFG_DIR/data
logs = $CFG_DIR/logs
plugins = /opt/homebrew/var/lib/grafana/plugins
provisioning = $ROOT/grafana/provisioning
[server]
http_port = 3077
[auth.anonymous]
enabled = true
org_role = Admin
[security]
# Panels are embedded in the app at :8077, so framing must be allowed.
allow_embedding = true
cookie_samesite = none
[dashboards]
default_home_dashboard_path = $ROOT/grafana/dashboards/coverage.json
[auth]
disable_login_form = true
[analytics]
reporting_enabled = false
check_for_updates = false
INI

# Grafana expands ${VAR} in its provisioning files from its own environment,
# so the datasource path and the alert webhook are set here rather than being
# written into the YAML. That is what keeps those files working on a clone.
# Every variable the provisioning files reference must be exported here, with
# its default applied here too. Grafana substitutes a bare ${VAR} and has no
# default syntax of its own, and an unset one becomes the empty string: an empty
# contact-point `url` aborts provisioning, which takes down the datasource and
# the dashboards with it and stops Grafana starting at all.
export TICKERROOM_METRICS_DB="${TICKERROOM_METRICS_DB:-$ROOT/data/metrics.db}"
export TICKERROOM_DASHBOARDS="${TICKERROOM_DASHBOARDS:-$ROOT/grafana/dashboards}"
export TICKERROOM_ALERT_WEBHOOK="${TICKERROOM_ALERT_WEBHOOK:-http://127.0.0.1:8077/hooks/grafana}"
# Empty is the correct local default (the endpoint stays open when the app has
# no token set), but it still has to be exported for the expansion to resolve.
export TICKERROOM_ALERT_TOKEN="${TICKERROOM_ALERT_TOKEN:-}"

# Read the same Firestore the deployed service writes, so the local app shows
# live data instead of a SQLite snapshot that stopped moving whenever the last
# manual run happened. The scheduler only ever writes to Firestore, so a local
# SQLite copy goes stale silently and looks like a bug in the product.
# Set TICKERROOM_BACKEND=sqlite to work offline against data/tickerroom.db.
# Machine-local settings, if present: the name of the AWS profile and prefix
# holding this deployment's keys. Kept out of the repo (and out of
# src/core/secrets.py) because naming your own secret store in committed code
# publishes a map of where your credentials live. Nothing here is required:
# exporting PARALLEL_API_KEY skips SSM altogether.
[ -f "$ROOT/scripts/local.env" ] && . "$ROOT/scripts/local.env"

export TICKERROOM_BACKEND="${TICKERROOM_BACKEND:-firestore}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-ticker-room}"

pkill -f "uvicorn src.web.app" 2>/dev/null || true
pkill -f "grafana-tickerroom" 2>/dev/null || true

cd "$ROOT"
"$PY" -m uvicorn src.web.app:app --host 127.0.0.1 --port 8077 > "$CFG_DIR/web.log" 2>&1 &
"$GRAFANA_BIN" server --config "$CFG_DIR/grafana.ini" --homepath "$GRAFANA_HOME" > "$CFG_DIR/grafana.log" 2>&1 &

echo "The Ticker Room  ->  http://127.0.0.1:8077"
echo "Grafana          ->  http://127.0.0.1:3077/d/tickerroom-coverage"
wait
