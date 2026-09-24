#!/usr/bin/env python3
"""
Rebuild htf/htf_scan.db htf_news table from workflow/news_ingest_*.jsonl
with better symbol matching and dedupe, then leave row count unchanged.
"""
import json, sqlite3
from pathlib import Path
from datetime import datetime, timezone

FIRM = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm")
WORKFLOW = FIRM / "workflow"
HTF_DB = FIRM / "htf" / "htf_scan.db"
TODAY = datetime.now(timezone.utc).date().isoformat()
MAX_HOURS = 48

# Universe symbol set from htf/universe.py
sys_path = str(FIRM / "htf")
import sys
sys.path.insert(0, sys_path)
import universe as U
UNIVERSE = list(U.UNIVERSE.keys())

# Additional aliases for better matching
ALIASES = {
    '^GSPC': ['s&p 500','sp500','spx'],
    '^IXIC': ['nasdaq','nasdaq composite'],
    '^RUT': ['russell 2000','small cap'],
    '^VIX': ['vix','volatility index','cboe volatility'],
    '^FTSE': ['ftse 100','uk index'],
    '^GDAXI': ['dax','german index'],
    '^N225': ['nikkei','japan index'],
    'BTC-USD': ['bitcoin','btc'],
    'ETH-USD': ['ethereum','eth'],
    'SOL-USD': ['solana','sol'],
    'XRP-USD': ['ripple','xrp'],
    'AVAX-USD': ['avalanche','avax'],
    'LINK-USD': ['chainlink'],
    'ADA-USD': ['cardano','ada'],
    'DOGE-USD': ['dogecoin','doge'],
    'EURUSD=X': ['eur/usd','euro','ecb'],
    'GBPUSD=X': ['gbp/usd','sterling','pound','boe'],
    'USDJPY=X': ['usd/jpy','yen','jpy','boj'],
    'AUDUSD=X': ['aud/usd','aussie','rba'],
    'USDCAD=X': ['usd/cad','loonie','cad','boc'],
    'USDCHF=X': ['usd/chf','franc','chf','snb'],
    'NZDUSD=X': ['nzd/usd','kiwi','nzd','rbnz'],
    'GC=F': ['gold','xau'],
    'SI=F': ['silver','xag'],
    'HG=F': ['copper','base metal'],
    'PL=F': ['platinum'],
    'CL=F': ['crude','wti','oil'],
    'NG=F': ['natural gas'],
    'BZ=F': ['brent'],
    'ES=F': ['spx futures','s&p futures'],
    'NQ=F': ['nq futures','nasdaq futures'],
    'YM=F': ['dow futures'],
    'RTY=F': ['russell futures'],
    'ZN=F': ['10-year yield','treasury note'],
    'ZB=F': ['30-year yield','treasury bond'],
    'TLT': ['long-term treasury etf'],
    'IEF': ['intermediate treasury etf'],
    'HYG': ['high yield','junk bond'],
    'LQD': ['investment grade','corporate bond'],
    'AAPL': ['apple','iphone','mac','ios','airpods','vision pro','tim cook'],
    'MSFT': ['microsoft','windows','azure','office 365','xbox','satya nadella'],
    'NVDA': ['nvidia','gpu','ai chip','cuda','jensen huang','blackwell'],
    'AMD': ['amd','ryzen','epyc','instinct','lisa su'],
    'INTC': ['intel','core','xeon','pat gelsinger'],
    'AVGO': ['broadcom','vmware'],
    'QCOM': ['qualcomm','snapdragon'],
    'TSLA': ['tesla','elon musk','model 3','model y','cybertruck','fsd'],
    'AMZN': ['amazon','aws','prime','e-commerce'],
    'GOOGL': ['google','alphabet','search','youtube','pixel','sundar pichai'],
    'META': ['meta','facebook','instagram','whatsapp','mark zuckerberg','llama'],
    'NFLX': ['netflix','streaming'],
    'DIS': ['disney','marvel','star wars','pixar','bob iger'],
    'JPM': ['jpmorgan','jamie dimon'],
    'BAC': ['bank of america','bofa'],
    'GS': ['goldman sachs','sachs','david solomon'],
    'JNJ': ['johnson','johnson & johnson','jnj'],
    'PFE': ['pfizer','vaccine','albert bourla'],
    'UNH': ['unitedhealth','optum'],
    'LLY': ['eli lilly','insulin','trulicity'],
    'XOM': ['exxon','exxonmobil','darren woods'],
    'CVX': ['chevron'],
    'COP': ['conocophillips','ryan lance'],
    'SLB': ['schlumberger','oilfield'],
    'CAT': ['caterpillar'],
    'GE': ['general electric','ge aerospace'],
    'HON': ['honeywell'],
    'UPS': ['ups','parcel','carol tomé'],
    'KO': ['coca cola','coke','james quincey'],
    'PEP': ['pepsi','pepsico','ramon laguarta'],
    'WMT': ['walmart','douglas mcmillon'],
    'PG': ['procter','p&g'],
    'NEE': ['nextera','renewable'],
    'DUK': ['duke energy'],
    'SO': ['southern company'],
    'VNQ': ['reit','real estate etf'],
    'PLD': ['prologis','warehouse'],
    'AMT': ['american tower','cell tower'],
    'SPY': ['s&p 500 etf','sp500 etf'],
    'QQQ': ['nasdaq 100 etf','invesco qqq'],
    'IWM': ['russell 2000 etf','small cap etf'],
}

POS = ['bullish','upgrade','growth','surge','rally','beat','outperform','strong','gain','soar','breakthrough','record','win','approved']
NEG = ['bearish','downgrade','recession','crash','miss','underperform','weak','drop','decline','plunge','fear','lawsuit','cut','warning']

def score_text(text):
    low=text.lower(); p=sum(low.count(w) for w in POS); n=sum(low.count(w) for w in NEG)
    if p>n: return min(100,50+p*10-n*5),'BULLISH'
    if n>p: return max(0,50-n*10+p*5),'BEARISH'
    return 50,'NEUTRAL'

def load_recent_articles():
    articles=[]
    seen=set()
    for path in sorted(WORKFLOW.glob('news_ingest_*.jsonl')):
        try:
            lines=path.read_text(encoding='utf-8', errors='ignore').splitlines()
        except Exception:
            continue
        for line in lines:
            if not line.strip(): continue
            try: rec=json.loads(line)
            except: continue
            pub=(rec.get('published') or ''); ts=rec.get('ts') or ''
            try: pub_dt=datetime.fromisoformat(pub.replace('Z','+00:00')) if pub else None
            except: pub_dt=None
            try: ts_dt=datetime.fromisoformat(ts.replace('Z','+00:00')) if ts else None
            except: ts_dt=None
            when=pub_dt or ts_dt
            if when is None: continue
            if when.tzinfo is None: when=when.replace(tzinfo=timezone.utc)
            age_h=(datetime.now(timezone.utc)-when).total_seconds()/3600
            if age_h<0 or age_h>MAX_HOURS: continue
            key=rec.get('url') or rec.get('title')
            if not key or key in seen: continue
            seen.add(key); articles.append(rec)
    return articles

def classify_symbol(title, symbol):
    low=title.lower(); sym=symbol.lower()
    if sym in low: return True
    for a in ALIASES.get(symbol, []):
        if a.lower() in low: return True
    return False

def main():
    articles=load_recent_articles()
    # Build mapping
    updates={}
    for sym in UNIVERSE:
        heads=[]; parts=[]
        for rec in articles:
            title=(rec.get('title') or '')
            desc=(rec.get('categories') or rec.get('description') or '')
            if classify_symbol(title, sym):
                heads.append(title[:100]); parts.append(f"{title} {desc}")
        heads=list(dict.fromkeys(heads))[:8]
        txt=' '.join(parts[:20])
        sc,label=score_text(txt)
        updates[sym]=(label, sc, heads)

    # Update DB rows in place
    con=sqlite3.connect(str(HTF_DB)); cur=con.cursor()
    updated=0
    for sym,(label,sc,heads) in updates.items():
        head_str=' | '.join(heads) if heads else ''
        cur.execute('UPDATE htf_news SET sentiment=?, score=?, headlines=? WHERE symbol=? AND asof=?', (label,sc,head_str,sym,TODAY))
        if cur.rowcount:
            updated+=cur.rowcount
    con.commit()
    cur.execute('SELECT count(*), count(DISTINCT symbol), max(asof) FROM htf_news')
    print('summary', cur.fetchone())
    cur.execute('SELECT symbol,sentiment,score,headlines FROM htf_news WHERE headlines!="" ORDER BY asof DESC LIMIT 20')
    rows=cur.fetchall()
    print('nonempty rows', len(rows))
    for r in rows[:10]:
        print(r)
    con.close()
    print('updated rows', updated)

if __name__=='__main__':
    main()
