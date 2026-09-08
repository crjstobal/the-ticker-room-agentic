"""Collapse filing rows that are the same insider under a different spelling.

`filings.name_key` fixes this going forward: new rows are deduplicated on a
sorted, nickname-folded name, so "Huffman Steve Ladd" and "Steve Ladd Huffman"
never become two rows again. Rows stored before that existed are still there,
and on the deployed service they are what a reader sees: RDDT listed one CEO
three times, which reads as three separate trades.

Re-running the extraction would cost a Task run per ticker and would not be
more correct, since the duplicates are already stored with everything they
need. This merges them in place instead, using exactly the same key the live
code uses so the two cannot disagree.

Usage:
    python scripts/dedupe_filings.py            # report only, changes nothing
    python scripts/dedupe_filings.py --apply    # actually merge

The default is a dry run: this deletes rows from a production database, and
the deletion is not something a reader can undo.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import repo
from src.core.filings import _merge, display_name, name_key


def group(rows: list[dict]) -> dict[tuple, list[dict]]:
    """Rows that are the same filing, keyed the way the live code keys them."""
    out: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r.get("form_type", ""), r.get("filed_date", ""),
               name_key(r.get("insider_name", "")))
        out.setdefault(key, []).append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the merge; without it, only report")
    args = ap.parse_args()

    backend = repo.backend_name()
    print(f"backend: {backend}")

    total_dupes = 0
    for row in repo.get_watchlist("javi"):
        ticker = row["ticker"]
        rows = repo.latest_filings(ticker, limit=500)
        groups = group(rows)
        dupes = {k: v for k, v in groups.items() if len(v) > 1}
        if not dupes:
            print(f"{ticker}: {len(rows)} filings, nothing to merge")
            continue

        print(f"\n{ticker}: {len(rows)} filings, "
              f"{sum(len(v) - 1 for v in dupes.values())} duplicate rows")
        for key, members in dupes.items():
            names = sorted({m.get("insider_name", "") for m in members})
            print(f"  {key[0]:6} {key[1]} -> {len(members)} rows: {names}")
            total_dupes += len(members) - 1

            if not args.apply:
                continue

            # Keep the best-rendered name, fold the rest into it. The same
            # `_merge` the live path uses, so a field present on only one copy
            # survives rather than being dropped with its row.
            keeper = dict(members[0])
            for other in members[1:]:
                _merge(keeper, other)
            keeper["insider_name"] = display_name(keeper.get("insider_name", ""))
            repo.replace_filings(ticker, members, keeper)

    if not args.apply:
        print(f"\nDry run: {total_dupes} rows would be merged. "
              f"Re-run with --apply to write.")
    else:
        print(f"\nMerged {total_dupes} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
