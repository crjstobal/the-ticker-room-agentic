#!/usr/bin/env bash
# Sync Firestore composite indexes from firestore.indexes.json.
#
# The JSON on its own does nothing: it is a declaration, not a deployment.
# Two indexes (targets, filings) sat in that file for weeks while Firestore
# had never been told about them, and every page that ordered filings by date
# answered 500 with FAILED_PRECONDITION. This closes that gap.
#
# Idempotent: an index that already exists comes back as ALREADY_EXISTS and is
# reported as present rather than treated as a failure.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${GOOGLE_CLOUD_PROJECT:-ticker-room}"
SPEC="$ROOT/firestore.indexes.json"

echo "Syncing indexes from $SPEC into $PROJECT"

# gcloud takes one --field-config per field, so the JSON is flattened into the
# argument list here rather than being fed in wholesale.
/usr/bin/python3 - "$SPEC" "$PROJECT" <<'PY'
import json, subprocess, sys

spec, project = sys.argv[1], sys.argv[2]
indexes = json.load(open(spec)).get("indexes", [])
created = existing = failed = 0

for idx in indexes:
    group = idx["collectionGroup"]
    args = ["gcloud", "firestore", "indexes", "composite", "create",
            f"--project={project}", f"--collection-group={group}",
            f"--query-scope={idx.get('queryScope', 'COLLECTION')}"]
    for field in idx["fields"]:
        args.append(
            f"--field-config=field-path={field['fieldPath']},"
            f"order={field['order'].lower()}"
        )
    names = ",".join(f["fieldPath"] for f in idx["fields"])
    res = subprocess.run(args, capture_output=True, text=True)
    out = res.stdout + res.stderr
    if res.returncode == 0:
        print(f"  created  {group}: {names}")
        created += 1
    elif "ALREADY_EXISTS" in out or "already exists" in out.lower():
        print(f"  present  {group}: {names}")
        existing += 1
    else:
        print(f"  FAILED   {group}: {names}")
        print(f"           {out.strip().splitlines()[-1] if out.strip() else '?'}")
        failed += 1

print(f"\n{created} created, {existing} already present, {failed} failed")
if created:
    print("New indexes take a few minutes to build. Queries fail until they do.")
sys.exit(1 if failed else 0)
PY
