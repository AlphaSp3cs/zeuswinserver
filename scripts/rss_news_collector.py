#!/usr/bin/env python3
"""
Lightweight RSS/Atom news collector as fallback when blogwatcher-cli is unavailable.
Writes structured JSON with title, link, published, summary, source.
"""
import json, os, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
import feedparser

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
OUT_DIR = BASE / 'artifacts' / 'rss_news'
CONFIG = BASE / 'config' / 'rss_feeds.json'

DEFAULT_FEEDS = [
  {"name":"Reuters Markets","url":"https://feeds.reuters.com/reuters/businessNews","category":"world"},
  {"name":"Reuters Tech","url":"https://feeds.reuters.com/reuters/technologyNews","category":"world"},
  {"name":"CNBC Top News","url":"https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15837362","category":"world"},
  {"name":"MarketWatch","url":"http://feeds.marketwatch.com/marketwatch/topstories/","category":"world"},
  {"name":"Investing.com","url":"https://www.investing.com/rss/news.rss","category":"world"},
  {"name":"CoinDesk","url":"https://www.coindesk.com/arc/outboundfeeds/rss/","category":"crypto"},
  {"name":"Cointelegraph","url":"https://cointelegraph.com/rss","category":"crypto"},
  {"name":"ForexLive","url":"https://www.forexlive.com/feed/news","category":"fx"},
  {"name":"ActionForex","url":"https://www.actionforex.com/feed/","category":"fx"},
  {"name":"OilPrice","url":"https://oilprice.com/rss/main","category":"commodities"},
  {"name":"Kitco Gold","url":"https://www.kitco.com/rss/news","category":"commodities"},
]

KEYWORDS = {
  'crypto': ['bitcoin','ethereum','btc','eth','xrp','solana','sol','crypto','blockchain','etf','sec','tokenized','blackrock','fidelity'],
  'fx': ['usdjpy','eurusd','gbpusd','usd/jpy','intervention','boj','ecb','fed','treasury','dollar','yen','euro','sterling'],
  'commodities': ['oil','wti','brent','gold','silver','natural gas','opec+','iran','ceasefire','supply','inventory','cftc','commodity'],
  'equities': ['earnings','eps','revenue','guidance','forecast','tariff','lawsuit','sec investigation','delivery','catalyst','premarket','futures','yield'],
  'macro': ['ism','pmi','manufacturing','construction spending','jolts','10 year','treasury auction','payrolls','nonfarm','gdp','pce','cpi','inflation','jobs']
}

def load_feeds():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding='utf-8'))
        except Exception:
            pass
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(DEFAULT_FEEDS, indent=2), encoding='utf-8')
    return DEFAULT_FEEDS

def clean(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()

def classify(text):
    text_lower = clean(text).lower()
    cats = []
    for cat, kws in KEYWORDS.items():
        if any(k in text_lower for k in kws):
            cats.append(cat)
    return cats or ['uncategorized']

def fetch_feed(feed):
    items = []
    try:
        parsed = feedparser.parse(feed['url'])
        source = feed.get('name') or parsed.feed.get('title') or feed['url']
        for e in parsed.entries[:20]:
            title = clean(e.get('title',''))
            link = clean(e.get('link',''))
            summary = clean(e.get('summary','') or e.get('description',''))
            published = e.get('published') or e.get('updated') or datetime.now(timezone.utc).isoformat()
            text = f"{title} {summary}"
            item = {
                'title': title,
                'link': link,
                'published': published,
                'summary': summary,
                'source': source,
                'categories': classify(text),
                'hash': hashlib.sha1((title+link).encode('utf-8')).hexdigest()[:12]
            }
            items.append(item)
    except Exception as e:
        items.append({'title':'feed_error','link':feed['url'],'published':datetime.now(timezone.utc).isoformat(),'summary':str(e),'source':feed['name'],'categories':['error'],'hash':'error'})
    return items

def main():
    feeds = load_feeds()
    all_items = []
    for feed in feeds:
        items = fetch_feed(feed)
        all_items.extend(items)
    # Sort by published desc naive
    all_items.sort(key=lambda x: x.get('published',''), reverse=True)
    payload = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'feed_count': len(feeds),
        'item_count': len(all_items),
        'items': all_items
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f'rss_news_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
    out_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    latest = OUT_DIR / 'rss_news_latest.json'
    latest.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({'written': str(out_path), 'item_count': len(all_items)}, indent=2))

if __name__ == '__main__':
    main()
