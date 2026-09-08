"""Real price context for a ticker.

Every number the model is given about price comes from here. The model is
never allowed to supply price levels from its own training data: it once
reported a $50 level for a stock trading at $170.
"""
from __future__ import annotations

from typing import Any

import yfinance as yf


def fetch_quote(ticker: str) -> dict[str, Any] | None:
    """Spot price plus the technical context needed to ground the summary."""
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="3mo")
        if hist.empty:
            return None

        closes = hist["Close"]
        spot = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) > 1 else spot

        year = tk.history(period="1y")["Close"]
        high_52w = float(year.max()) if not year.empty else None
        low_52w = float(year.min()) if not year.empty else None

        return {
            "ticker": ticker,
            "spot": round(spot, 2),
            "change_pct": round((spot - prev) / prev * 100, 2) if prev else 0.0,
            "low_3mo": round(float(closes.min()), 2),
            "high_3mo": round(float(closes.max()), 2),
            "ma20": round(float(closes.tail(20).mean()), 2),
            "ma50": round(float(closes.tail(50).mean()), 2),
            "low_52w": round(low_52w, 2) if low_52w else None,
            "high_52w": round(high_52w, 2) if high_52w else None,
            "pct_off_52w_high": (
                round((spot - high_52w) / high_52w * 100, 2) if high_52w else None
            ),
        }
    except Exception as exc:  # yfinance scrapes a private API and breaks often
        print(f"[quotes] failed for {ticker}: {exc}")
        return None
