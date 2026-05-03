"""Local CSV-backed social sentiment dataflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


TICKER_COMPANY_MAP = {
    "AMZN": "amazon",
    "AAPL": "apple",
    "MSFT": "microsoft",
    "GOOGL": "google",
    "GOOG": "google",
    "META": "meta",
    "NVDA": "nvidia",
    "TSLA": "tesla",
}


def _repo_root_candidates() -> list[Path]:
    cwd = Path.cwd()
    module_path = Path(__file__).resolve()
    return [cwd, *cwd.parents, module_path.parents[3], *module_path.parents]


def _find_social_csv(ticker: str) -> Path | None:
    ticker = ticker.upper()
    names = [
        f"{ticker}Reddit.csv",
        f"{ticker.lower()}Reddit.csv",
    ]
    if ticker == "AMZN":
        names.extend(["AmazonReddit.csv", "amazon_reddit.csv"])

    for root in _repo_root_candidates():
        for name in names:
            path = root / name
            if path.exists():
                return path
        for subdir in ["data/raw/social", "data/raw", "data"]:
            folder = root / subdir
            if folder.exists():
                for pattern in [f"*{ticker}*reddit*.csv", "*AmazonReddit*.csv", "*reddit*.csv"]:
                    matches = list(folder.glob(pattern))
                    if matches:
                        return matches[0]
    return None


def _polarity(label: Any, score: Any) -> float:
    try:
        confidence = float(score)
    except (TypeError, ValueError):
        confidence = 1.0
    label_norm = str(label or "").strip().lower()
    if label_norm.startswith("pos"):
        return confidence
    if label_norm.startswith("neg"):
        return -confidence
    return 0.0


def _format_posts(posts: pd.DataFrame, limit: int) -> str:
    if posts.empty:
        return "No matching Reddit posts found."

    lines = []
    for _, row in posts.head(limit).iterrows():
        text = str(row.get("Cleaned_Text", "")).strip()
        if len(text) > 450:
            text = text[:450].rsplit(" ", 1)[0] + "..."
        lines.append(
            "- "
            f"{row['Date'].date()}: {row.get('Sentiment', 'Unknown')} "
            f"(polarity={row.get('polarity', 0):+.3f}, score={row.get('Score', 0)}, "
            f"comments={row.get('Comments', 0)}) - {text}"
        )
    return "\n".join(lines)


def get_social_sentiment(
    ticker: str,
    start_date: str,
    end_date: str,
    limit: int = 12,
) -> str:
    """Return local Reddit sentiment for a ticker/date range.

    Expected CSV columns include Date, Company, Cleaned_Text, Sentiment,
    Sentiment_Score, Score, and Comments. The current project has
    AmazonReddit.csv at the repo root.
    """
    path = _find_social_csv(ticker)
    if not path:
        return f"No local Reddit/social sentiment CSV found for {ticker}."

    df = pd.read_csv(path)
    if "Date" not in df.columns:
        return f"Local social CSV {path.name} is missing a Date column."

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df[df["Date"].notna()].copy()

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    df = df[(df["Date"] >= start) & (df["Date"] <= end)].copy()

    company_hint = TICKER_COMPANY_MAP.get(ticker.upper())
    if company_hint and "Company" in df.columns:
        df = df[df["Company"].astype(str).str.lower().str.contains(company_hint, na=False)]

    if df.empty:
        return f"No local Reddit/social sentiment rows found for {ticker} from {start_date} to {end_date}."

    df["polarity"] = df.apply(lambda r: _polarity(r.get("Sentiment"), r.get("Sentiment_Score")), axis=1)
    df["engagement"] = pd.to_numeric(df.get("Score", 0), errors="coerce").fillna(0) + pd.to_numeric(
        df.get("Comments", 0), errors="coerce"
    ).fillna(0)

    daily = (
        df.groupby(df["Date"].dt.date)
        .agg(
            posts=("Cleaned_Text", "count"),
            avg_polarity=("polarity", "mean"),
            total_engagement=("engagement", "sum"),
            positive=("Sentiment", lambda s: (s.astype(str).str.lower() == "positive").sum()),
            neutral=("Sentiment", lambda s: (s.astype(str).str.lower() == "neutral").sum()),
            negative=("Sentiment", lambda s: (s.astype(str).str.lower() == "negative").sum()),
        )
        .reset_index()
        .rename(columns={"Date": "date"})
    )

    weighted = (df["polarity"] * (df["engagement"] + 1)).sum() / (df["engagement"] + 1).sum()
    label_counts = df["Sentiment"].astype(str).value_counts().to_dict() if "Sentiment" in df.columns else {}
    top_posts = df.sort_values(["engagement", "Date"], ascending=[False, False])

    lines = [
        f"# Local Reddit Sentiment for {ticker.upper()}",
        f"Source file: {path.name}",
        f"Date range: {start_date} to {end_date}",
        f"Rows matched: {len(df)}",
        f"Sentiment counts: {label_counts}",
        f"Average polarity: {df['polarity'].mean():+.3f}",
        f"Engagement-weighted polarity: {weighted:+.3f}",
        "",
        "## Daily Sentiment Summary",
        daily.to_markdown(index=False),
        "",
        f"## Highest-Engagement Reddit Posts (top {min(limit, len(top_posts))})",
        _format_posts(top_posts, limit),
    ]
    return "\n".join(lines)
