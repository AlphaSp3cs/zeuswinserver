"""
OuroTaurus Flux — Multi-Sector Intelligence Scan
Live trade-setup scanner across all 6 sectors (Stocks, ETFs, Forex, Crypto, Indices, Commodities).
Pulls real data via yfinance, computes trend/momentum/RSI/ATR, and ranks BUY / SELL setups.
"""
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# ---------------------------------------------------------------- universe
UNIVERSE = {
    "STOCKS (GICS 11)": [
        "XLE","XLF","XLK","XLV","XLI","XLP","XLY","XLB","XLU","XLRE","XLC",
    ],
    "ETFs (STYLE/FACTOR)": [
        "SPY","QQQ","IWM","DIA","VTI","MTUM","QUAL","VLUE","SDY","REMX","COPX","LIT",
    ],
    "FOREX (MAJORS)": [
        "EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","AUDUSD=X","NZDUSD=X","USDCAD=X",
    ],
    "CRYPTO (MAJORS + ALT)": [
        "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD","ADA-USD","AVAX-USD","LINK-USD","DOGE-USD",
    ],
    "INDICES (GLOBAL)": [
        "^GSPC","^NDX","^DJI","^RUT","^GDAXI","^FTSE","^N225","^HSI","^VIX",
    ],
    "COMMODITIES (FUTURES)": [
        "GC=F","SI=F","HG=F","PL=F","PA=F","CL=F","BZ=F","NG=F","ZW=F","ZC=F","ZS=F","HG=F",
    ],
}

# ---------------------------------------------------------------- indicators
def sma(s, n):
    return s.rolling(n).mean()

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = -d.clip(upper=0).rolling(n).mean()
    rs = up / (dn + 1e-9)
    return 100 - 100 / (1 + rs)

def atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def fetch(tickers, period="1y"):
    raw = yf.download(tickers, period=period, interval="1d",
                      auto_adjust=True, progress=False, threads=False)
    # normalize to single or multi index
    if isinstance(raw.columns, pd.MultiIndex):
        out = {}
        for col in ["Open","High","Low","Close","Adj Close","Volume"]:
            if col in raw.columns.get_level_values(0):
                out[col] = raw[col]
        return out
    # single ticker: wrap
    return {"Close": raw["Close"], "High": raw["High"], "Low": raw["Low"],
            "Open": raw["Open"], "Volume": raw.get("Volume")}

def series_for(data, col, t):
    if isinstance(data[col], pd.DataFrame):
        return data[col][t]
    return data[col]

# ---------------------------------------------------------------- setup logic
def score_setup(row):
    """Return (signal, strength 0-100, note)."""
    close = row["close"]; r = row["ret20"]; r60 = row["ret60"]
    sma50 = row["sma50"]; sma200 = row["sma200"]; rs = row["rsi"]
    above50 = close > sma50; above200 = close > sma200
    trend_up = above50 and (sma50 >= sma200)
    trend_dn = (close < sma50) and (sma50 <= sma200)

    buy_pts, sell_pts = 0.0, 0.0
    notes = []

    # --- momentum
    if r > 0: buy_pts += min(r/0.10, 1.0)*15
    else:    sell_pts += min(-r/0.10, 1.0)*15
    if r60 > 0: buy_pts += 10
    else:       sell_pts += 10

    # --- trend
    if trend_up:  buy_pts += 25; notes.append("uptrend")
    if trend_dn:  sell_pts += 25; notes.append("downtrend")

    # --- RSI
    if 45 <= rs <= 65: buy_pts += 15; notes.append("RSI healthy")
    elif rs < 40 and trend_up: buy_pts += 12; notes.append("pullback in uptrend")
    elif rs > 70: sell_pts += 18; notes.append("overbought")
    elif 65 < rs <= 70: sell_pts += 6
    elif rs < 30: sell_pts += 8; notes.append("oversold")

    # --- pullback-to-MA buy zone
    if above200 and close < sma50*1.0 and r < 0 and r60 > 0:
        buy_pts += 10; notes.append("pullback-to-MA")

    if buy_pts >= sell_pts and buy_pts >= 30:
        return "BUY", round(min(buy_pts, 100), 1), ", ".join(notes)
    if sell_pts > buy_pts and sell_pts >= 30:
        return "SELL", round(min(sell_pts, 100), 1), ", ".join(notes)
    return "HOLD", round(max(buy_pts, sell_pts), 1), ", ".join(notes)

# ---------------------------------------------------------------- main
def analyze():
    results = {}
    for sector, ticks in UNIVERSE.items():
        recs = []
        try:
            data = fetch(ticks, period="1y")
        except Exception as e:
            results[sector] = {"error": str(e), "rows": []}
            continue
        closes = data["Close"]
        highs = data.get("High"); lows = data.get("Low")
        if not isinstance(closes, pd.DataFrame):
            closes = pd.DataFrame({ticks[0]: closes})
        for t in ticks:
            try:
                c = closes[t].dropna()
                if len(c) < 60:
                    continue
                h = lows_ = None
                if isinstance(highs, pd.DataFrame) and t in highs:
                    h = highs[t].reindex(c.index)
                    lows_ = lows[t].reindex(c.index)
                close = float(c.iloc[-1])
                ret20 = float(c.iloc[-1]/c.iloc[-21]-1) if len(c) > 21 else float("nan")
                ret60 = float(c.iloc[-1]/c.iloc[-61]-1) if len(c) > 61 else float("nan")
                s50 = float(sma(c,50).iloc[-1]); s200 = float(sma(c,200).iloc[-1]) if len(c)>=200 else float("nan")
                rs = float(rsi(c,14).iloc[-1])
                hi52 = float(c.max()); lo52 = float(c.min())
                dist_hi = (close/hi52-1); dist_lo = (close/lo52-1)
                vol = float(c.pct_change().std()*np.sqrt(252)) if len(c)>2 else float("nan")
                # ATR% proxy via vol if no HL
                atrp = vol
                if h is not None and lows_ is not None:
                    a = atr(h, lows_, c, 14).iloc[-1]
                    atrp = float(a/close)
                rec = dict(t=t, close=close, ret20=ret20, ret60=ret60,
                           sma50=s50, sma200=s200, rsi=rs,
                           dist_hi=dist_hi, dist_lo=dist_lo, atr=atrp)
                sig, strength, note = score_setup(rec)
                rec.update(signal=sig, strength=strength, note=note)
                recs.append(rec)
            except Exception as e:
                continue
        results[sector] = {"rows": recs}
    return results

def fmt_pct(x):
    if x != x: return "  n/a"
    return f"{x*100:+6.2f}%"

def pct(x, w=7):
    if x != x: return "   n/a "
    return f"{x*100:+{w-1}.1f}%"

def main():
    print("=" * 104)
    print("OUROTAURUS FLUX — MULTI-SECTOR INTELLIGENCE SCAN  (live yfinance)")
    print("Generated:", datetime.now().strftime("%Y-%m-%d %H:%M ET"))
    print("=" * 104)
    R = analyze()
    grand_buys, grand_sells = [], []
    for sector, blk in R.items():
        print(f"\n{'='*104}\n{sector}\n{'='*104}")
        if "error" in blk:
            print("  DATA ERROR:", blk["error"]); continue
        rows = blk["rows"]
        if not rows:
            print("  (no data)"); continue
        rows.sort(key=lambda r: r["strength"], reverse=True)
        # breadth
        adv = sum(1 for r in rows if r["ret20"]>0)
        dec = len(rows)-adv
        buys = [r for r in rows if r["signal"]=="BUY"]
        sells = [r for r in rows if r["signal"]=="SELL"]
        print(f"  Breadth: {adv} up / {dec} down  |  BUY setups: {len(buys)}  SELL setups: {len(sells)}")
        print(f"  {'TICKER':<12}{'PRICE':>11}{'20D':>9}{'60D':>9}{'RSI':>7}{'vsSMA50':>9}{'vsSMA200':>10}{'ATR%':>8}{'SIG':>6}{'STR':>6}")
        print("  " + "-"*95)
        for r in rows:
            vs50 = (r['close']/r['sma50']-1) if r['sma50']==r['sma50'] else float('nan')
            vs200 = (r['close']/r['sma200']-1) if (r['sma200']==r['sma200']) else float('nan')
            price = f"{r['close']:>11.3f}" if r['close']<1000 else f"{r['close']:>11.1f}"
            print(f"  {r['t']:<12}{price}{pct(r['ret20'])}{pct(r['ret60'])}{r['rsi']:>7.1f}"
                  f"{pct(vs50)}{pct(vs200)}{pct(r['atr'],7)}{r['signal']:>6}{r['strength']:>6.0f}")
        # top setups
        if buys:
            b = buys[0]
            print(f"  >> TOP BUY : {b['t']} @ {b['close']:.3f}  strength {b['strength']:.0f}  [{b['note']}]")
            grand_buys.extend(buys)
        if sells:
            s = sells[0]
            print(f"  >> TOP SELL: {s['t']} @ {s['close']:.3f}  strength {s['strength']:.0f}  [{s['note']}]")
            grand_sells.extend(sells)
    # -------------------------------------------------- consolidated
    print("\n" + "="*104)
    print("CONSOLIDATED — TOP 12 BUY SETUPS (by strength)")
    print("="*104)
    for r in sorted(grand_buys, key=lambda r: r['strength'], reverse=True)[:12]:
        print(f"  {r['t']:<12} @ {r['close']:<11.3f}  str {r['strength']:>5.0f}  20D {pct(r['ret20'])}  RSI {r['rsi']:>5.1f}  [{r['note']}]")
    print("\n" + "="*104)
    print("CONSOLIDATED — TOP 12 SELL SETUPS (by strength)")
    print("="*104)
    for r in sorted(grand_sells, key=lambda r: r['strength'], reverse=True)[:12]:
        print(f"  {r['t']:<12} @ {r['close']:<11.3f}  str {r['strength']:>5.0f}  20D {pct(r['ret20'])}  RSI {r['rsi']:>5.1f}  [{r['note']}]")
    print("\n" + "="*104)
    print("DISCLAIMER: Scan is mechanical/swing-oriented, not financial advice. Verify SL/TP")
    print("per charter (risk <=2%/trade, <=8%/port). Advance winners: trail to BE at +2%.")
    print("="*104)

if __name__ == "__main__":
    main()
