"""End-to-end smoke test: seed a watchlist, research it, print the briefings."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import storage
from src.core.runner import run_for_user

USER = "javi"
SEED = [("RDDT", "Reddit"), ("ONDS", "Ondas Holdings")]

conn = storage.connect()
for ticker, name in SEED:
    storage.add_to_watchlist(conn, USER, ticker, name)
conn.close()

print(f"Running The Ticker Room for '{USER}'...\n")
for r in run_for_user(USER):
    print("=" * 78)
    q = r.quote
    price = f"${q['spot']} ({q['change_pct']:+.2f}%)" if q else "no price data"
    print(f"{r.ticker} — {r.company_name} | {price}")
    print(f"articles: {len(r.articles)} kept ({r.new_articles} new)")
    if r.errors:
        print(f"errors: {r.errors}")
    print("-" * 78)
    print(r.briefing or "(no briefing)")
    print()
