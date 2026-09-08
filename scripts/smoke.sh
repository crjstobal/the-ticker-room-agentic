#!/usr/bin/env bash
# Fetch every page a judge could open and fail on the first one that is not 200.
#
# The bug this exists to catch: /lobby answered 500 for weeks because a Firestore
# composite index was declared but never deployed. Nothing failed loudly, the
# home page was fine, and the break only showed on a route nobody had opened
# since the change. Nine requests find that in about a second.
#
#   ./scripts/smoke.sh                       # local, port 8077
#   ./scripts/smoke.sh https://your-url      # the deployed service
set -uo pipefail
BASE="${1:-http://127.0.0.1:8077}"

# /healthz is deliberately absent: Cloud Run's front end answers that path with
# its own 404 before it reaches the container, so testing it would fail against
# a service that is perfectly healthy. /health is the real check.
ROUTES=(/ /lobby /health /ask /discover /settings /how-it-works
        /sitemap /sitemap.xml /robots.txt /privacy /terms /legal-notice /cookies)

# Ticker pages are the ones that exercise the ordered Firestore queries, so
# they are pulled from the live watchlist rather than hardcoded.
TICKERS=$(curl -fsS --max-time 20 "$BASE/api/metrics" 2>/dev/null \
  | /usr/bin/python3 -c 'import sys,json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
seen = []
for q in d.get("quotes", []):
    t = q.get("ticker")
    if t and t not in seen:
        seen.append(t)
print(" ".join(seen))' 2>/dev/null || true)

for t in $TICKERS; do ROUTES+=("/lobby/$t"); done

echo "Smoke testing $BASE"
fail=0
for route in "${ROUTES[@]}"; do
  read -r code time < <(curl -s -o /dev/null -w '%{http_code} %{time_total}' \
    --max-time 30 "$BASE$route" 2>/dev/null || echo "000 0")
  if [ "$code" = "200" ]; then
    printf '  ok   %-18s %ss\n' "$route" "$time"
  else
    printf '  FAIL %-18s HTTP %s\n' "$route" "$code"
    fail=$((fail + 1))
  fi
done

if [ "$fail" -gt 0 ]; then
  echo "$fail route(s) failed"
  exit 1
fi

# A shrinking list is a failure, not a pass. /watch and its page were dropped
# from the source and this script cheerfully reported "All 8 routes OK": the
# route was gone, so it was never requested, so nothing could fail. Pin the
# count, and make a deliberate change to the route list edit this number.
EXPECTED=16
if [ "${#ROUTES[@]}" -lt "$EXPECTED" ]; then
  echo "Only ${#ROUTES[@]} routes tested, expected $EXPECTED."
  echo "A route disappeared from the app (or the watchlist is empty)."
  exit 1
fi
echo "All ${#ROUTES[@]} routes OK"
