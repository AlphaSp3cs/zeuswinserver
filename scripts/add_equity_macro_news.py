#!/usr/bin/env python3
"""
Append equity/macro specific headlines from targeted RSS + web queries.
"""
import json, re, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

FIRM = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm")
WORKFLOW = FIRM / "workflow"
TODAY = "2026-08-16"
jsonl_path = WORKFLOW / f"news_ingest_{TODAY}.jsonl"
HDR = {"User-Agent": "OuroTaurus/1.0"}
MAX_ITEMS = 120


def fetch_rss_titles(url, max_items=40):
    titles = []
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="ignore")
        titles = re.findall(r"<title>(.*?)</title>", raw)[:max_items]
    except Exception:
        pass
    return [t.strip() for t in titles if t.strip()]


def fetch_ddg_news(query, max_items=20):
    url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    titles = []
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="ignore")
        titles = re.findall(r'<a[^>]+class="result__a"[^>]*>(.*?)</a>', raw, re.S)[:max_items]
        titles = [re.sub(r"<[^>]+>", "", t).strip() for t in titles if t.strip()]
    except Exception:
        pass
    return titles


def main():
    ts = datetime.now(timezone.utc).isoformat()
    seen = set()
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                seen.add(rec.get("url") or rec.get("title"))
            except Exception:
                pass

    items = []
    rss_feeds = [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://rss.nytimes.com/xml/feed/markets.xml",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.bloomberg.com/markets/news/rss",
        "https://www.wsj.com/xml/rss/3_7031.xml",
        "https://www.wsj.com/xml/rss/3_7014.xml",
        "https://www.ft.com/rss/markets",
        "https://www.marketscreener.com/rss/market_news.php",
        "https://www.barrons.com/rss/market_news",
    ]
    queries = [
        "technology stocks news today AAPL NVDA MSFT",
        "financial stocks news today JPM GS BAC",
        "healthcare stocks news today JNJ PFE LLY UNH",
        "energy stocks news today XOM CVX COP",
        "consumer stocks news today TSLA AMZN WMT KO",
        "industrial stocks news today CAT GE HON UPS",
        "materials stocks news today FCX NEM",
        "utilities stocks news today NEE DUK SO",
        "real estate REIT news today PLD AMT VNQ",
        "Treasury yield news today",
        "gold price news today",
        "oil price news today",
        "dollar index news today",
        "S&P 500 Nasdaq news today",
    ]

    for url in rss_feeds:
        titles = fetch_rss_titles(url, max_items=35)
        for title in titles:
            if title in seen:
                continue
            seen.add(title)
            items.append({
                "ts": ts,
                "title": title,
                "source": urllib.parse.urlparse(url).hostname,
                "url": url,
                "published": "",
                "categories": title,
            })
            if len(items) >= MAX_ITEMS:
                break
        if len(items) >= MAX_ITEMS:
            break
        time.sleep(0.5)

    if len(items) < MAX_ITEMS:
        for q in queries:
            titles = fetch_ddg_news(q, max_items=15)
            for title in titles:
                if title in seen:
                    continue
                seen.add(title)
                items.append({
                    "ts": ts,
                    "title": title,
                    "source": "duckduckgo",
                    "url": "",
                    "published": "",
                    "categories": title,
                })
                if len(items) >= MAX_ITEMS:
                    break
            if len(items) >= MAX_ITEMS:
                break
            time.sleep(1.0)

    with jsonl_path.open("a", encoding="utf-8") as f:
        for rec in items:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("APPENDED", len(items), "to", jsonl_path)


if __name__ == "__main__":
    main()
