"""
Create report-ready Phase 1 result plots.

Outputs:
  - phase1_results/metrics_comparison.csv
  - phase1_results/metrics_comparison.png
  - phase1_results/equity_curves.png
  - phase1_results/tradingagents_decisions.png
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

from phase1_benchmarks import (
    buy_and_hold,
    kdj_rsi_strategy,
    macd_strategy,
    sma_strategy,
    zmr_strategy,
)


RESULTS_DIR = Path("phase1_results")
TA_RESULTS_PATH = RESULTS_DIR / "AMZN_results.json"
BENCHMARKS_PATH = RESULTS_DIR / "benchmarks.json"


def fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    end_fetch = (pd.Timestamp(end) + timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, end=end_fetch, progress=False, auto_adjust=True)
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    df.index = df.index.strftime("%Y-%m-%d")
    return df


def signal_to_position(signal: str) -> float:
    return {
        "BUY": 1.0,
        "OVERWEIGHT": 0.5,
        "HOLD": 0.0,
        "UNDERWEIGHT": -0.5,
        "SELL": -1.0,
    }.get(signal.strip().upper(), 0.0)


def equity_curve(positions: pd.Series, prices: pd.Series) -> pd.Series:
    returns = prices.pct_change().fillna(0.0)
    strategy_returns = positions.shift(1).fillna(0.0) * returns
    return (1 + strategy_returns).cumprod()


def load_results() -> tuple[dict, dict]:
    ta_results = json.loads(TA_RESULTS_PATH.read_text())
    benchmarks = json.loads(BENCHMARKS_PATH.read_text())
    return ta_results, benchmarks


def make_metrics_table(ta_results: dict, benchmarks: dict) -> pd.DataFrame:
    ticker = ta_results["ticker"]
    rows = {"TradingAgents": ta_results["metrics"]}
    rows.update(benchmarks[ticker])
    table = pd.DataFrame(rows).T
    table = table[
        [
            "cumulative_return_pct",
            "annualized_return_pct",
            "sharpe_ratio",
            "max_drawdown_pct",
            "n_trading_days",
        ]
    ]
    table.to_csv(RESULTS_DIR / "metrics_comparison.csv")
    return table


def plot_metrics(table: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fig.suptitle("AMZN January 2024: TradingAgents vs Benchmarks", fontsize=14, fontweight="bold")

    specs = [
        ("cumulative_return_pct", "Cumulative Return (%)"),
        ("sharpe_ratio", "Sharpe Ratio"),
        ("max_drawdown_pct", "Max Drawdown (%)"),
    ]

    colors = ["#1f77b4" if idx == "TradingAgents" else "#8a8f98" for idx in table.index]
    for ax, (column, title) in zip(axes, specs):
        values = table[column]
        bars = ax.bar(table.index, values, color=colors)
        ax.set_title(title)
        ax.axhline(0, color="#222222", linewidth=0.8)
        ax.tick_params(axis="x", rotation=35, labelsize=8)
        ax.grid(axis="y", alpha=0.25)
        for bar, value in zip(bars, values):
            va = "bottom" if value >= 0 else "top"
            y_offset = 0.03 * (values.max() - values.min() or 1)
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + (y_offset if value >= 0 else -y_offset),
                f"{value:.2f}",
                ha="center",
                va=va,
                fontsize=8,
            )

    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "metrics_comparison.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_equity_curves(ta_results: dict) -> None:
    ticker = ta_results["ticker"]
    ohlcv = fetch_ohlcv(ticker, ta_results["start"], ta_results["end"])
    prices = ohlcv["close"]

    decisions = pd.Series(ta_results["decisions"], dtype="string")
    decisions = decisions.reindex(prices.index).ffill().fillna("HOLD")
    ta_positions = decisions.map(signal_to_position).astype(float)

    curves = {
        "TradingAgents": equity_curve(ta_positions, prices),
        "Buy & Hold": equity_curve(buy_and_hold(prices), prices),
        "MACD": equity_curve(macd_strategy(prices), prices),
        "KDJ + RSI": equity_curve(kdj_rsi_strategy(ohlcv), prices),
        "ZMR": equity_curve(zmr_strategy(prices), prices),
        "SMA (10/30)": equity_curve(sma_strategy(prices), prices),
    }

    curve_df = pd.DataFrame(curves)
    curve_df.to_csv(RESULTS_DIR / "equity_curves.csv")

    fig, ax = plt.subplots(figsize=(11, 5))
    for name, series in curve_df.items():
        linewidth = 2.8 if name == "TradingAgents" else 1.5
        alpha = 1.0 if name == "TradingAgents" else 0.75
        ax.plot(series.index, series.values, label=name, linewidth=linewidth, alpha=alpha)

    ax.set_title("AMZN January 2024 Equity Curves", fontsize=14, fontweight="bold")
    ax.set_ylabel("Growth of $1")
    ax.grid(alpha=0.25)
    ax.legend(ncol=3, fontsize=8)
    ax.tick_params(axis="x", rotation=35, labelsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "equity_curves.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    plot_decisions(decisions, prices)


def plot_decisions(decisions: pd.Series, prices: pd.Series) -> None:
    color_map = {"BUY": "#2ca02c", "HOLD": "#7f7f7f", "SELL": "#d62728"}
    marker_map = {"BUY": "^", "HOLD": "o", "SELL": "v"}

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(prices.index, prices.values, color="#1f2937", linewidth=2, label="AMZN adjusted close")

    for signal in ["BUY", "HOLD", "SELL"]:
        mask = decisions.str.upper() == signal
        ax.scatter(
            decisions.index[mask],
            prices.reindex(decisions.index)[mask],
            color=color_map[signal],
            marker=marker_map[signal],
            s=70,
            label=signal,
            zorder=3,
        )

    ax.set_title("TradingAgents Daily Decisions", fontsize=14, fontweight="bold")
    ax.set_ylabel("Adjusted Close")
    ax.grid(alpha=0.25)
    ax.legend(ncol=4, fontsize=8)
    ax.tick_params(axis="x", rotation=35, labelsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "tradingagents_decisions.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    ta_results, benchmarks = load_results()
    table = make_metrics_table(ta_results, benchmarks)
    plot_metrics(table)
    plot_equity_curves(ta_results)

    print("Saved:")
    for name in [
        "metrics_comparison.csv",
        "metrics_comparison.png",
        "equity_curves.csv",
        "equity_curves.png",
        "tradingagents_decisions.png",
    ]:
        print(f"  {RESULTS_DIR / name}")


if __name__ == "__main__":
    main()
