#!/usr/bin/env python3
"""
Pre-Market Dayshift All-Sector Scan - 08:14 AM ET 2026-08-18
Gap up/down, White Horse/Three White Soldiers, Three Black Crows,
Breakouts, Multi-TF confirmation, News, Full scoring.
Outputs to C:\Users\bravo-usr1\Desktop\scandata\DAYSHIFT_2026-08-18_PREMKT_<STAMP>.json/.md
"""

import json
import os
import sys
import time
import math
import datetime
import threading
from pathlib import Path
from datetime import timezone, timedelta
import numpy as np
import pandas as pd
import yfinance as yf
import requests

# ─── Config ──────────────────────────────────────────────────────────────
BASE = Path(r'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
SCANDATA = Path(r'C:/Users/bravo-usr1/Desktop/scandata')
SCANDATA.mkdir(parents=True, exist_ok=True)
NOW = datetime.datetime.now(timezone.utc)
STAMP = NOW.strftime('%Y%m%dT%H%M%SZ')
OUT_JSON = SCANDATA / f'DAYSHIFT_2026-08-18_PREMKT_{STAMP}.json'
OUT_MD   = SCANDATA / f'DAYSHIFT_2026-08-18_PREMKT_{STAMP}.md'

# ─── Universe ───────────────────────────────────────────────────────────
UNIVERSE = {
    'Equities': [
        'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','JPM','V','JNJ',
        'WMT','PG','MA','UNH','HD','DIS','BAC','XOM','PFE','KO','PEP',
        'AMD','INTC','CRM','ADBE','NFLX','AVGO','COST','ABBV','TMO','MRK',
        'LLY','ACN','ORCL','CSCO','QCOM','TXN','INTC','AMGN','LIN','PM',
        'IBM','GE','CAT','BA','MMM','HON','RTX','LMT','DE','UNP','UPS'
    ],
    'ETFs': [
        'SPY','QQQ','IWM','DIA','VOO','VTI','ARKK','XLF','XLK','XLE',
        'XLI','XLV','XLP','XLU','XLB','XLY','EFA','EEM','GLD','SLV',
        'TLT','HYG','LQD','IEF','SHY','EEM','EFA','VNQ','OIH','XME'
    ],
    'Indices': [
        '^GSPC','^IXIC','^DJI','^RUT','^VIX','ES=F','NQ=F','YM=F','RTY=F'
    ],
    'Forex': [
        'EURUSD=X','GBPUSD=X','USDJPY=X','AUDUSD=X','USDCAD=X','USDCHF=X',
        'NZDUSD=X','EURJPY=X','EURGBP=X','GBPJPY=X','AUDJPY=X'
    ],
    'Crypto': [
        'BTC-USD','ETH-USD','SOL-USD','XRP-USD','AVAX-USD','LINK-USD',
        'ADA-USD','DOGE-USD','DOT-USD','MATIC-USD','UNI-USD','AAVE-USD'
    ],
    'Commodities': [
        'GC=F','SI=F','CL=F','NG=F','HG=F','PL=F','ZC=F','ZS=F','ZW=F','KC=F'
    ],
    'Bonds': [
        '^TNX','^TYX','TLT','IEF','SHY','ZB=F','ZN=F','ZF=F'
    ]
}

# ─── Helpers ────────────────────────────────────────────────────────────
def fetch_yf(symbol, period='1mo', interval='1h'):
    """Fetch data with fallback intervals."""
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         auto_adjust=True, progress=False, threads=False, timeout=15)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            return df
    except Exception as e:
        pass
    return pd.DataFrame()

def fetch_multi_tf(symbol):
    """Fetch 1H, 4H, 1D, 1W timeframes."""
    tfs = {}
    for interval, period in [('1h','1mo'),('4h','3mo'),('1d','1y'),('1wk','2y')]:
        df = fetch_yf(symbol, period=period, interval=interval)
        if not df.empty:
            tfs[interval] = df
    return tfs

def calc_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calc_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calc_vwap(df):
    """VWAP from 1H data (typical price * volume)."""
    if 'volume' not in df.columns or df['volume'].isna().all():
        return pd.Series(index=df.index, dtype=float)
    tp = (df['high'] + df['low'] + df['close']) / 3
    vwap = (tp * df['volume']).cumsum() / df['volume'].cumsum()
    return vwap

def detect_gap(df_daily):
    """Detect gap up/down from prev close to current open."""
    if len(df_daily) < 2:
        return None
    prev_close = df_daily['close'].iloc[-2]
    curr_open = df_daily['open'].iloc[-1]
    pct = (curr_open - prev_close) / prev_close * 100
    return {'pct': round(pct, 2), 'direction': 'UP' if pct > 0.1 else 'DOWN' if pct < -0.1 else 'FLAT'}

def detect_white_soldiers(df, period=3):
    """Three White Soldiers: 3 consecutive bullish candles, each closing higher."""
    if len(df) < period:
        return False
    last3 = df.tail(period)
    return all(last3['close'] > last3['open']) and \
           (last3['close'].iloc[-1] > last3['close'].iloc[-2] > last3['close'].iloc[-3])

def detect_black_crows(df, period=3):
    """Three Black Crows: 3 consecutive bearish candles, each closing lower."""
    if len(df) < period:
        return False
    last3 = df.tail(period)
    return all(last3['close'] < last3['open']) and \
           (last3['close'].iloc[-1] < last3['close'].iloc[-2] < last3['close'].iloc[-3])

def detect_bullish_engulfing(df):
    if len(df) < 2: return False
    prev = df.iloc[-2]; curr = df.iloc[-1]
    return (prev['close'] < prev['open']) and (curr['close'] > curr['open']) and \
           (curr['open'] < prev['close']) and (curr['close'] > prev['open'])

def detect_bearish_engulfing(df):
    if len(df) < 2: return False
    prev = df.iloc[-2]; curr = df.iloc[-1]
    return (prev['close'] > prev['open']) and (curr['close'] < curr['open']) and \
           (curr['open'] > prev['close']) and (curr['close'] < prev['open'])

def detect_breakout(df, lookback=20):
    """Price breaks above 20-bar high with volume."""
    if len(df) < lookback + 1: return False
    recent_high = df['high'].iloc[-lookback-1:-1].max()
    curr_close = df['close'].iloc[-1]
    curr_vol = df['volume'].iloc[-1] if 'volume' in df.columns else 0
    avg_vol = df['volume'].iloc[-lookback-1:-1].mean() if 'volume' in df.columns else 0
    return curr_close > recent_high and curr_vol > avg_vol * 1.2

def detect_breakdown(df, lookback=20):
    """Price breaks below 20-bar low with volume."""
    if len(df) < lookback + 1: return False
    recent_low = df['low'].iloc[-lookback-1:-1].min()
    curr_close = df['close'].iloc[-1]
    curr_vol = df['volume'].iloc[-1] if 'volume' in df.columns else 0
    avg_vol = df['volume'].iloc[-lookback-1:-1].mean() if 'volume' in df.columns else 0
    return curr_close < recent_low and curr_vol > avg_vol * 1.2

def trend_confirmation(tfs):
    """Check multi-timeframe trend alignment: 1H, 4H, 1D, 1W all bullish/bearish."""
    bulls = 0; bears = 0
    for tf, df in tfs.items():
        if len(df) < 50: continue
        ema20 = calc_ema(df['close'], 20).iloc[-1]
        ema50 = calc_ema(df['close'], 50).iloc[-1]
        if ema20 > ema50: bulls += 1
        else: bears += 1
    total = bulls + bears
    if total == 0: return 'UNKNOWN', 0
    return ('BULLISH' if bulls > bears else 'BEARISH', round(max(bulls, bears)/total*100, 1))

def backtest_simple(df, side='LONG', sl_mult=1.0, tp_mult=2.0, period=90):
    """Simple ATR-based backtest on 1H data."""
    if len(df) < period + 1: return {'win_rate': 0, 'expectancy': 0, 'trades': 0}
    highs = df['high']; lows = df['low']; closes = df['close']
    atr = calc_atr(highs, lows, closes, 14)
    if atr is None or atr.iloc[-1] == 0: return {'win_rate': 0, 'expectancy': 0, 'trades': 0}
    atr_val = atr.iloc[-1]
    wins = losses = total_r = 0
    for i in range(20, min(len(df)-1, period+20)):
        entry = closes.iloc[i]
        if side == 'LONG':
            sl = entry - sl_mult * atr_val
            tp = entry + tp_mult * atr_val
            for j in range(i+1, len(df)):
                if lows.iloc[j] <= sl: losses += 1; total_r -= 1; break
                if highs.iloc[j] >= tp: wins += 1; total_r += tp_mult; break
        else:
            sl = entry + sl_mult * atr_val
            tp = entry - tp_mult * atr_val
            for j in range(i+1, len(df)):
                if highs.iloc[j] >= sl: losses += 1; total_r -= 1; break
                if lows.iloc[j] <= tp: wins += 1; total_r += tp_mult; break
    trades = wins + losses
    wr = wins/trades if trades else 0
    exp = total_r/trades if trades else 0
    return {'win_rate': round(wr,2), 'expectancy': round(exp,2), 'trades': trades}

def fetch_news(symbol, asset_class):
    """Fetch lightweight news sentiment via DuckDuckGo HTML scrape."""
    try:
        query = f"{symbol} {asset_class} market news today"
        url = f"https://lite.duckduckgo.com/lite/?q={requests.utils.quote(query)}"
        r = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0'})
        text = r.text.lower()
        bull_kw = ['surge','rally','breakout','upgrade','bullish','gain','soar','record','beat','outperform','etf approval','inflow']
        bear_kw = ['crash','downgrade','bearish','sell-off','hack','ban','lawsuit','miss','underperform','outflow','probe']
        score = sum(text.count(k) for k in bull_kw) - sum(text.count(k) for k in bear_kw)
        sentiment = 'BULLISH' if score > 1 else 'BEARISH' if score < -1 else 'NEUTRAL'
        return sentiment, score
    except Exception:
        return 'NEUTRAL', 0

# ─── Main Scan ──────────────────────────────────────────────────────────
print(f"[SCAN] Starting pre-market dayshift scan at {NOW.isoformat()}")
print(f"[SCAN] Universe: {sum(len(v) for v in UNIVERSE.values())} symbols across {len(UNIVERSE)} asset classes")

results = {
    'scan_metadata': {
        'shift': 'DAYSHIFT',
        'scan_type': 'PREMARKET_ALL_SECTOR',
        'timestamp': NOW.isoformat(),
        'date': NOW.strftime('%Y-%m-%d'),
        'universe_size': sum(len(v) for v in UNIVERSE.values()),
        'asset_classes': list(UNIVERSE.keys()),
        'scanner_version': 'premarket_dayshift_v1'
    },
    'gap_leaders': {'up': [], 'down': []},
    'white_soldiers': [],
    'black_crows': [],
    'breakouts': [],
    'breakdowns': [],
    'bullish_engulfing': [],
    'bearish_engulfing': [],
    'qualified_setups': [],
    'watchlist': [],
    'sector_summary': {}
}

lock = threading.Lock()

def scan_symbol(symbol, asset_class):
    tfs = fetch_multi_tf(symbol)
    if not tfs or '1h' not in tfs:
        return
    df_1h = tfs['1h']
    df_4h = tfs.get('4h', pd.DataFrame())
    df_1d = tfs.get('1d', pd.DataFrame())
    df_1w = tfs.get('1w', pd.DataFrame())

    # --- Gap detection (daily) ---
    gap = detect_gap(df_1d) if len(df_1d) >= 2 else None

    # --- Pattern detection (1H) ---
    ws = detect_white_soldiers(df_1h)
    bc = detect_black_crows(df_1h)
    be = detect_bullish_engulfing(df_1h)
    bse = detect_bearish_engulfing(df_1h)
    bo = detect_breakout(df_1h)
    bd = detect_breakdown(df_1h)

    # --- Multi-TF trend ---
    trend_label, trend_pct = trend_confirmation(tfs)

    # --- Technical indicators (1H) ---
    close = df_1h['close']
    rsi = calc_rsi(close).iloc[-1] if len(close) > 14 else 50
    atr = calc_atr(df_1h['high'], df_1h['low'], close).iloc[-1] if len(df_1h) > 14 else 0
    vwap = calc_vwap(df_1h).iloc[-1] if len(df_1h) > 20 else close.iloc[-1]
    ema20 = calc_ema(close, 20).iloc[-1] if len(close) > 20 else close.iloc[-1]
    ema50 = calc_ema(close, 50).iloc[-1] if len(close) > 50 else close.iloc[-1]

    # --- Backtest ---
    bt_long = backtest_simple(df_1h, 'LONG')
    bt_short = backtest_simple(df_1h, 'SHORT')

    # --- News ---
    news_sent, news_score = fetch_news(symbol, asset_class)

    # --- Entry/SL/TP (ATR-based) ---
    price = float(close.iloc[-1])
    atr_val = float(atr) if atr > 0 else price * 0.01
    sl_dist = 1.5 * atr_val
    tp_dist = 3.0 * atr_val

    # Direction bias from patterns + trend
    bullish_signals = sum([ws, be, bo, trend_label == 'BULLISH', ema20 > ema50, rsi < 60])
    bearish_signals = sum([bc, bse, bd, trend_label == 'BEARISH', ema20 < ema50, rsi > 40])

    direction = 'LONG' if bullish_signals > bearish_signals else 'SHORT' if bearish_signals > bullish_signals else 'NEUTRAL'

    if direction == 'LONG':
        entry = round(price, 4)
        sl = round(price - sl_dist, 4)
        tp = round(price + tp_dist, 4)
        bt = bt_long
    elif direction == 'SHORT':
        entry = round(price, 4)
        sl = round(price + sl_dist, 4)
        tp = round(price - tp_dist, 4)
        bt = bt_short
    else:
        entry = sl = tp = price
        bt = {'win_rate': 0, 'expectancy': 0, 'trades': 0}

    rr = round(abs(tp - entry) / abs(entry - sl), 2) if sl != entry else 0

    # --- Conviction score (0-10) ---
    conviction = 0
    if ws: conviction += 2
    if bc: conviction += 2
    if be: conviction += 1.5
    if bse: conviction += 1.5
    if bo: conviction += 2
    if bd: conviction += 2
    if trend_pct >= 75: conviction += 2
    elif trend_pct >= 50: conviction += 1
    if bt.get('win_rate', 0) >= 0.55: conviction += 2
    elif bt.get('win_rate', 0) >= 0.45: conviction += 1
    if bt.get('expectancy', 0) > 0.5: conviction += 1
    if abs(gap.get('pct', 0)) > 1.5: conviction += 1
    conviction = min(10, max(0, conviction))

    # --- Record gap ---
    if gap and gap['direction'] == 'UP' and gap['pct'] > 1:
        with lock:
            results['gap_leaders']['up'].append({'symbol': symbol, 'asset_class': asset_class, 'gap_pct': gap['pct'], 'price': price})
    elif gap and gap['direction'] == 'DOWN' and gap['pct'] < -1:
        with lock:
            results['gap_leaders']['down'].append({'symbol': symbol, 'asset_class': asset_class, 'gap_pct': gap['pct'], 'price': price})

    # --- Record patterns ---
    if ws:
        with lock:
            results['white_soldiers'].append({'symbol': symbol, 'asset_class': asset_class, 'price': price, 'trend': trend_label})
    if bc:
        with lock:
            results['black_crows'].append({'symbol': symbol, 'asset_class': asset_class, 'price': price, 'trend': trend_label})
    if bo:
        with lock:
            results['breakouts'].append({'symbol': symbol, 'asset_class': asset_class, 'price': price, 'volume_surge': True})
    if bd:
        with lock:
            results['breakdowns'].append({'symbol': symbol, 'asset_class': asset_class, 'price': price, 'volume_surge': True})
    if be:
        with lock:
            results['bullish_engulfing'].append({'symbol': symbol, 'asset_class': asset_class, 'price': price})
    if bse:
        with lock:
            results['bearish_engulfing'].append({'symbol': symbol, 'asset_class': asset_class, 'price': price})

    # --- Qualified setup (conviction >= 5, backtested, RR >= 1.8) ---
    qualified = (conviction >= 5 and bt.get('win_rate', 0) >= 0.45 and rr >= 1.8 and direction != 'NEUTRAL')
    
    setup = {
        'symbol': symbol,
        'asset_class': asset_class,
        'direction': direction,
        'price': price,
        'entry': entry,
        'stop_loss': sl,
        'take_profit': tp,
        'risk_reward': rr,
        'conviction': round(conviction, 1),
        'trend': trend_label,
        'trend_alignment_pct': trend_pct,
        'rsi': round(rsi, 1),
        'atr': round(atr_val, 4),
        'vwap': round(vwap, 4),
        'ema20': round(ema20, 4),
        'ema50': round(ema50, 4),
        'gap': gap,
        'patterns': {
            'white_soldiers': ws,
            'black_crows': bc,
            'bullish_engulfing': be,
            'bearish_engulfing': bse,
            'breakout': bo,
            'breakdown': bd
        },
        'backtest': bt,
        'news': {'sentiment': news_sent, 'score': news_score},
        'qualified': qualified,
        'qualified_reason': 'OK' if qualified else f"conv={conviction} wr={bt.get('win_rate',0)} rr={rr} dir={direction}"
    }

    with lock:
        if asset_class not in results['sector_summary']:
            results['sector_summary'][asset_class] = {'total': 0, 'qualified': 0, 'gap_up': 0, 'gap_down': 0}
        results['sector_summary'][asset_class]['total'] += 1
        if qualified:
            results['sector_summary'][asset_class]['qualified'] += 1
            results['qualified_setups'].append(setup)
        else:
            results['watchlist'].append(setup)

threads = []
for asset_class, symbols in UNIVERSE.items():
    for sym in symbols:
        t = threading.Thread(target=scan_symbol, args=(sym, asset_class))
        t.start()
        threads.append(t)
        if len(threads) >= 20:  # batch
            for t in threads: t.join()
            threads = []

for t in threads:
    t.join()

# ─── Sort & Rank ────────────────────────────────────────────────────────
results['qualified_setups'].sort(key=lambda x: (-x['conviction'], -x['backtest']['win_rate']))
results['watchlist'].sort(key=lambda x: (-x['conviction'], -x['backtest']['win_rate']))
results['gap_leaders']['up'].sort(key=lambda x: -x['gap_pct'])
results['gap_leaders']['down'].sort(key=lambda x: x['gap_pct'])

# ─── Save JSON ──────────────────────────────────────────────────────────
OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
print(f"[SCAN] Saved JSON: {OUT_JSON}")

# ─── Generate Markdown Report ───────────────────────────────────────────
md = []
md.append(f"# 🌅 DAYSHIFT PRE-MARKET SCAN — {NOW.strftime('%Y-%m-%d %H:%M:%S %Z')}")
md.append(f"**Scanner:** Pre-Market All-Sector v1  \n**Universe:** {results['scan_metadata']['universe_size']} symbols across {len(results['scan_metadata']['asset_classes'])} asset classes  \n**Qualified Setups:** {len(results['qualified_setups'])}  \n**Watchlist:** {len(results['watchlist'])}")
md.append("")

# Gap Leaders
if results['gap_leaders']['up']:
    md.append("## 📈 GAP UP LEADERS")
    md.append("| Symbol | Class | Gap % | Price |")
    md.append("|--------|-------|-------|-------|")
    for g in results['gap_leaders']['up'][:10]:
        md.append(f"| {g['symbol']} | {g['asset_class']} | +{g['gap_pct']}% | {g['price']} |")
    md.append("")

if results['gap_leaders']['down']:
    md.append("## 📉 GAP DOWN LEADERS")
    md.append("| Symbol | Class | Gap % | Price |")
    md.append("|--------|-------|-------|-------|")
    for g in results['gap_leaders']['down'][:10]:
        md.append(f"| {g['symbol']} | {g['asset_class']} | {g['gap_pct']}% | {g['price']} |")
    md.append("")

# White Soldiers / Black Crows
if results['white_soldiers']:
    md.append("## ⚪ THREE WHITE SOLDIERS (Bullish)")
    md.append("| Symbol | Class | Price | Trend |")
    md.append("|--------|-------|-------|-------|")
    for s in results['white_soldiers'][:10]:
        md.append(f"| {s['symbol']} | {s['asset_class']} | {s['price']} | {s['trend']} |")
    md.append("")

if results['black_crows']:
    md.append("## ⚫ THREE BLACK CROWS (Bearish)")
    md.append("| Symbol | Class | Price | Trend |")
    md.append("|--------|-------|-------|-------|")
    for s in results['black_crows'][:10]:
        md.append(f"| {s['symbol']} | {s['asset_class']} | {s['price']} | {s['trend']} |")
    md.append("")

# Breakouts / Breakdowns
if results['breakouts']:
    md.append("## 🚀 BREAKOUTS (Volume Confirmed)")
    md.append("| Symbol | Class | Price |")
    md.append("|--------|-------|-------|")
    for s in results['breakouts'][:10]:
        md.append(f"| {s['symbol']} | {s['asset_class']} | {s['price']} |")
    md.append("")

if results['breakdowns']:
    md.append("## 💥 BREAKDOWNS (Volume Confirmed)")
    md.append("| Symbol | Class | Price |")
    md.append("|--------|-------|-------|")
    for s in results['breakdowns'][:10]:
        md.append(f"| {s['symbol']} | {s['asset_class']} | {s['price']} |")
    md.append("")

# Qualified Setups Table
if results['qualified_setups']:
    md.append("## 🏆 QUALIFIED SETUPS (Conviction ≥ 5, WR ≥ 45%, RR ≥ 1.8)")
    md.append("| # | Symbol | Class | Dir | Conv | Trend | RSI | Gap | Entry | SL | TP | RR | WR | Exp | BT Trades | News |")
    md.append("|---|--------|-------|-----|------|-------|-----|-----|-------|----|----|----|----|-----|-----------|------|")
    for i, s in enumerate(results['qualified_setups'][:20], 1):
        gap_str = f"{s['gap']['direction']} {s['gap']['pct']}%" if s['gap'] else "—"
        md.append(f"| {i} | {s['symbol']} | {s['asset_class']} | {s['direction']} | {s['conviction']} | {s['trend']} {s['trend_alignment_pct']}% | {s['rsi']} | {gap_str} | {s['entry']} | {s['stop_loss']} | {s['take_profit']} | {s['risk_reward']} | {s['backtest']['win_rate']} | {s['backtest']['expectancy']} | {s['backtest']['trades']} | {s['news']['sentiment']} |")
    md.append("")

# Sector Summary
md.append("## 📊 SECTOR SUMMARY")
md.append("| Class | Total | Qualified | Gap Up | Gap Down |")
md.append("|-------|-------|-----------|--------|----------|")
for cls, stats in sorted(results['sector_summary'].items()):
    md.append(f"| {cls} | {stats['total']} | {stats['qualified']} | {stats['gap_up']} | {stats['gap_down']} |")
md.append("")

# Watchlist (top 20)
if results['watchlist']:
    md.append("## 👀 WATCHLIST (Top 20 by Conviction)")
    md.append("| Symbol | Class | Dir | Conv | Trend | RSI | RR | WR | Qual Reason |")
    md.append("|--------|-------|-----|------|-------|-----|----|----|-------------|")
    for s in results['watchlist'][:20]:
        md.append(f"| {s['symbol']} | {s['asset_class']} | {s['direction']} | {s['conviction']} | {s['trend']} | {s['rsi']} | {s['risk_reward']} | {s['backtest']['win_rate']} | {s['qualified_reason']} |")
    md.append("")

md.append(f"\n---\n*Generated: {NOW.isoformat()}  \n*Source: `{OUT_JSON.name}`")

OUT_MD.write_text("\n".join(md), encoding='utf-8')
print(f"[SCAN] Saved Markdown: {OUT_MD}")
print(f"[SCAN] Complete. Qualified: {len(results['qualified_setups'])}, Watch: {len(results['watchlist'])}")