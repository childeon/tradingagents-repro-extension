# Modified from the original TradingAgents by Tauric Research.
# Original repository: https://github.com/TauricResearch/TradingAgents
# Original code licensed under the Apache License, Version 2.0.
# Modifications by Yujia Zhang, Ruiyan Li, Yeyuxi Yi — Columbia University, Spring 2026.
# Changes: Added no-risk-layer ablation branch: portfolio manager evaluates trader plan directly without risk debate.
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction


def create_portfolio_manager(llm, memory):
    def portfolio_manager_node(state) -> dict:

        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if history.strip():
            opening = "As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision."
            risk_context = f"""**Risk Analysts Debate History:**
{history}"""
            thesis_instruction = "Detailed reasoning anchored in the analysts' debate and past reflections."
        else:
            opening = "As the Portfolio Manager operating in the no-risk-layer ablation mode, directly evaluate the trader's plan and deliver the final trading decision. There is intentionally no risk analyst debate history."
            risk_context = "Risk analyst debate was omitted for this ablation. Perform a concise final risk check directly from the trader plan and analyst reports."
            thesis_instruction = "Detailed reasoning anchored in the trader plan, analyst reports, and past reflections."

        prompt = f"""{opening}

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
- Lessons from past decisions: **{past_memory_str}**

**Required Output Structure:**
1. **Rating**: State one of Buy / Overweight / Hold / Underweight / Sell.
2. **Executive Summary**: A concise action plan covering entry strategy, position sizing, key risk levels, and time horizon.
3. **Investment Thesis**: {thesis_instruction}

---

{risk_context}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return portfolio_manager_node
