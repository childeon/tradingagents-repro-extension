"""Add Apache 2.0 modification notices to all changed TradingAgents files."""
import os

BASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "TradingAgents"
)

HEADER = """\
# Modified from the original TradingAgents by Tauric Research.
# Original repository: https://github.com/TauricResearch/TradingAgents
# Original code licensed under the Apache License, Version 2.0.
# Modifications by Yujia Zhang, Ruiyan Li, Yeyuxi Yi — Columbia University, Spring 2026.
# Changes: {change}
"""

FILES = {
    "tradingagents/agents/analysts/fundamentals_analyst.py":
        "Added date-parameterised SEC filing cache; prevents stale look-ahead data when backtesting historical periods.",
    "tradingagents/agents/analysts/news_analyst.py":
        "Updated system prompt to use date-bounded local/GDELT news retrieval instead of live yfinance endpoint.",
    "tradingagents/agents/analysts/social_media_analyst.py":
        "Replaced get_news with get_social_sentiment; routes social-media analysis through local Reddit dataset.",
    "tradingagents/agents/analysts/market_analyst.py":
        "Clarified prompt: use shared OHLCV cache for stock data retrieval; disallow manual indicator calculation.",
    "tradingagents/dataflows/interface.py":
        "Registered 'sec' and 'local' data-vendor backends for SEC fundamentals and local GDELT/Reddit news.",
    "tradingagents/dataflows/y_finance.py":
        "Fixed stock-data retrieval to reuse shared OHLCV cache with date filtering, avoiding redundant yfinance calls.",
    "tradingagents/default_config.py":
        "Added ablation_mode key ('full' | 'no_research_debate' | 'no_risk_layer') for ablation experiments.",
    "tradingagents/graph/setup.py":
        "Added ablation mode wiring: skips debate layer or risk layer based on ablation_mode config.",
    "tradingagents/graph/trading_graph.py":
        "Added ablation_mode validation and registered get_social_sentiment tool for social-media agents.",
    "tradingagents/agents/managers/portfolio_manager.py":
        "Added no-risk-layer ablation branch: portfolio manager evaluates trader plan directly without risk debate.",
    "tradingagents/agents/managers/research_manager.py":
        "Added no-research-debate ablation branch: synthesises analyst reports directly without bull/bear debate.",
    "tradingagents/agents/utils/agent_utils.py":
        "Imported get_social_sentiment from social_data_tools for local Reddit sentiment access.",
}

SENTINEL = "Modified from the original TradingAgents"

for rel, change in FILES.items():
    path = os.path.join(BASE, rel)
    with open(path, "r") as f:
        content = f.read()
    if SENTINEL in content:
        print(f"skip  {rel}")
        continue
    notice = HEADER.format(change=change)
    with open(path, "w") as f:
        f.write(notice + content)
    print(f"  ✓   {rel}")

print("Done.")
