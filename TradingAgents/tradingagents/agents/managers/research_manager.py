# Modified from the original TradingAgents by Tauric Research.
# Original repository: https://github.com/TauricResearch/TradingAgents
# Original code licensed under the Apache License, Version 2.0.
# Modifications by Yujia Zhang, Ruiyan Li, Yeyuxi Yi — Columbia University, Spring 2026.
# Changes: Added no-research-debate ablation branch: synthesises analyst reports directly without bull/bear debate.

from tradingagents.agents.utils.agent_utils import build_instrument_context


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if history.strip():
            task_context = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision: align with the bear analyst, the bull analyst, or choose Hold only if it is strongly justified based on the arguments presented.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation—Buy, Sell, or Hold—must be clear and actionable. Avoid defaulting to Hold simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments.
"""
            evidence_context = f"""Here is the debate:
Debate History:
{history}"""
        else:
            task_context = """You are an investment synthesis manager operating in the no-research-debate ablation mode. There is intentionally no bull/bear debate history. Your role is to synthesize the analyst reports directly and make a definitive investment recommendation for the trader.

Summarize the strongest evidence from the market, social sentiment, news, and fundamentals reports. Your recommendation—Buy, Sell, or Hold—must be clear and actionable. Avoid defaulting to Hold unless it is strongly justified by the analyst evidence.
"""
            evidence_context = f"""Analyst reports available:
Market report:
{market_research_report}

Social sentiment report:
{sentiment_report}

News report:
{news_report}

Fundamentals report:
{fundamentals_report}"""

        prompt = f"""{task_context}

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting. 

Here are your past reflections on mistakes:
\"{past_memory_str}\"

{instrument_context}

{evidence_context}"""
        response = llm.invoke(prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
