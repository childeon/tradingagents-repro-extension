"""Local file-backed news dataflows (CSV or Excel).

Supports two file formats:
  - Bloomberg/Yahoo xlsx  (event_time_utc, text, publisher, url_or_link, ticker_match, ...)
  - GDELT CSV             (date, title, domain, url, optional summary/snippet/text)
  - Generic fallback      (auto-detects date/title/text/publisher/url columns)

Register as vendor "local" in config:
    config["data_vendors"]["news_data"] = "local,yfinance"
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _repo_root_candidates() -> list[Path]:
    cwd = Path.cwd()
    module_path = Path(__file__).resolve()
    return [cwd, *cwd.parents, module_path.parents[3], *module_path.parents]


def _find_news_file(ticker: str) -> Path | None:
    ticker = ticker.upper()
    t = ticker.lower()

    patterns = [
        f"{t}_gdelt_news*.csv",
        f"{t}_news*.csv",
        f"{t}_news*.xlsx",
        f"*{t}*news*.csv",
        f"*{t}*news*.xlsx",
    ]
    if ticker == "AMZN":
        patterns += [
            "amzn_gdelt_news*.csv",
            "amzn_news*.xlsx",
            "AmazonNews*.csv",
        ]

    search_dirs: list[Path] = []
    for root in _repo_root_candidates():
        search_dirs.append(root)
        for subdir in ("data/raw/news", "data/raw", "data"):
            candidate = root / subdir
            if candidate.exists():
                search_dirs.append(candidate)

    for directory in search_dirs:
        for pattern in patterns:
            matches = sorted(directory.glob(pattern))
            if matches:
                return matches[0]

    return None


# ---------------------------------------------------------------------------
# Loading & normalisation
# ---------------------------------------------------------------------------

def _load_and_normalize(path: Path, ticker: str) -> pd.DataFrame:
    """Return a DataFrame with columns: date, title, summary, publisher, url."""
    suffix = path.suffix.lower()
    df = pd.read_excel(path) if suffix in (".xlsx", ".xls") else pd.read_csv(path)
    cols = set(df.columns)

    # ── Bloomberg/Yahoo xlsx ──────────────────────────────────────────────
    if "event_time_utc" in cols and "text" in cols:
        # Filter to rows that mention this ticker
        if "ticker_match" in cols:
            amzn_rows = df[df["ticker_match"] == True]
            if not amzn_rows.empty:
                df = amzn_rows.copy()
        elif "stocks" in cols:
            df = df[df["stocks"].astype(str).str.contains(ticker, na=False)].copy()

        df["_date"] = pd.to_datetime(df["event_time_utc"], errors="coerce", utc=True).dt.tz_localize(None)

        raw_text = df["text"].astype(str)
        df["_title"] = raw_text.str.split("\n").str[0].str.strip()
        df["_summary"] = raw_text.apply(
            lambda t: "\n".join(t.split("\n")[1:]).strip()[:500] if "\n" in t else ""
        )

        # Prefer wire publisher over platform source
        pub = df.get("publisher", pd.Series(dtype=str))
        src = df.get("source", pd.Series(dtype=str))
        df["_publisher"] = pub.where(pub.notna() & (pub != ""), src).fillna("Unknown")
        df["_url"] = df.get("url_or_link", pd.Series(dtype=str)).fillna("")

    # ── GDELT CSV ─────────────────────────────────────────────────────────
    elif "domain" in cols and "title" in cols:
        df["_date"] = pd.to_datetime(df["date"], errors="coerce")
        df["_title"] = df["title"].astype(str)
        summary_col = next(
            (col for col in ("summary", "snippet", "description", "text") if col in cols),
            None,
        )
        df["_summary"] = df[summary_col].astype(str).str[:500] if summary_col else ""
        df["_publisher"] = df["domain"].astype(str)
        df["_url"] = df.get("url", pd.Series(dtype=str)).fillna("")

    # ── Generic fallback ──────────────────────────────────────────────────
    else:
        def _pick(keywords: list[str]) -> str | None:
            return next((c for c in df.columns if any(k in c.lower() for k in keywords)), None)

        date_col = _pick(["date", "time", "published"])
        title_col = _pick(["title", "headline"])
        text_col = _pick(["text", "body", "content", "summary"])
        pub_col = _pick(["publisher", "source", "domain", "outlet"])
        url_col = _pick(["url", "link"])

        df["_date"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT
        df["_title"] = df[title_col].astype(str) if title_col else "No title"
        df["_summary"] = df[text_col].astype(str).str[:500] if text_col else ""
        df["_publisher"] = df[pub_col].astype(str) if pub_col else "Unknown"
        df["_url"] = df[url_col].astype(str) if url_col else ""

    result = df[["_date", "_title", "_summary", "_publisher", "_url"]].copy()
    result.columns = ["date", "title", "summary", "publisher", "url"]
    return result[result["date"].notna()].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public dataflow functions
# ---------------------------------------------------------------------------

def get_news_local(ticker: str, start_date: str, end_date: str) -> str:
    max_articles = 25
    path = _find_news_file(ticker)
    if not path:
        return f"No local news file found for {ticker}."

    df = _load_and_normalize(path, ticker)

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date) + pd.Timedelta(days=1)
    df = df[(df["date"] >= start) & (df["date"] < end)].sort_values("date")

    if df.empty:
        return f"No local news found for {ticker} between {start_date} and {end_date}."

    total_articles = len(df)
    if total_articles > max_articles:
        df = df.tail(max_articles)

    news_str = ""
    for _, row in df.iterrows():
        news_str += f"### {row['date'].date()} - {row['title']} (source: {row['publisher']})\n"
        if row["summary"]:
            news_str += f"{row['summary']}\n"
        if row["url"]:
            news_str += f"Link: {row['url']}\n"
        news_str += "\n"

    header = f"## {ticker} News, from {start_date} to {end_date}"
    if total_articles > max_articles:
        header += f" (showing latest {max_articles} of {total_articles} local articles)"
    header += ":\n\n"
    return header + news_str


def get_global_news_local(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    # Local files are ticker-specific; no global market file is available.
    return (
        "No local global news file configured. "
        "Set news_data vendor to 'local,yfinance' to fall back to yfinance for global news."
    )
