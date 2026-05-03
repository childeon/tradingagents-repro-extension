"""
Phase 1: Benchmark Strategies
Five rule-based baselines to compare against TradingAgents:
  1. Buy & Hold
  2. MACD (EMA12/26/9)
  3. KDJ + RSI
  4. ZMR (Zero Mean Reversion via rolling z-score)
  5. SMA Crossover (10/30-day)

Signal convention: 1 = fully long, -1 = short, 0 = flat
Execution model: signal generated at close on day t, applied to day t+1 return.
This matches phase1_backtest.py.
"""

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

TICKER     = "AMZN"
START_DATE = "2024-01-02"
END_DATE   = "2024-01-31"
RESULTS_DIR = Path("phase1_results")


# ── Data fetching ─────────────────────────────────────────────────────────────
def fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    end_fetch = (pd.Timestamp(end) + timedelta(days=1)).strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, end=end_fetch,
                     progress=False, auto_adjust=True)
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                  for c in df.columns]
    df.index = df.index.strftime("%Y-%m-%d")
    return df


# ── Shared backtesting engine ─────────────────────────────────────────────────
def backtest(positions: pd.Series, prices: pd.Series) -> dict:
    """
    Signal on day t is applied to day t+1 return (close-to-close).
    Matches the execution model in phase1_backtest.py.
    """
    ret = prices.pct_change().fillna(0.0)
    strat_ret = positions.shift(1).fillna(0.0) * ret

    cum = (1 + strat_ret).cumprod()
    total = cum.iloc[-1] - 1
    n = len(strat_ret)
    ann_ret = (1 + total) ** (252 / n) - 1
    ann_vol = strat_ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    drawdown = (cum - cum.cummax()) / cum.cummax()

    return {
        "cumulative_return_pct":  round(total * 100, 2),
        "annualized_return_pct":  round(ann_ret * 100, 2),
        "sharpe_ratio":           round(sharpe, 3),
        "max_drawdown_pct":       round(drawdown.min() * 100, 2),
        "n_trading_days":         n,
    }


# ── Strategy 1: Buy & Hold ────────────────────────────────────────────────────
def buy_and_hold(prices: pd.Series) -> pd.Series:
    return pd.Series(1.0, index=prices.index)


# ── Strategy 2: MACD (EMA12 − EMA26, signal EMA9) ────────────────────────────
def macd_strategy(prices: pd.Series) -> pd.Series:
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()

    pos, positions = 0.0, pd.Series(0.0, index=prices.index)
    for i in range(1, len(macd)):
        was_above = macd.iloc[i - 1] > sig.iloc[i - 1]
        is_above  = macd.iloc[i]     > sig.iloc[i]
        if not was_above and is_above:      # bullish crossover → long
            pos = 1.0
        elif was_above and not is_above:    # bearish crossover → short
            pos = -1.0
        positions.iloc[i] = pos
    return positions


# ── Strategy 3: KDJ + RSI ─────────────────────────────────────────────────────
def kdj_rsi_strategy(ohlcv: pd.DataFrame,
                     k_period: int = 9, rsi_period: int = 14) -> pd.Series:
    high  = ohlcv["high"]
    low   = ohlcv["low"]
    close = ohlcv["close"]

    # KDJ
    ll = low.rolling(k_period).min()
    hh = high.rolling(k_period).max()
    k  = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    k  = k.fillna(50.0)
    d  = k.rolling(3).mean()
    j  = 3 * k - 2 * d

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(rsi_period).mean()
    loss  = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rsi   = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rsi   = rsi.fillna(50.0)

    pos, positions = 0.0, pd.Series(0.0, index=close.index)
    for i in range(1, len(j)):
        j_up   = j.iloc[i - 1] < k.iloc[i - 1] and j.iloc[i] >= k.iloc[i]
        j_down = j.iloc[i - 1] > k.iloc[i - 1] and j.iloc[i] <= k.iloc[i]
        if j_up   and rsi.iloc[i] < 70:    # J crosses up + not overbought → long
            pos = 1.0
        elif j_down and rsi.iloc[i] > 30:  # J crosses down + not oversold → short
            pos = -1.0
        positions.iloc[i] = pos
    return positions


# ── Strategy 4: ZMR (Zero Mean Reversion) ─────────────────────────────────────
def zmr_strategy(prices: pd.Series,
                 window: int = 20, entry_z: float = -1.0) -> pd.Series:
    mu  = prices.rolling(window).mean()
    sd  = prices.rolling(window).std().replace(0, np.nan)
    z   = ((prices - mu) / sd).fillna(0.0)

    pos, positions = 0.0, pd.Series(0.0, index=prices.index)
    for i in range(1, len(z)):
        if z.iloc[i] < entry_z:                    # price far below mean → buy
            pos = 1.0
        elif pos == 1.0 and z.iloc[i] >= 0.0:      # reverted to mean → exit
            pos = 0.0
        positions.iloc[i] = pos
    return positions


# ── Strategy 5: SMA Crossover (10 / 30-day) ───────────────────────────────────
def sma_strategy(prices: pd.Series,
                 short: int = 10, long: int = 30) -> pd.Series:
    sma_s = prices.rolling(short).mean()
    sma_l = prices.rolling(long).mean()

    pos, positions = 0.0, pd.Series(0.0, index=prices.index)
    for i in range(1, len(prices)):
        was_above = sma_s.iloc[i - 1] > sma_l.iloc[i - 1]
        is_above  = sma_s.iloc[i]     > sma_l.iloc[i]
        if not was_above and is_above:     # golden cross → long
            pos = 1.0
        elif was_above and not is_above:   # death cross → short
            pos = -1.0
        positions.iloc[i] = pos
    return positions


# ── Run all benchmarks ─────────────────────────────────────────────────────────
def run_benchmarks(ticker: str = TICKER,
                   start: str  = START_DATE,
                   end: str    = END_DATE,
                   results_dir: Path = RESULTS_DIR) -> dict:

    results_dir.mkdir(exist_ok=True)
    ohlcv  = fetch_ohlcv(ticker, start, end)
    prices = ohlcv["close"]

    strategies = {
        "Buy & Hold":    buy_and_hold(prices),
        "MACD":          macd_strategy(prices),
        "KDJ + RSI":     kdj_rsi_strategy(ohlcv),
        "ZMR":           zmr_strategy(prices),
        "SMA (10/30)":   sma_strategy(prices),
    }

    all_metrics = {}
    print(f"\nBenchmark results for {ticker}  ({start} → {end})\n{'='*55}")
    for name, pos in strategies.items():
        m = backtest(pos, prices)
        all_metrics[name] = m
        print(f"\n{name}")
        for k, v in m.items():
            unit = "%" if "return" in k or "drawdown" in k else ""
            print(f"  {k}: {v}{unit}")

    out_path = results_dir / "benchmarks.json"
    with open(out_path, "w") as f:
        json.dump({ticker: all_metrics}, f, indent=2)
    print(f"\nSaved to {out_path}")
    return all_metrics


if __name__ == "__main__":
    run_benchmarks()
