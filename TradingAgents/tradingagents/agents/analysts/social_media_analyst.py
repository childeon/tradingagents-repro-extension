# Modified from the original TradingAgents by Tauric Research.
# Original repository: https://github.com/TauricResearch/TradingAgents
# Original code licensed under the Apache License, Version 2.0.
# Modifications by Yujia Zhang, Ruiyan Li, Yeyuxi Yi — Columbia University, Spring 2026.
# Changes: Replaced get_news with get_social_sentiment; routes social-media analysis through local Reddit dataset.
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction, get_social_sentiment
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_social_sentiment,
        ]

        system_message = (
            "You are a social media sentiment analyst tasked with analyzing Reddit/social posts and public sentiment for a specific company. Use the exact ticker from the instrument context when calling get_social_sentiment(ticker, start_date, end_date). Use a recent trailing window ending on the current trade date, preferably the previous 7 calendar days when available. The tool returns local Reddit sentiment rows, daily polarity summaries, engagement counts, and representative posts. Write a comprehensive report explaining sentiment direction, engagement intensity, notable positive/negative themes, and implications for traders. Ground your conclusions in the returned sentiment counts, polarity scores, and example posts, and explicitly note if the sample is small or noisy."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node
