"""
Phase 1 Extension: Ablation backtests.

Runs the two extension variants:
  1. no_research_debate: analysts -> research manager -> trader -> risk layer -> portfolio manager
  2. no_risk_layer: analysts -> research debate -> trader -> portfolio manager

The full-lite replication remains in phase1_backtest.py.
"""

from copy import deepcopy

import phase1_backtest as base
ABLATION_MODES = ["no_research_debate", "no_risk_layer"]


def run_ablation_backtest(
    mode: str,
    tickers: list[str] = base.TICKERS,
    start: str = base.START_DATE,
    end: str = base.END_DATE,
    results_dir: str | None = None,
):
    if mode not in ABLATION_MODES:
        raise ValueError(f"Unknown ablation mode {mode!r}. Expected one of {ABLATION_MODES}.")

    output_dir = results_dir or f"phase1_results_{mode}"
    config = deepcopy(base.LLM_CONFIG)
    config["ablation_mode"] = mode
    config["results_dir"] = output_dir

    original_config = base.LLM_CONFIG
    try:
        base.LLM_CONFIG = config
        return base.run_backtest(
            tickers=tickers,
            start=start,
            end=end,
            results_dir=output_dir,
        )
    finally:
        base.LLM_CONFIG = original_config


def run_all_ablations(
    tickers: list[str] = base.TICKERS,
    start: str = base.START_DATE,
    end: str = base.END_DATE,
):
    results = {}
    for mode in ABLATION_MODES:
        results[mode] = run_ablation_backtest(mode, tickers, start, end)
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=[*ABLATION_MODES, "all"], default="all")
    parser.add_argument("--tickers", nargs="+", default=base.TICKERS)
    parser.add_argument("--start", default=base.START_DATE)
    parser.add_argument("--end", default=base.END_DATE)
    args = parser.parse_args()

    if args.mode == "all":
        run_all_ablations(args.tickers, args.start, args.end)
    else:
        run_ablation_backtest(args.mode, args.tickers, args.start, args.end)
