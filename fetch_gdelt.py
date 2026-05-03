"""Download GDELT Amazon news for Dec 2023 + Jan 2024, filter to finance domains."""

import requests, time, json, pandas as pd
from pathlib import Path

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
OUT  = Path(__file__).parent / "amzn_gdelt_news_dec2023_jan2024.csv"

QUERY = '"Amazon" sourcelang:english'

WINDOWS = [
    ("20231201000000", "20231210235959"),
    ("20231211000000", "20231220235959"),
    ("20231221000000", "20231231235959"),
    ("20240101000000", "20240110235959"),
    ("20240111000000", "20240120235959"),
    ("20240121000000", "20240131235959"),
]

FINANCE_DOMAINS = {
    "fool.com", "finance.yahoo.com", "news.yahoo.com", "yahoo.com",
    "benzinga.com", "marketwatch.com", "seekingalpha.com", "thestreet.com",
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "barrons.com",
    "cnbc.com", "businessinsider.com", "forbes.com", "fortune.com",
    "investopedia.com", "zacks.com", "nasdaq.com", "stockanalysis.com",
    "investing.com", "investorplace.com", "proactiveinvestors.com",
    "economictimes.indiatimes.com", "livemint.com", "moneycontrol.com",
    "apnews.com", "techcrunch.com", "theverge.com", "arstechnica.com",
    "wired.com", "cnet.com", "zdnet.com", "venturebeat.com",
    "nytimes.com", "washingtonpost.com", "cbsnews.com", "nbcnews.com",
    "bbc.com", "bbc.co.uk", "theguardian.com", "axios.com",
    "morningstar.com", "valuewalk.com", "247wallst.com",
    "globenewswire.com", "prnewswire.com", "businesswire.com",
    "accesswire.com", "globeandmail.com", "financialpost.com",
}


def fetch_window(start, end, retries=5):
    params = {
        "query": QUERY, "mode": "artlist",
        "maxrecords": 250, "startdatetime": start,
        "enddatetime": end, "format": "json",
    }
    for attempt in range(retries):
        try:
            r = requests.get(BASE, params=params, timeout=45)
            if r.text.strip().startswith("{"):
                return r.json().get("articles", [])
            wait = 8 * (2 ** attempt)
            print(f"  non-JSON → retry in {wait}s: {r.text[:60].strip()}", flush=True)
            time.sleep(wait)
        except Exception as e:
            wait = 8 * (2 ** attempt)
            print(f"  error: {e} → retry in {wait}s", flush=True)
            time.sleep(wait)
    return []


articles = []
seen_urls: set[str] = set()

for start, end in WINDOWS:
    print(f"Fetching {start[:8]}–{end[:8]} …", end=" ", flush=True)
    batch = fetch_window(start, end)
    new = 0
    for a in batch:
        url = a.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            articles.append({
                "date":     a.get("seendate", "")[:8],  # raw YYYYMMDD string
                "title":    a.get("title", "").strip(),
                "domain":   a.get("domain", ""),
                "url":      url,
                "language": a.get("language", ""),
            })
            new += 1
    print(f"batch={len(batch)}  new={new}  running={len(articles)}", flush=True)
    time.sleep(3)

# ── Parse dates (raw strings are YYYYMMDD integers, e.g. "20231205") ─────────
df = pd.DataFrame(articles)
df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
df = df.dropna(subset=["date"]).drop_duplicates("title").sort_values("date").reset_index(drop=True)

print(f"\nRaw total: {len(df)}")

# ── Finance-domain filter ────────────────────────────────────────────────────
df_finance = df[df["domain"].isin(FINANCE_DOMAINS)].reset_index(drop=True)

print(f"After finance filter: {len(df_finance)}")
print("\nTop domains:")
print(df_finance["domain"].value_counts().head(12).to_string())

# Coverage check
print("\nArticles per week:")
df_finance["week"] = df_finance["date"].dt.to_period("W")
print(df_finance.groupby("week").size().to_string())

df_finance.drop(columns=["week"]).to_csv(OUT, index=False)
print(f"\nSaved → {OUT.name}")

print("\nSample titles:")
for t in df_finance["title"].head(10):
    print(" -", t)
