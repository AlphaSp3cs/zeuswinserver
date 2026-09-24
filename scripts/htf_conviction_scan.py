#!/usr/bin/env python3
"""
HTF CONVICTION SCAN — all-sector, high-time-frame, fundamentals + news + backtest.

Pipeline:
  1. Pull 1y daily history (yfinance) for a full cross-asset universe (crypto, equity
     sectors, commodities, forex, indices).
  2. Compute TRUE high-time-frame RSI: daily RSI(14), weekly RSI(14) [resampled],
     monthly RSI(14) [resampled]. Flag overbought (weekly>65 / monthly>60) and
     oversold (weekly<35 / monthly<40) regimes.
  3. Fundamentals (equities via fast_info: mktcap, PE, fwdPE, peg, margin, rev growth,
     earnings growth, debt/equity, div yield; crypto via CoinGecko mcap/vol/24h).
  4. News sentiment: parse live RSS (rss_news_latest.json) with a lexicon + source
     credibility model, map to symbols/sectors, align with trade direction.
  5. Backtest: weekly-RSI mean-reversion (long<35 exit>50; short>65 exit<50) over the
     1y daily series -> win rate, expectancy (R), avg win/loss, trade count.
  6. Conviction blend (HTF 30% + backtest 30% + fundamentals 20% + news 20%) -> ranked
     longs & shorts with full setup (entry, SL, TP, RR) and broker route suggestion.
  7. Emit JSON + Markdown + CSV execution plan into scans/all_sector/.

No orders are placed. This is a read-only analytical scan.
"""
import sqlite3, json, math, re, time, os, sys, warnings, datetime as dt
from pathlib import Path
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

FIRM = Path(r"C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm")
RSS_PATH = FIRM / "artifacts" / "rss_news" / "rss_news_latest.json"
OUT_DIR = FIRM / "scans" / "all_sector"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = FIRM / "data" / "daily"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

NOW = dt.datetime.now(dt.timezone.utc)

# ---------------------------------------------------------------------------
# UNIVERSE  (symbol -> (yf_symbol, sector, asset_class))
# ---------------------------------------------------------------------------
UNIVERSE = {}
def add(yf_sym, sector, cls, key=None):
    UNIVERSE[key or yf_sym] = (yf_sym, sector, cls)

# Crypto
CRYPTO = ["BTC-USD","ETH-USD","SOL-USD","XRP-USD","ADA-USD","AVAX-USD","LINK-USD",
          "DOGE-USD","DOT-USD","MATIC-USD","LTC-USD","ATOM-USD","UNI-USD","AAVE-USD",
          "NEAR-USD","APT-USD","SUI-USD","RNDR-USD","FET-USD","ICP-USD","ARB-USD",
          "OP-USD","INJ-USD","TIA-USD","HBAR-USD","TRX-USD","ALGO-USD","XLM-USD","FIL-USD","ETC-USD"]
for s in CRYPTO:
    add(s, "Crypto", "crypto", key=s.replace("-USD",""))

# Equity sectors (sector ETF + flagships)
EQUITY = {
    "Technology": ["XLK","AAPL","MSFT","NVDA","AVGO"],
    "Healthcare": ["XLV","JNJ","LLY","PFE"],
    "Financials": ["XLF","JPM","BAC","GS"],
    "Consumer_Discretionary": ["XLY","AMZN","TSLA","HD"],
    "Consumer_Staples": ["XLP","PG","KO","COST"],
    "Energy": ["XLE","XOM","CVX"],
    "Industrials": ["XLI","HON","CAT"],
    "Materials": ["XLB","LIN","FCX"],
    "Real_Estate": ["XLRE","AMT","PLD"],
    "Utilities": ["XLU","NEE"],
    "Communication": ["XLC","GOOGL","META","NFLX"],
}
for sec, syms in EQUITY.items():
    for s in syms:
        add(s, sec, "equity")

# Commodities
for s, sec in [("GLD","Metals"),("SLV","Metals"),("USO","Energy_Commodity"),
               ("UNG","Energy_Commodity"),("HG=F","Metals")]:
    add(s, sec, "commodity")

# Forex
for s in ["EURUSD=X","GBPUSD=X","USDJPY=X","USDCAD=X","AUDUSD=X"]:
    add(s, "Forex", "forex", key=s.replace("=X",""))

# Indices
for s, sec in [("SPY","Indices"),("QQQ","Indices"),("IWM","Indices"),("DIA","Indices")]:
    add(s, sec, "index")

# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------
def rsi(series: pd.Series, n=14) -> pd.Series:
    series = series.astype(float).dropna()
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.fillna(50)
    return out

def wma(price, n=200):
    return price.rolling(n).mean()

# ---------------------------------------------------------------------------
# DATA FETCH
# ---------------------------------------------------------------------------
def close_series(yf_sym):
    """Return a daily Close Series (1y) with caching."""
    cache = CACHE_DIR / (re.sub(r"[^A-Za-z0-9]", "_", yf_sym) + ".csv")
    if cache.exists():
        try:
            df = pd.read_csv(cache, index_col=0, parse_dates=True)
            if len(df) > 50:
                return df["close"]
        except Exception:
            pass
    try:
        df = yf.download(yf_sym, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) == 0:
            return None
        # yfinance 1.5.2 may return a MultiIndex (field, ticker)
        if isinstance(df.columns, pd.MultiIndex):
            close = df[("Close", yf_sym)] if (("Close", yf_sym) in df.columns) else df.xs("Close", axis=1, level=0).iloc[:,0]
        else:
            close = df["Close"]
        close = close.dropna()
        if len(close) < 50:
            return None
        close.to_frame("close").to_csv(cache)
        return close
    except Exception as e:
        sys.stderr.write(f"  ! {yf_sym} fetch err: {str(e)[:80]}\n")
        return None

def crypto_fundamentals():
    out = {}
    try:
        import urllib.request
        ids = {"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","XRP":"ripple","ADA":"cardano",
               "AVAX":"avalanche-2","LINK":"chainlink","DOGE":"dogecoin","DOT":"polkadot",
               "MATIC":"matic-network","LTC":"litecoin","ATOM":"cosmos","UNI":"uniswap",
               "AAVE":"aave","NEAR":"near","APT":"aptos","SUI":"sui","RNDR":"render-token",
               "FET":"fetch-ai","ICP":"internet-computer","ARB":"arbitrum","OP":"optimism",
               "INJ":"injective","TIA":"celestia","HBAR":"hedera-hashgraph","TRX":"tron",
               "ALGO":"algorand","XLM":"stellar","FIL":"filecoin","ETC":"ethereum-classic"}
        url = ("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids="
               + ",".join(ids.values()) + "&order=market_cap_desc&per_page=100&page=1&sparkline=false")
        req = urllib.request.Request(url, headers={"User-Agent":"htf-scan/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        for d in data:
            sym = next((k for k,v in ids.items() if v==d["id"]), None)
            if sym:
                out[sym] = {
                    "market_cap": d.get("market_cap") or 0,
                    "volume": d.get("total_volume") or 0,
                    "change_24h": d.get("price_change_percentage_24h") or 0,
                    "price": d.get("current_price") or 0,
                }
    except Exception as e:
        sys.stderr.write(f"  ! coingecko err: {str(e)[:80]}\n")
    return out

def equity_fundamentals(yf_syms):
    out = {}
    for yf_sym in yf_syms:
        try:
            t = yf.Ticker(yf_sym)
            fi = t.fast_info
            rec = {
                "market_cap": float(getattr(fi, "market_cap", None) or 0),
                "trailing_pe": float(getattr(fi, "trailing_pe", None) or 0),
                "forward_pe": float(getattr(fi, "forward_pe", None) or 0),
                "dividend_yield": float(getattr(fi, "dividend_yield", None) or 0),
            }
        except Exception:
            rec = {"market_cap":0,"trailing_pe":0,"forward_pe":0,"dividend_yield":0}
        # enrich with growth/margins via get_info (best-effort, single field reads)
        try:
            info = yf.Ticker(yf_sym).get_info()
            rec["peg"] = float(info.get("pegRatio") or 0)
            rec["profit_margin"] = float(info.get("profitMargins") or 0)
            rec["revenue_growth"] = float(info.get("revenueGrowth") or 0)
            rec["earnings_growth"] = float(info.get("earningsGrowth") or 0)
            rec["debt_to_equity"] = float(info.get("debtToEquity") or 0)
            rec["sector"] = info.get("sector")
            rec["short_percent"] = float(info.get("shortPercentOfFloat") or 0)
        except Exception:
            rec.update({"peg":0,"profit_margin":0,"revenue_growth":0,"earnings_growth":0,"debt_to_equity":0,"sector":None,"short_percent":0})
        out[yf_sym] = rec
    return out

# ---------------------------------------------------------------------------
# NEWS SENTIMENT
# ---------------------------------------------------------------------------
POS = ["rally","surge","gain","gains","beat","beats","soar","soars","jump","jumps","rise","rises",
       "bullish","upgrade","upgrades","record","profit","profits","growth","strong","higher","rises",
       "approved","approval","partnership","adoption","inflow","inflows","buyback","outperform","win","wins"]
NEG = ["slump","plunge","drop","drops","fall","falls","crash","miss","misses","loss","losses","bearish",
       "downgrade","downgrades","selloff","sell-off","weak","lower","decline","declines","lawsuit","probe",
       "hack","hacked","fraud","ban","bans","outflow","outflows","default","recession","cut","cuts","warn","warning"]
def lexicon_score(text):
    t = (text or "").lower()
    pos = sum(t.count(w) for w in POS)
    neg = sum(t.count(w) for w in NEG)
    total = pos + neg
    if total == 0:
        return 0.0, 0.0  # score, strength
    return (pos - neg) / total, min(1.0, total / 4.0)

# Asset keyword map for news routing
NEWS_KEYS = {
    "BTC":["bitcoin","btc"], "ETH":["ethereum","eth "], "SOL":["solana"], "XRP":["ripple","xrp"],
    "ADA":["cardano"], "AVAX":["avalanche"], "DOGE":["dogecoin","doge"], "LINK":["chainlink"],
    "AAPL":["apple"], "MSFT":["microsoft"], "NVDA":["nvidia"], "AVGO":["broadcom"], "AMZN":["amazon"],
    "TSLA":["tesla"], "GOOGL":["google","alphabet"], "META":["meta","facebook"], "NFLX":["netflix"],
    "JPM":["jpmorgan","j.p. morgan"], "BAC":["bank of america"], "GS":["goldman"], "JNJ":["johnson & johnson"],
    "LLY":["eli lilly","lilly"], "PFE":["pfizer"], "XOM":["exxon"], "CVX":["chevron"], "HD":["home depot"],
    "PG":["procter"], "KO":["coca-cola","coke"], "COST":["costco"], "HON":["honeywell"], "CAT":["caterpillar"],
    "LIN":["linde"], "FCX":["freeport"], "AMT":["ametek","american tower"], "NEE":["nextEra"], "GLD":["gold"],
    "SLV":["silver"], "USO":["oil"], "UNG":["natural gas","gas"], "XLK":["tech","technology"], "XLE":["energy sector"],
    "XLV":["healthcare"], "XLF":["financials","banks"], "XLY":["consumer discretionary"], "XLP":["staples"],
    "XLI":["industrials"], "XLB":["materials"], "XLRE":["real estate"], "XLU":["utilities"], "XLC":["communication"],
    "SPY":["s&p","sp500","stocks"], "QQQ":["nasdaq"], "EURUSD":["euro","eur/usd"], "USDJPY":["yen","usd/jpy"],
}
SECTOR_OF = {k: v[1] for k, v in UNIVERSE.items()}

def load_news():
    sentiments = {}  # symbol -> list of (score, strength, cred, src)
    freshness_hours = None
    if not RSS_PATH.exists():
        return sentiments, None
    try:
        d = json.loads(RSS_PATH.read_text(encoding="utf-8"))
        ts = d.get("timestamp_utc") or d.get("updated_utc")
        if ts:
            try:
                t = dt.datetime.fromisoformat(ts.replace("Z","+00:00"))
                freshness_hours = (NOW - t).total_seconds()/3600
            except Exception:
                pass
        items = d.get("items", [])
        for it in items:
            text = (it.get("title","") + " " + it.get("summary","")).lower()
            src = (it.get("source") or "").lower()
            # source credibility proxy
            cred = 0.85 if any(w in src for w in ["reuters","bloomberg","cnbc","wsj","ft","marketwatch","coindesk","cointelegraph","ap "]) else 0.6
            sc, strength = lexicon_score(text)
            if sc == 0:
                continue
            for sym, keys in NEWS_KEYS.items():
                if any(k in text for k in keys):
                    sentiments.setdefault(sym, []).append((sc, strength, cred, src))
    except Exception as e:
        sys.stderr.write(f"  ! news parse err: {str(e)[:80]}\n")
    return sentiments, freshness_hours

def news_for_symbol(sym, sentiments):
    recs = sentiments.get(sym, [])
    if not recs:
        return 0.0, 0, None
    # weighted by strength*cred
    num = sum(sc*strength*cred for sc,strength,cred,_ in recs)
    den = sum(strength*cred for _,strength,cred,_ in recs)
    score = num/den if den else 0.0
    return round(score,3), len(recs), recs[0][3]

# ---------------------------------------------------------------------------
# BACKTEST  (weekly-RSI mean reversion)
# ---------------------------------------------------------------------------
def backtest(daily_close, weekly_rsi, monthly_rsi, direction):
    """Position from HTF RSI; P&L on daily closes. Returns dict of stats."""
    # align weekly rsi to daily index
    wr = weekly_rsi.reindex(daily_close.index).ffill()
    mr = monthly_rsi.reindex(daily_close.index).ffill()
    pos = pd.Series(0, index=daily_close.index)
    if direction == "LONG":
        pos = ((wr < 35) & (mr < 55)).astype(int)
        exit_mask = (wr > 50)
    else:
        pos = ((wr > 65) & (mr > 45)).astype(int)
        exit_mask = (wr < 50)
    # close position on exit
    pos = pos.where(~exit_mask, 0)
    ret = daily_close.pct_change().fillna(0)
    strat = pos.shift(1) * ret  # enter next day
    # trade runs
    trades = []
    in_pos = False; entry_idx = None; cum = 0.0
    for i in range(len(pos)):
        p = pos.iloc[i]
        if not in_pos and p != 0:
            in_pos = True; entry_idx = i; cum = 0.0
        if in_pos:
            cum += strat.iloc[i]
            if p == 0 or i == len(pos)-1:
                trades.append(cum)
                in_pos = False
    if not trades:
        return {"trades":0,"win_rate":0,"expectancy":0,"avg_win":0,"avg_loss":0,"profit_factor":0}
    wins = [t for t in trades if t > 0]
    loss = [t for t in trades if t <= 0]
    wr = len(wins)/len(trades)
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(loss) if loss else 0
    exp = np.mean(trades)
    pf = (sum(wins)/abs(sum(loss))) if loss and sum(loss)!=0 else (9.9 if wins else 0)
    return {"trades":len(trades),"win_rate":round(wr,3),"expectancy":round(exp,4),
            "avg_win":round(avg_win,4),"avg_loss":round(avg_loss,4),"profit_factor":round(pf,2)}

# ---------------------------------------------------------------------------
# CONVICTION
# ---------------------------------------------------------------------------
def fundamental_score(fund, cls):
    if cls != "equity":
        return None  # not applicable
    pe = fund.get("trailing_pe",0) or 0
    fpe = fund.get("forward_pe",0) or 0
    peg = fund.get("peg",0) or 0
    margin = fund.get("profit_margin",0) or 0
    rg = fund.get("revenue_growth",0) or 0
    eg = fund.get("earnings_growth",0) or 0
    de = fund.get("debt_to_equity",0) or 0
    score = 50.0
    # valuation: lower PE good (cap 40)
    if 0 < pe <= 15: score += 15
    elif 15 < pe <= 25: score += 8
    elif 25 < pe <= 40: score += 2
    elif pe > 40: score -= 10
    if 0 < peg <= 1: score += 10
    elif 1 < peg <= 2: score += 4
    elif peg > 2: score -= 6
    score += max(-10, min(15, margin*100/2))   # margin %
    score += max(-10, min(10, rg*100/2))       # revenue growth
    score += max(-10, min(10, eg*100/2))       # earnings growth
    if de > 200: score -= 8
    elif de > 150: score -= 4
    return max(0, min(100, score))

def blend(direction, htf, bt, fund_score, news_score, cls):
    # htf: 0-100 extremity; bt: expectancy-based 0-100; fund: 0-100 or None; news: -1..1
    # backtest score from expectancy
    bt_score = max(0, min(100, 50 + bt["expectancy"]*600))  # exp 0.05->80, 0.08->98
    bt_score = bt_score * (1 if bt["trades"] >= 3 else 0.6)  # discount thin samples
    news_align = 0.0
    if news_score is not None:
        # align: long wants positive news, short wants negative
        target = 1 if direction=="LONG" else -1
        news_align = news_score * target  # -1..1
    news_0_100 = (news_align + 1) / 2 * 100  # 0..100
    if fund_score is None:
        # redistribute: htf 35, bt 35, news 30
        w = {"htf":0.35,"bt":0.35,"news":0.30}
        conv = w["htf"]*htf + w["bt"]*bt_score + w["news"]*news_0_100
    else:
        w = {"htf":0.30,"bt":0.30,"fund":0.20,"news":0.20}
        conv = w["htf"]*htf + w["bt"]*bt_score + w["fund"]*fund_score + w["news"]*news_0_100
    return round(conv,1), round(bt_score,1)

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    print(f"HTF CONVICTION SCAN — {NOW.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Universe: {len(UNIVERSE)} symbols across all sectors")
    print("Fetching crypto fundamentals (CoinGecko) ...")
    cf = crypto_fundamentals()
    print(f"  got {len(cf)} crypto fundamentals")
    print("Loading news sentiment ...")
    sentiments, fresh = load_news()
    print(f"  news items mapped to {len(sentiments)} symbols"
          + (f" (RSS age {fresh:.1f}h)" if fresh else ""))

    eq_syms = [v[0] for v in UNIVERSE.values() if v[2]=="equity"]
    eqf_cache = CACHE_DIR / "equity_fundamentals.json"
    if eqf_cache.exists() and (NOW.timestamp() - eqf_cache.stat().st_mtime) < 86400:
        try:
            eqf = json.loads(eqf_cache.read_text())
            print(f"Loaded cached equity fundamentals for {len(eqf)} names")
        except Exception:
            eqf = {}
    else:
        eqf = {}
    if not eqf:
        print(f"Fetching equity fundamentals for {len(eq_syms)} names ...")
        eqf = equity_fundamentals(eq_syms)
        try:
            eqf_cache.write_text(json.dumps(eqf, default=str))
        except Exception:
            pass

    rows = []
    failed = []
    for sym, (yf_sym, sector, cls) in UNIVERSE.items():
        c = close_series(yf_sym)
        if c is None or len(c) < 60:
            failed.append(sym); continue
        daily_rsi = rsi(c, 14)
        wk = c.resample("W-FRI").last().dropna()
        wk_rsi = rsi(wk, 14)
        mo = c.resample("ME").last().dropna()
        mo_rsi = rsi(mo, 14)
        last = float(c.iloc[-1])
        d_rsi = float(daily_rsi.iloc[-1])
        w_rsi = float(wk_rsi.reindex(c.index).ffill().iloc[-1])
        m_rsi = float(mo_rsi.reindex(c.index).ffill().iloc[-1])
        sma200 = float(wma(c,200).iloc[-1]) if len(c)>=200 else float(c.mean())
        above_200 = last > sma200

        fund = eqf.get(yf_sym, {}) if cls=="equity" else cf.get(sym, {}) if cls=="crypto" else {}
        fscore = fundamental_score(fund, cls) if cls=="equity" else None
        nscore, ncount, nsrc = news_for_symbol(sym, sentiments)

        # HTF extremity -> 0..100
        if w_rsi < 50:
            htf_long = max(0, min(100, (50 - w_rsi)/50*100))
        else:
            htf_long = 0.0
        if w_rsi > 50:
            htf_short = max(0, min(100, (w_rsi - 50)/50*100))
        else:
            htf_short = 0.0
        # monthly adds
        if m_rsi < 50: htf_long = max(htf_long, (50-m_rsi)/50*100*0.8)
        if m_rsi > 50: htf_short = max(htf_short, (m_rsi-50)/50*100*0.8)
        htf_long = round(min(100,htf_long),1); htf_short = round(min(100,htf_short),1)

        bt_long = backtest(c, wk_rsi, mo_rsi, "LONG")
        bt_short = backtest(c, wk_rsi, mo_rsi, "SHORT")

        # qualify
        long_ok = (w_rsi < 38 or m_rsi < 42) and above_200
        short_ok = (w_rsi > 62 or m_rsi > 58) and (not above_200 or d_rsi>55)

        if long_ok:
            conv, bts = blend("LONG", htf_long, bt_long, fscore, nscore, cls)
            sl = round(min(last*0.94, float(c.tail(20).min())*0.99), 4)
            risk = last - sl
            if risk <= 0: risk = last*0.04
            rr = lambda mult: round(last + risk*mult, 4)
            rows.append({
                "direction":"LONG","symbol":sym,"yf":yf_sym,"sector":sector,"class":cls,
                "price":round(last,4),"sma200":round(sma200,4),"above_200":above_200,
                "daily_rsi":round(d_rsi,1),"weekly_rsi":round(w_rsi,1),"monthly_rsi":round(m_rsi,1),
                "htf_score":htf_long,"fund_score":fscore,"news_score":nscore,"news_count":ncount,
                "backtest":bt_long,"bt_score":bts,
                "conviction":conv,
                "entry":round(last,4),
                "sl":sl,"sl_pct":round((last-sl)/last*100,2),
                "tp1":rr(1.0),"tp2":rr(2.0),"tp3":rr(3.0),
                "rr_t2":2.0,
                "market_cap":fund.get("market_cap",0),
                "volume":fund.get("volume",0),
            })
        if short_ok:
            conv, bts = blend("SHORT", htf_short, bt_short, fscore, nscore, cls)
            sl = round(max(last*1.06, float(c.tail(20).max())*1.01), 4)
            risk = sl - last
            if risk <= 0: risk = last*0.04
            rr = lambda mult: round(last - risk*mult, 4)
            rows.append({
                "direction":"SHORT","symbol":sym,"yf":yf_sym,"sector":sector,"class":cls,
                "price":round(last,4),"sma200":round(sma200,4),"above_200":above_200,
                "daily_rsi":round(d_rsi,1),"weekly_rsi":round(w_rsi,1),"monthly_rsi":round(m_rsi,1),
                "htf_score":htf_short,"fund_score":fscore,"news_score":nscore,"news_count":ncount,
                "backtest":bt_short,"bt_score":bts,
                "conviction":conv,
                "entry":round(last,4),
                "sl":sl,"sl_pct":round((sl-last)/last*100,2),
                "tp1":rr(1.0),"tp2":rr(2.0),"tp3":rr(3.0),
                "rr_t2":2.0,
                "market_cap":fund.get("market_cap",0),
                "volume":fund.get("volume",0),
            })
        if (len(rows) % 10) == 0:
            sys.stderr.write(f"  ...processed {len(rows)} setups, {len(UNIVERSE)-len(rows)-len(failed)} left\n")

    elapsed = time.time()-t0
    longs = sorted([r for r in rows if r["direction"]=="LONG"], key=lambda x:-x["conviction"])
    shorts = sorted([r for r in rows if r["direction"]=="SHORT"], key=lambda x:-x["conviction"])

    print(f"\n=== SCAN COMPLETE in {elapsed:.1f}s | setups: {len(rows)} "
          f"(LONG {len(longs)} / SHORT {len(shorts)}) | failed_fetch: {len(failed)} ===")
    if failed:
        print("  no-data symbols:", ", ".join(failed[:20]))

    # ---- OUTPUT ----
    ts = NOW.strftime("%Y%m%d_%H%M")
    result = {
        "scan_metadata":{
            "timestamp": NOW.isoformat(),
            "scanner":"htf_conviction_scan v1.0",
            "universe_size": len(UNIVERSE),
            "data_source":"yfinance 1y daily + coingecko + rss_news_latest.json",
            "htf_def":"weekly RSI(14) resampled W-FRI, monthly RSI(14) resampled ME",
            "news_age_hours": round(fresh,1) if fresh else None,
            "failed_symbols": failed,
            "elapsed_seconds": round(elapsed,1),
        },
        "qualified_longs": longs,
        "qualified_shorts": shorts,
        "all_sector_coverage": sorted(set(v[1] for v in UNIVERSE.values())),
    }
    (OUT_DIR / f"htf_conviction_{ts}.json").write_text(json.dumps(result, indent=2, default=str))

    # Markdown
    md = [f"# HTF CONVICTION SCAN — {NOW.strftime('%Y-%m-%d %H:%M UTC')}",
          f"**Universe:** {len(UNIVERSE)} symbols · **Setups:** {len(rows)} "
          f"(LONG {len(longs)} / SHORT {len(shorts)})",
          f"**HTF:** weekly & monthly RSI(14) · **News:** rss_news_latest.json "
          f"(age {round(fresh,1) if fresh else '?'}h) · **Backtest:** 1y weekly-RSI mean-reversion",
          "",
          "## TOP CONVICTION LONGS (oversold HTF)",
          "| # | Sym | Sector | Conv | WkRSI | MoRSI | DlyRSI | Price | SL% | TP2 | BTwin% | BTexp | News |",
          "|---|-----|--------|------|-------|-------|--------|-------|-----|-----|--------|-------|------|"]
    for i,r in enumerate(longs[:25],1):
        md.append(f"| {i} | {r['symbol']} | {r['sector']} | **{r['conviction']}** | {r['weekly_rsi']} | "
                  f"{r['monthly_rsi']} | {r['daily_rsi']} | {r['price']} | {r['sl_pct']} | {r['tp2']} | "
                  f"{round(r['backtest']['win_rate']*100,1)} | {r['backtest']['expectancy']} | "
                  f"{r['news_score']} ({r['news_count']}) |")
    md += ["", "## TOP CONVICTION SHORTS (overbought HTF)",
          "| # | Sym | Sector | Conv | WkRSI | MoRSI | DlyRSI | Price | SL% | TP2 | BTwin% | BTexp | News |",
          "|---|-----|--------|------|-------|-------|--------|-------|-----|-----|--------|-------|------|"]
    for i,r in enumerate(shorts[:25],1):
        md.append(f"| {i} | {r['symbol']} | {r['sector']} | **{r['conviction']}** | {r['weekly_rsi']} | "
                  f"{r['monthly_rsi']} | {r['daily_rsi']} | {r['price']} | {r['sl_pct']} | {r['tp2']} | "
                  f"{round(r['backtest']['win_rate']*100,1)} | {r['backtest']['expectancy']} | "
                  f"{r['news_score']} ({r['news_count']}) |")
    md += ["", "## PER-SECTOR COVERAGE",
          "| Sector | Setups |", "|--------|--------|"]
    sec_counts = {}
    for r in rows: sec_counts[r["sector"]] = sec_counts.get(r["sector"],0)+1
    for sec in sorted(result["all_sector_coverage"]):
        md.append(f"| {sec} | {sec_counts.get(sec,0)} |")
    (OUT_DIR / f"htf_conviction_{ts}.md").write_text("\n".join(md))

    # CSV execution plan (standard scan format)
    import csv
    csvp = OUT_DIR / f"htf_conviction_plan_{ts}.csv"
    with open(csvp,"w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["direction","symbol","sector","class","conviction","entry","sl","sl_pct",
                    "tp1","tp2","tp3","rr_t2","weekly_rsi","monthly_rsi","daily_rsi","backtest_winrate",
                    "backtest_expectancy","backtest_trades","fund_score","news_score","news_count",
                    "market_cap","backtested","executable","broker_route"])
        for r in longs+shorts:
            w.writerow([r["direction"],r["symbol"],r["sector"],r["class"],r["conviction"],r["entry"],
                        r["sl"],r["sl_pct"],r["tp1"],r["tp2"],r["tp3"],r["rr_t2"],r["weekly_rsi"],
                        r["monthly_rsi"],r["daily_rsi"],round(r["backtest"]["win_rate"]*100,1),
                        r["backtest"]["expectancy"],r["backtest"]["trades"],r["fund_score"],
                        r["news_score"],r["news_count"],r["market_cap"],"YES","REVIEW",
                        "kraken" if r["class"]=="crypto" else "ibkr" if r["class"] in ("equity","index","commodity") else "fx"])
    print(f"\nArtifacts:")
    print(f"  JSON: {OUT_DIR / ('htf_conviction_'+ts+'.json')}")
    print(f"  MD:   {OUT_DIR / ('htf_conviction_'+ts+'.md')}")
    print(f"  CSV:  {csvp}")

    # Top-5 quick print
    print("\n=== TOP 5 LONGS ===")
    for r in longs[:5]:
        print(f"  {r['symbol']:6} conv={r['conviction']:5}  WkRSI={r['weekly_rsi']} MoRSI={r['monthly_rsi']} "
              f"  BTwin={round(r['backtest']['win_rate']*100,1)}% exp={r['backtest']['expectancy']} "
              f"  news={r['news_score']}({r['news_count']})  entry={r['entry']} sl={r['sl']} tp2={r['tp2']}")
    print("=== TOP 5 SHORTS ===")
    for r in shorts[:5]:
        print(f"  {r['symbol']:6} conv={r['conviction']:5}  WkRSI={r['weekly_rsi']} MoRSI={r['monthly_rsi']} "
              f"  BTwin={round(r['backtest']['win_rate']*100,1)}% exp={r['backtest']['expectancy']} "
              f"  news={r['news_score']}({r['news_count']})  entry={r['entry']} sl={r['sl']} tp2={r['tp2']}")

if __name__ == "__main__":
    main()
