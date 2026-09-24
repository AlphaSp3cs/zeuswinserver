#!/usr/bin/env python3
"""
Build per-symbol equity/ETF/news mapping from:
- workflow/news_ingest_<date>.jsonl
- lightweight public sources

Outputs:
- workflow/news_symbol_map_<date>.json
"""
import json, re, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

FIRM = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm")
WORKFLOW = FIRM / "workflow"
TODAY = "2026-08-16"
jsonl_path = WORKFLOW / f"news_ingest_{TODAY}.jsonl"
out_path = WORKFLOW / f"news_symbol_map_{TODAY}.json"
HDR = {"User-Agent": "OuroTaurus/1.0"}

# Common symbol aliases and company names for better matching
SYMBOL_ALIASES = {
    'AAPL': ['apple','iphone','mac','ios','airpods','vision pro','tim cook'],
    'MSFT': ['microsoft','windows','azure','office 365','xbox','satya nadella'],
    'NVDA': ['nvidia','gpu','ai chip','cuda','jensen huang','blackwell'],
    'AMD': ['amd','ryzen','epyc','instinct','lisa su'],
    'INTC': ['intel','core','xeon','pat gelsinger'],
    'AVGO': ['broadcom','vmware','tomahawk'],
    'QCOM': ['qualcomm','snapdragon','android'],
    'TSLA': ['tesla','elon musk','model 3','model y','cybertruck','fsd'],
    'AMZN': ['amazon','aws','prime','jeff bezos','e-commerce'],
    'GOOGL': ['google','alphabet','search','youtube','android','pixel','sundar pichai'],
    'META': ['meta','facebook','instagram','whatsapp','mark zuckerberg','llama'],
    'NFLX': ['netflix','streaming',' Reed Hastings'],
    'DIS': ['disney','marvel','star wars','pixar','bob iger'],
    'JPM': ['jpmorgan','jamie dimon','banking'],
    'BAC': ['bank of america','bofa','brian moynihan'],
    'GS': ['goldman sachs','sachs','david solomon'],
    'JNJ': ['johnson','johnson & johnson','pharmaceutical'],
    'PFE': ['pfizer','vaccine','pill','albert bourla'],
    'UNH': ['unitedhealth','optum','andrew witty'],
    'LLY': ['eli lilly','insulin','trulicity','dave ricks'],
    'XOM': ['exxon','exxonmobil','darren woods'],
    'CVX': ['chevron','mike wyatt'],
    'COP': ['conocophillips','ryan lance'],
    'SLB': ['schlumberger','oilfield','fracking'],
    'CAT': ['caterpillar','earthmoving','jim umbrella'],
    'GE': ['general electric','aerospace','honeywell'],
    'HON': ['honeywell','automation'],
    'UPS': ['ups','parcel','delivery','carol tomé'],
    'KO': ['coca cola','coke','james quincey'],
    'PEP': ['pepsi','pepsico','ramon laguarta'],
    'WMT': ['walmart','retail','douglas mcmillon'],
    'PG': ['procter','p&g','consumer staples'],
    'NEE': ['nextera','renewable','solar'],
    'DUK': ['duke energy','utility'],
    'SO': ['southern company','utility'],
    'VNQ': ['reit','real estate','prologis','equinix'],
    'PLD': ['prologis','warehouse','reit'],
    'AMT': ['american tower','cell tower','reit'],
    'SPY': ['s&p 500','sp500','index'],
    'QQQ': ['nasdaq 100','invesco qqq','tech index'],
    'IWM': ['russell 2000','small cap'],
    '^GSPC': ['s&p 500','sp500','standard & poor'],
    '^IXIC': ['nasdaq','nasdaq composite'],
    '^RUT': ['russell 2000','small cap'],
    '^VIX': ['volatility index','cboe volatility'],
    '^FTSE': ['ftse 100','uk index'],
    '^GDAXI': ['dax','german index'],
    '^N225': ['nikkei','japan index'],
    'GC=F': ['gold','precious metal','safe haven'],
    'SI=F': ['silver','precious metal'],
    'HG=F': ['copper','base metal','industrial metal'],
    'CL=F': ['crude oil','wti','petroleum'],
    'NG=F': ['natural gas'],
    'BZ=F': ['brent crude','oil'],
    'ES=F': ['s&p 500 futures','spx futures'],
    'NQ=F': ['nasdaq 100 futures','nq futures'],
    'YM=F': ['dow futures','dji futures'],
    'RTY=F': ['russell 2000 futures'],
    'ZN=F': ['treasury note','10-year yield'],
    'ZB=F': ['treasury bond','30-year yield'],
    'TLT': ['treasury etf','long-term treasury'],
    'IEF': ['intermediate treasury'],
    'HYG': ['high yield','junk bond'],
    'LQD': ['investment grade','corporate bond'],
    '^TNX': ['10-year yield','treasury yield'],
    'BTC-USD': ['bitcoin','btc','crypto','blockchain'],
    'ETH-USD': ['ethereum','eth','smart contract','defi'],
    'SOL-USD': ['solana','sol','high throughput'],
    'XRP-USD': ['ripple','xrp','payment'],
    'AVAX-USD': ['avalanche','avax','subnet'],
    'LINK-USD': ['chainlink','oracle'],
    'ADA-USD': ['cardano','ada','stake'],
    'DOGE-USD': ['dogecoin','doge','meme'],
    'EURUSD=X': ['euro','eur','ecb','eurozone'],
    'GBPUSD=X': ['pound','sterling','gbp','boe'],
    'USDJPY=X': ['yen','jpy','boj','japan'],
    'AUDUSD=X': ['aussie','aud','rba'],
    'USDCAD=X': ['loonie','cad','boc'],
    'USDCHF=X': ['franc','chf','snb'],
    'NZDUSD=X': ['kiwi','nzd','rbnz'],
}


def fetch_public_rss(max_items=60):
    titles = []
    feeds = [
        'https://feeds.marketwatch.com/marketwatch/topstories/',
        'https://rss.nytimes.com/xml/feed/markets.xml',
        'https://www.cnbc.com/id/100003114/device/rss/rss.html',
    ]
    for url in feeds:
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode('utf-8', errors='ignore')
            titles.extend(re.findall(r'<title>(.*?)</title>', raw)[:max_items])
            time.sleep(0.5)
        except Exception:
            continue
    return [t.strip() for t in titles if t.strip()]


def fetch_web_queries(queries, limit=5):
    items = []
    try:
        from hermes_tools import web_search
    except Exception:
        return items
    for q in queries:
        try:
            res = web_search(q, limit=limit)
            web = (res.get('data') or {}).get('web') or []
            for r in web:
                title = (r.get('title') or '').strip()
                desc = (r.get('description') or '').strip()
                url = (r.get('url') or '').strip()
                source = (r.get('name') or 'web').strip()
                if title:
                    items.append({
                        'title': title,
                        'description': desc,
                        'source': source,
                        'url': url,
                    })
            time.sleep(0.5)
        except Exception:
            continue
    return items


def classify_symbol(title: str, symbol: str):
    low = title.lower()
    sym = symbol.lower()
    aliases = SYMBOL_ALIASES.get(symbol, [])
    if sym in low:
        return True
    for a in aliases:
        if a.lower() in low:
            return True
    return False


def score_text(text: str):
    POS = ['bullish', 'upgrade', 'growth', 'surge', 'rally', 'beat', 'outperform',
           'strong', 'gain', 'soar', 'breakthrough', 'record', 'win', 'approved']
    NEG = ['bearish', 'downgrade', 'recession', 'crash', 'miss', 'underperform',
           'weak', 'drop', 'decline', 'plunge', 'fear', 'lawsuit', 'cut', 'warning']
    low = text.lower()
    p = sum(low.count(w) for w in POS)
    n = sum(low.count(w) for w in NEG)
    if p > n:
        return min(100, 50 + p * 10 - n * 5), 'BULLISH'
    if n > p:
        return max(0, 50 - n * 10 + p * 5), 'BEARISH'
    return 50, 'NEUTRAL'


def main():
    ts = datetime.now(timezone.utc).isoformat()

    # Load existing ingest
    articles = []
    seen = set()
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding='utf-8', errors='ignore').splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            key = rec.get('url') or rec.get('title')
            if key and key not in seen:
                seen.add(key)
                articles.append(rec)

    rss_titles = fetch_public_rss()
    web_items = fetch_web_queries([
        'stock market news today',
        'S&P 500 Nasdaq news',
        'Treasury yields news',
        'gold silver price news',
        'oil price news',
        'dollar euro yen news',
    ])

    # Build symbol→headlines map
    symbol_map = {}
    symbols = list(SYMBOL_ALIASES.keys())
    for sym in symbols:
        heads = []
        txt_parts = []
        for rec in articles:
            title = rec.get('title', '')
            desc = rec.get('categories') or rec.get('description') or ''
            if classify_symbol(title, sym):
                heads.append(title[:100])
                txt_parts.append(f"{title} {desc}")
        for title in rss_titles:
            if classify_symbol(title, sym):
                heads.append(title[:100])
                txt_parts.append(title)
        for item in web_items:
            title = item.get('title', '')
            desc = item.get('description', '')
            if classify_symbol(title, sym):
                heads.append(title[:100])
                txt_parts.append(f"{title} {desc}")
        # dedupe
        heads = list(dict.fromkeys(heads))[:8]
        txt = ' '.join(txt_parts[:20])
        sc, label = score_text(txt)
        symbol_map[sym] = {
            'symbol': sym,
            'asof': ts,
            'sentiment': label,
            'score': sc,
            'headlines': heads,
            'headline_count': len(heads),
        }

    out_path.write_text(json.dumps({'generated_at': ts, 'symbols': symbol_map}, indent=2), encoding='utf-8')
    print('WROTE', out_path)
    print('SYMBOLS', len(symbol_map))
    covered = [sym for sym, v in symbol_map.items() if v['headline_count']]
    print('COVERED', len(covered))
    print('SAMPLE', covered[:10])


if __name__ == '__main__':
    main()
