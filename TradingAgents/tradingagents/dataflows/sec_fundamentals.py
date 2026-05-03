"""SEC EDGAR companyfacts-backed fundamentals.

The SEC companyfacts API gives point-in-time XBRL facts with filing dates.
These helpers turn that raw fact table into compact reports for the
fundamentals analyst while filtering out facts unavailable on the trade date.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd

from .config import get_config


SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "TradingAgents academic research contact@example.com",
)

TICKER_CIK_FALLBACK = {
    "AMZN": "0001018724",
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "GOOG": "0001652044",
    "META": "0001326801",
    "NVDA": "0001045810",
    "TSLA": "0001318605",
}

METRICS = {
    "revenue": {
        "label": "Revenue",
        "tags": ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "statement": "income",
        "unit": "USD",
    },
    "cost_of_revenue": {
        "label": "Cost of Revenue",
        "tags": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
        "statement": "income",
        "unit": "USD",
    },
    "gross_profit": {
        "label": "Gross Profit",
        "tags": ["GrossProfit"],
        "statement": "income",
        "unit": "USD",
    },
    "operating_income": {
        "label": "Operating Income",
        "tags": ["OperatingIncomeLoss"],
        "statement": "income",
        "unit": "USD",
    },
    "net_income": {
        "label": "Net Income",
        "tags": ["NetIncomeLoss"],
        "statement": "income",
        "unit": "USD",
    },
    "eps_diluted": {
        "label": "Diluted EPS",
        "tags": ["EarningsPerShareDiluted"],
        "statement": "income",
        "unit": "USD/shares",
    },
    "assets": {
        "label": "Total Assets",
        "tags": ["Assets"],
        "statement": "balance",
        "unit": "USD",
    },
    "current_assets": {
        "label": "Current Assets",
        "tags": ["AssetsCurrent"],
        "statement": "balance",
        "unit": "USD",
    },
    "cash": {
        "label": "Cash and Cash Equivalents",
        "tags": ["CashAndCashEquivalentsAtCarryingValue"],
        "statement": "balance",
        "unit": "USD",
    },
    "inventory": {
        "label": "Inventory",
        "tags": ["InventoryNet"],
        "statement": "balance",
        "unit": "USD",
    },
    "current_liabilities": {
        "label": "Current Liabilities",
        "tags": ["LiabilitiesCurrent"],
        "statement": "balance",
        "unit": "USD",
    },
    "liabilities": {
        "label": "Total Liabilities",
        "tags": ["Liabilities"],
        "statement": "balance",
        "unit": "USD",
    },
    "long_term_debt": {
        "label": "Long-Term Debt",
        "tags": ["LongTermDebtNoncurrent", "LongTermDebt"],
        "statement": "balance",
        "unit": "USD",
    },
    "equity": {
        "label": "Stockholders' Equity",
        "tags": ["StockholdersEquity"],
        "statement": "balance",
        "unit": "USD",
    },
    "operating_cash_flow": {
        "label": "Operating Cash Flow",
        "tags": ["NetCashProvidedByUsedInOperatingActivities"],
        "statement": "cashflow",
        "unit": "USD",
    },
    "capex": {
        "label": "Capital Expenditures",
        "tags": [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ],
        "statement": "cashflow",
        "unit": "USD",
    },
    "investing_cash_flow": {
        "label": "Investing Cash Flow",
        "tags": ["NetCashProvidedByUsedInInvestingActivities"],
        "statement": "cashflow",
        "unit": "USD",
    },
    "financing_cash_flow": {
        "label": "Financing Cash Flow",
        "tags": ["NetCashProvidedByUsedInFinancingActivities"],
        "statement": "cashflow",
        "unit": "USD",
    },
}


def _repo_root_candidates() -> list[Path]:
    cwd = Path.cwd()
    module_path = Path(__file__).resolve()
    return [cwd, *cwd.parents, module_path.parents[3], *module_path.parents]


def _find_local_file(filename: str) -> Path | None:
    for root in _repo_root_candidates():
        path = root / filename
        if path.exists():
            return path
    return None


def _compact_accn(accn: Any) -> str:
    return re.sub(r"\D", "", str(accn or ""))


def _format_cik(cik: Any) -> str:
    return str(cik).strip().zfill(10)


def _ticker_to_cik(ticker: str) -> str | None:
    ticker = ticker.upper()
    submissions_path = _find_local_file("submissions.csv")
    if submissions_path:
        usecols = ["cik", "ticker"]
        submissions = pd.read_csv(submissions_path, usecols=usecols)
        rows = submissions[submissions["ticker"].astype(str).str.upper() == ticker]
        if not rows.empty:
            return _format_cik(rows.iloc[0]["cik"])
    return TICKER_CIK_FALLBACK.get(ticker)


def _load_companyfacts(cik: str) -> dict[str, Any]:
    config = get_config()
    cache_dir = Path(config["data_cache_dir"]) / "sec_companyfacts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"CIK{cik}.json"

    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    url = SEC_COMPANYFACTS_URL.format(cik=cik)
    req = Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with urlopen(req, timeout=30) as response:
        data = json.load(response)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def _facts_to_frame(companyfacts: dict[str, Any]) -> pd.DataFrame:
    rows = []
    us_gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag, payload in us_gaap.items():
        label = payload.get("label", tag)
        for unit, facts in payload.get("units", {}).items():
            for fact in facts:
                rows.append(
                    {
                        "tag": tag,
                        "label": label,
                        "unit": unit,
                        "start": fact.get("start"),
                        "end": fact.get("end"),
                        "filed": fact.get("filed"),
                        "form": fact.get("form"),
                        "fp": fact.get("fp"),
                        "fy": fact.get("fy"),
                        "frame": fact.get("frame"),
                        "accn": fact.get("accn"),
                        "adsh": _compact_accn(fact.get("accn")),
                        "value": fact.get("val"),
                    }
                )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ["start", "end", "filed"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _load_submissions(ticker: str) -> pd.DataFrame:
    path = _find_local_file("submissions.csv")
    if not path:
        return pd.DataFrame()
    usecols = ["adsh", "cik", "form", "period", "accepted", "ticker"]
    df = pd.read_csv(path, usecols=usecols)
    df = df[df["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if df.empty:
        return df
    df["accepted"] = pd.to_datetime(df["accepted"], errors="coerce")
    df["period"] = pd.to_datetime(df["period"], errors="coerce")
    df["adsh"] = df["adsh"].map(_compact_accn)
    return df


def _latest_submission_metadata(ticker: str, curr_date: str, freq: str = "quarterly") -> dict[str, Any] | None:
    """Return optional local filing metadata when submissions.csv exists.

    Fact selection does not depend on this file; it is only a report header
    cross-check with accepted timestamps.
    """
    submissions = _load_submissions(ticker)
    if submissions.empty:
        return None
    trade_dt = pd.to_datetime(curr_date)
    forms = ["10-Q"] if freq.lower().startswith("q") else ["10-K"]
    rows = submissions[
        submissions["form"].isin(forms)
        & submissions["accepted"].notna()
        & (submissions["accepted"] <= trade_dt + pd.Timedelta(days=1))
    ].sort_values("accepted")
    if rows.empty and forms == ["10-Q"]:
        rows = submissions[
            submissions["form"].isin(["10-Q", "10-K"])
            & submissions["accepted"].notna()
            & (submissions["accepted"] <= trade_dt + pd.Timedelta(days=1))
        ].sort_values("accepted")
    if rows.empty:
        return None
    return rows.iloc[-1].to_dict()


def _duration_days(row: pd.Series) -> int | None:
    if pd.isna(row.get("start")) or pd.isna(row.get("end")):
        return None
    return int((row["end"] - row["start"]).days) + 1


def _fact_period_matches(row: pd.Series, statement: str, freq: str) -> bool:
    days = _duration_days(row)
    if statement == "balance":
        return days is None or days <= 2
    if freq.lower().startswith("a"):
        return days is not None and 330 <= days <= 380
    return days is not None and 70 <= days <= 110


def _latest_fact_period(facts: pd.DataFrame, curr_date: str, freq: str) -> pd.Timestamp | None:
    """Find latest available 10-Q/10-K period using companyfacts only."""
    trade_dt = pd.to_datetime(curr_date)
    forms = ["10-K"] if freq.lower().startswith("a") else ["10-Q"]
    rows = facts[
        facts["filed"].notna()
        & (facts["filed"] <= trade_dt)
        & facts["form"].isin(forms)
        & facts["end"].notna()
    ].copy()
    if rows.empty and forms == ["10-Q"]:
        rows = facts[
            facts["filed"].notna()
            & (facts["filed"] <= trade_dt)
            & facts["form"].isin(["10-Q", "10-K"])
            & facts["end"].notna()
        ].copy()
    if rows.empty:
        return None

    rows["_valid_period"] = rows.apply(
        lambda r: _fact_period_matches(r, "income", freq)
        or _fact_period_matches(r, "balance", freq),
        axis=1,
    )
    rows = rows[rows["_valid_period"]]
    if rows.empty:
        return None
    return rows["end"].max()


def _period_score(row: pd.Series, statement: str, period: pd.Timestamp | None, freq: str) -> tuple[int, int]:
    end = row.get("end")
    end_score = 1 if period is not None and pd.notna(end) and end.date() == period.date() else 0
    days = _duration_days(row)
    if statement == "balance":
        duration_score = 2 if days is None or days <= 2 else 0
    elif freq.lower().startswith("a"):
        duration_score = 2 if days is not None and 330 <= days <= 380 else 0
    else:
        duration_score = 2 if days is not None and 70 <= days <= 110 else 0
    return (end_score, duration_score)


def _select_fact(
    facts: pd.DataFrame,
    tags: list[str],
    unit: str,
    statement: str,
    target_period: pd.Timestamp | None,
    curr_date: str,
    freq: str,
) -> pd.Series | None:
    trade_dt = pd.to_datetime(curr_date)
    rows = facts[
        facts["tag"].isin(tags)
        & (facts["unit"] == unit)
        & facts["filed"].notna()
        & (facts["filed"] <= trade_dt)
        & facts["form"].isin(["10-Q", "10-K"])
    ].copy()
    if rows.empty:
        return None

    period = target_period
    if period is not None:
        rows = rows[rows["end"].notna() & (rows["end"].dt.date == period.date())].copy()
        if rows.empty:
            return None
    elif "end" in rows:
        period = rows["end"].dropna().max()

    rows["_score"] = rows.apply(lambda r: _period_score(r, statement, period, freq), axis=1)
    rows = rows.sort_values(["_score", "filed", "end"], ascending=[False, False, False])
    return rows.iloc[0] if not rows.empty else None


def _derived_value(values: dict[str, Any], key: str) -> float | None:
    if key == "gross_profit":
        revenue = _raw(values, "revenue", allow_derived=False)
        cost_of_revenue = _raw(values, "cost_of_revenue", allow_derived=False)
        if revenue is not None and cost_of_revenue is not None:
            return revenue - cost_of_revenue
    if key == "liabilities":
        assets = _raw(values, "assets", allow_derived=False)
        equity = _raw(values, "equity", allow_derived=False)
        if assets is not None and equity is not None:
            return assets - equity
    return None


def _metric_values(ticker: str, curr_date: str, freq: str = "quarterly") -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    cik = _ticker_to_cik(ticker)
    if not cik:
        raise ValueError(f"No CIK found for ticker {ticker}")

    companyfacts = _load_companyfacts(cik)
    facts = _facts_to_frame(companyfacts)
    target_period = _latest_fact_period(facts, curr_date, freq)
    submission = _latest_submission_metadata(ticker, curr_date, freq)

    values = {}
    for key, spec in METRICS.items():
        row = _select_fact(
            facts,
            spec["tags"],
            spec["unit"],
            spec["statement"],
            target_period,
            curr_date,
            freq,
        )
        values[key] = {"spec": spec, "row": row}
    meta = {
        "ticker": ticker.upper(),
        "cik": cik,
        "entity_name": companyfacts.get("entityName", ticker.upper()),
        "submission": submission,
        "target_period": target_period,
    }
    return meta, values, facts


def get_latest_fundamental_period(ticker: str, curr_date: str, freq: str = "quarterly") -> str:
    """Return latest SEC fact period available for a ticker/date, or curr_date.

    This is used by analyst-report caching so repeated trading days in the
    same filing period can reuse one fundamentals analyst report.
    """
    cik = _ticker_to_cik(ticker)
    if not cik:
        return curr_date
    companyfacts = _load_companyfacts(cik)
    facts = _facts_to_frame(companyfacts)
    period = _latest_fact_period(facts, curr_date, freq)
    return period.strftime("%Y-%m-%d") if period is not None else curr_date


def _fmt_value(value: Any, unit: str) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if unit == "USD":
        abs_value = abs(float(value))
        if abs_value >= 1_000_000_000:
            return f"${float(value) / 1_000_000_000:,.2f}B"
        if abs_value >= 1_000_000:
            return f"${float(value) / 1_000_000:,.2f}M"
        return f"${float(value):,.0f}"
    if unit == "USD/shares":
        return f"${float(value):,.2f}"
    return f"{float(value):,.2f}"


def _raw(values: dict[str, Any], key: str, allow_derived: bool = True) -> float | None:
    row = values.get(key, {}).get("row")
    if row is None and allow_derived:
        return _derived_value(values, key)
    if row is None:
        return None
    val = row.get("value")
    return None if val is None or pd.isna(val) else float(val)


def _ratio_lines(values: dict[str, Any]) -> list[str]:
    revenue = _raw(values, "revenue")
    net_income = _raw(values, "net_income")
    current_assets = _raw(values, "current_assets")
    current_liabilities = _raw(values, "current_liabilities")
    liabilities = _raw(values, "liabilities")
    equity = _raw(values, "equity")
    operating_cash_flow = _raw(values, "operating_cash_flow")
    capex = _raw(values, "capex")

    lines = []
    if revenue and net_income is not None:
        lines.append(f"- Net Margin: {net_income / revenue:.2%}")
    if current_assets is not None and current_liabilities:
        lines.append(f"- Current Ratio: {current_assets / current_liabilities:.2f}")
    if liabilities is not None and equity:
        lines.append(f"- Liabilities / Equity: {liabilities / equity:.2f}")
    if net_income is not None and equity:
        lines.append(f"- Return on Equity: {net_income / equity:.2%}")
    if operating_cash_flow is not None and capex is not None:
        lines.append(f"- Free Cash Flow: {_fmt_value(operating_cash_flow - capex, 'USD')}")
    return lines


def _report_header(meta: dict[str, Any], curr_date: str, title: str) -> str:
    submission = meta.get("submission")
    target_period = meta.get("target_period")
    lines = [
        f"# {title} for {meta['entity_name']} ({meta['ticker']})",
        f"Trade date / point-in-time cutoff: {curr_date}",
        f"SEC CIK: {meta['cik']}",
    ]
    if target_period is not None:
        lines.append(f"Latest SEC fact period selected: {target_period.strftime('%Y-%m-%d')}")
    if submission:
        accepted = submission.get("accepted")
        accepted_str = accepted.strftime("%Y-%m-%d %H:%M:%S") if hasattr(accepted, "strftime") else str(accepted)
        period = submission.get("period")
        period_str = period.strftime("%Y-%m-%d") if hasattr(period, "strftime") else str(period)
        lines.append(
            f"Optional submissions.csv cross-check: latest available {submission.get('form')} period ended {period_str}, accepted {accepted_str}, accession {submission.get('adsh')}"
        )
    lines.append("Source: SEC EDGAR companyfacts API; facts filtered by SEC filed date to avoid look-ahead bias.")
    return "\n".join(lines)


def _statement_table(values: dict[str, Any], statement: str) -> str:
    lines = ["| Metric | Value | Period End | Filed | SEC Tag |", "|---|---:|---|---|---|"]
    for key, item in values.items():
        spec = item["spec"]
        if spec["statement"] != statement:
            continue
        row = item["row"]
        if row is None:
            derived = _derived_value(values, key)
            if derived is not None:
                lines.append(f"| {spec['label']} | {_fmt_value(derived, spec['unit'])} | Derived | Derived | Derived from SEC facts |")
            else:
                lines.append(f"| {spec['label']} | N/A | N/A | N/A | {', '.join(spec['tags'])} |")
            continue
        end = row["end"].strftime("%Y-%m-%d") if pd.notna(row["end"]) else "N/A"
        filed = row["filed"].strftime("%Y-%m-%d") if pd.notna(row["filed"]) else "N/A"
        lines.append(
            f"| {spec['label']} | {_fmt_value(row['value'], spec['unit'])} | {end} | {filed} | {row['tag']} |"
        )
    return "\n".join(lines)


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    meta, values, _ = _metric_values(ticker, curr_date, "quarterly")
    sections = [
        _report_header(meta, curr_date, "SEC Point-in-Time Fundamentals"),
        "\n## Key Financial Metrics",
        _statement_table(values, "income"),
        "\n## Balance Sheet Snapshot",
        _statement_table(values, "balance"),
        "\n## Cash Flow Snapshot",
        _statement_table(values, "cashflow"),
    ]
    ratios = _ratio_lines(values)
    if ratios:
        sections.extend(["\n## Derived Ratios", "\n".join(ratios)])
    return "\n".join(sections)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    meta, values, _ = _metric_values(ticker, curr_date, freq)
    return "\n\n".join(
        [
            _report_header(meta, curr_date, "SEC Balance Sheet"),
            _statement_table(values, "balance"),
        ]
    )


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    meta, values, _ = _metric_values(ticker, curr_date, freq)
    return "\n\n".join(
        [
            _report_header(meta, curr_date, "SEC Cash Flow Statement"),
            _statement_table(values, "cashflow"),
        ]
    )


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    meta, values, _ = _metric_values(ticker, curr_date, freq)
    return "\n\n".join(
        [
            _report_header(meta, curr_date, "SEC Income Statement"),
            _statement_table(values, "income"),
        ]
    )
