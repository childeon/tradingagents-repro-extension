# Modified from the original TradingAgents by Tauric Research.
# Original repository: https://github.com/TauricResearch/TradingAgents
# Original code licensed under the Apache License, Version 2.0.
# Modifications by Yujia Zhang, Ruiyan Li, Yeyuxi Yi — Columbia University, Spring 2026.
# Changes: Added date-parameterised SEC filing cache; prevents stale look-ahead data when backtesting historical periods.
import re
from pathlib import Path

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_language_instruction,
)
from tradingagents.dataflows.config import get_config


def _safe_cache_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _sec_fundamentals_cache_path(ticker: str, trade_date: str) -> Path | None:
    config = get_config()
    tool_vendor = config.get("tool_vendors", {}).get("get_fundamentals")
    category_vendor = config.get("data_vendors", {}).get("fundamental_data", "")
    vendor = tool_vendor or category_vendor
    if "sec" not in [part.strip() for part in str(vendor).lower().split(",")]:
        return None

    try:
        from tradingagents.dataflows.sec_fundamentals import get_latest_fundamental_period

        period = get_latest_fundamental_period(ticker, trade_date)
    except Exception:
        period = trade_date

    cache_dir = Path(config["data_cache_dir"]) / "analyst_reports" / "fundamentals"
    filename = f"{_safe_cache_part(ticker.upper())}_{_safe_cache_part(period)}.md"
    return cache_dir / filename


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        cache_path = _sec_fundamentals_cache_path(ticker, current_date)

        if cache_path and cache_path.exists():
            report = cache_path.read_text(encoding="utf-8")
            return {
                "messages": [AIMessage(content=report)],
                "fundamentals_report": report,
            }

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
        ]

        system_message = (
            "You are a fundamentals analyst. Analyze only the company financial information available as of the current trade date. The tools may return SEC point-in-time companyfacts data, including the latest available 10-Q/10-K period, income statement, balance sheet, cash flow statement, and derived ratios. Do not describe this as a past-week report; fundamentals update quarterly or annually. Write a comprehensive report on profitability, growth, liquidity, leverage, cash flow quality, valuation-relevant metrics when available, and key risks or strengths. Make sure to include as much detail as possible and ground every conclusion in the returned filing period, filed date, and financial metrics."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content
            if cache_path and report:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(report, encoding="utf-8")

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
