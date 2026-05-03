from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.local_social_sentiment import get_social_sentiment as _get_social_sentiment


@tool
def get_social_sentiment(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    limit: Annotated[int, "Maximum number of example posts to return"] = 12,
) -> str:
    """
    Retrieve local Reddit/social sentiment data for a ticker and date range.
    Uses CSV files such as AmazonReddit.csv when present in the project.
    """
    return _get_social_sentiment(ticker, start_date, end_date, limit)
