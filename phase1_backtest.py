"""
Phase 1: Baseline Reproduction
Runs TradingAgents on historical stock data and computes portfolio metrics:
cumulative return, annualized return, Sharpe ratio, max drawdown.
"""

import os
import re
import time
import json
import argparse
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# ── Backtest settings ─────────────────────────────────────────────────────────
TICKERS        = ["AMZN"]
INITIAL_CAPITAL = 1_000_000     # $1M per ticker

# ── Date ranges (swap comments to switch) ─────────────────────────────────────
# Phase 1 run: 1 month, 1 ticker (~21 trading days)
START_DATE = "2024-01-02"
END_DATE   = "2024-01-31"

# Extended run: ~6-month window matching paper's evaluation horizon
# START_DATE = "2024-01-02"
# END_DATE   = "2024-06-28"

LLM_CONFIG = DEFAULT_CONFIG.copy()
LLM_CONFIG["llm_provider"]           = "google"
LLM_CONFIG["deep_think_llm"]         = "gemini-2.5-flash-lite"   # ~4x cheaper than 2.5-flash, faster
LLM_CONFIG["quick_think_llm"]        = "gemini-2.5-flash-lite"
LLM_CONFIG["backend_url"]            = None   # clear OpenAI default URL — Google uses its own endpoint
LLM_CONFIG["max_debate_rounds"]      = 1
LLM_CONFIG["max_risk_discuss_rounds"] = 1
LLM_CONFIG["data_vendors"] = {
    **LLM_CONFIG["data_vendors"],
    # Use point-in-time SEC companyfacts for financial statements and ratios.
    "fundamental_data": "sec",
    # Use historical local/GDELT news for the January 2024 backtest instead of
    # current yfinance headlines, which are not point-in-time for old dates.
    "news_data": "local",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_trading_days(start: str, end: str) -> list[str]:
    """Return actual NYSE trading days in range using SPY as a reference."""
    end_fetch = (pd.Timestamp(end) + timedelta(days=1)).strftime("%Y-%m-%d")
    ref = yf.download("SPY", start=start, end=end_fetch, progress=False, auto_adjust=True)
    return list(ref.index.strftime("%Y-%m-%d"))


def fetch_prices(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch adjusted close prices indexed by YYYY-MM-DD strings."""
    end_fetch = (pd.Timestamp(end) + timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, end=end_fetch, progress=False, auto_adjust=True)
    s = df["Close"].squeeze()
    s.index = s.index.strftime("%Y-%m-%d")
    return s


def signal_to_position(signal: str) -> float:
    """Map a 5-tier signal to a portfolio weight (-1 to +1)."""
    return {
        "BUY":         1.0,
        "OVERWEIGHT":  0.5,
        "HOLD":        0.0,
        "UNDERWEIGHT": -0.5,
        "SELL":        -1.0,
    }.get(signal.strip().upper(), 0.0)


def compute_metrics(returns: pd.Series) -> dict:
    """Cumulative return, annualized return, Sharpe ratio, max drawdown."""
    cum = (1 + returns).cumprod()
    total = cum.iloc[-1] - 1
    n = len(returns)
    ann_ret = (1 + total) ** (252 / n) - 1
    ann_vol = returns.std() * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0
    drawdown = (cum - cum.cummax()) / cum.cummax()
    return {
        "cumulative_return_pct":  round(total * 100, 2),
        "annualized_return_pct":  round(ann_ret * 100, 2),
        "sharpe_ratio":           round(sharpe, 3),
        "max_drawdown_pct":       round(drawdown.min() * 100, 2),
        "n_trading_days":         n,
    }


# ── Main backtest loop ────────────────────────────────────────────────────────
def run_backtest(tickers: list[str], start: str, end: str, results_dir: str = "phase1_results"):
    out = Path(results_dir)
    out.mkdir(exist_ok=True)

    print("Initializing TradingAgents graph...", flush=True)
    ta = TradingAgentsGraph(debug=False, config=LLM_CONFIG)
    print("Fetching trading calendar...", flush=True)
    trading_days = get_trading_days(start, end)
    print(f"Backtesting {len(trading_days)} trading days: {trading_days[0]} → {trading_days[-1]}\n")

    all_metrics = {}

    for ticker in tickers:
        print(f"{'='*55}\n{ticker}\n{'='*55}")
        prices = fetch_prices(ticker, start, end)

        decisions: dict[str, str]   = {}
        positions: dict[str, float] = {}

        for trade_date in trading_days:
            if trade_date not in prices.index:
                print(f"  [skip] {trade_date} — no price")
                continue

            print(f"  {trade_date} ...", end=" ", flush=True)
            signal = None
            for attempt in range(5):
                try:
                    _, signal = ta.propagate(ticker, trade_date)
                    break
                except Exception as e:
                    msg = str(e)
                    m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg)
                    wait = float(m.group(1)) + 5 if m else 60 * (2 ** attempt)
                    print(f"rate-limited, sleeping {wait:.0f}s ...", end=" ", flush=True)
                    time.sleep(wait)

            if signal:
                pos = signal_to_position(signal)
                decisions[trade_date] = signal
                positions[trade_date] = pos
                print(f"{signal}  (pos={pos:+.1f})")
            else:
                print("FAILED after retries, defaulting to HOLD")
                decisions[trade_date] = "HOLD"
                positions[trade_date] = 0.0

        # ── Portfolio simulation ──────────────────────────────────────────────
        # Signal on day t is generated after close → applied to next-day return
        pos_series    = pd.Series(positions)
        price_returns = prices.pct_change().fillna(0.0)
        price_returns = price_returns.reindex(pos_series.index)
        strat_returns = pos_series.shift(1).fillna(0.0) * price_returns

        first_day = list(positions.keys())[0]
        strat_returns = strat_returns.loc[first_day:]

        metrics = compute_metrics(strat_returns)
        all_metrics[ticker] = metrics

        ticker_out = {
            "ticker": ticker, "start": start, "end": end,
            "decisions": decisions, "metrics": metrics,
        }
        with open(out / f"{ticker}_results.json", "w") as f:
            json.dump(ticker_out, f, indent=2)

        print(f"\n  Results for {ticker}:")
        for k, v in metrics.items():
            print(f"    {k}: {v}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*55}\nPHASE 1 SUMMARY\n{'='*55}")
    print(pd.DataFrame(all_metrics).T.to_string())

    with open(out / "summary.json", "w") as f:
        json.dump(all_metrics, f, indent=2)

    print(f"\nAll results saved to ./{results_dir}/")
    return all_metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers",     nargs="+", default=TICKERS)
    parser.add_argument("--start",       default=START_DATE)
    parser.add_argument("--end",         default=END_DATE)
    parser.add_argument("--results-dir", default="phase1_results")
    args = parser.parse_args()

    run_backtest(args.tickers, args.start, args.end, args.results_dir)
