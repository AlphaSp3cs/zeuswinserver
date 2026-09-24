#!/usr/bin/env python3
"""
Dayshift all-sector scan with robust yfinance handling, 30-day backtest before qualification.
Outputs: scandata DAYSHIFT_2026-08-18_PREMKT_<STAMP>.json/.md
"""
import json
import datetime
import threading
from pathlib import Path
from datetime import timezone
import math
import requests
import numpy as np
import pandas as pd
import yfinance as yf

SCANDATA = Path('C:/Users/bravo-usr1/Desktop/scandata')
SCANDATA.mkdir(parents=True, exist_ok=True)
NOW = datetime.datetime.now(timezone.utc)
STAMP = NOW.strftime('%Y%m%dT%H%M%SZ')
OUT_JSON = SCANDATA / f'DAYSHIFT_2026-08-18_PREMKT_{STAMP}.json'
OUT_MD = SCANDATA / f'DAYSHIFT_2026-08-18_PREMKT_{STAMP}.md'

UNIVERSE = {
    'Equities': [
        'AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','JPM','V','JNJ',
        'WMT','PG','MA','UNH','HD','DIS','BAC','XOM','PFE','KO','PEP',
        'AMD','INTC','CRM','ADBE','NFLX','AVGO','COST','ABBV','TMO','MRK',
        'LLY','ACN','ORCL','CSCO','QCOM','TXN','AMGN','LIN','PM',
        'IBM','GE','CAT','BA','MMM','HON','RTX','LMT','DE','UNP','UPS'
    ],
    'ETFs': [
        'SPY','QQQ','IWM','DIA','VOO','VTI','ARKK','XLF','XLK','XLE',
        'XLI','XLV','XLP','XLU','XLB','XLY','EFA','EEM','GLD','SLV',
        'TLT','HYG','LQD','IEF','SHY','VNQ','OIH','XME'
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

def fetch_yf(symbol, period='1mo', interval='1h'):
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False, timeout=15)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                try:
                    df = df.xs(symbol, level=1, axis=1)
                    if isinstance(df, pd.Series):
                        df = df.to_frame()
                except Exception:
                    df = df.droplevel(1, axis=1)
            df.columns = [str(c).lower() for c in df.columns]
            return df
    except Exception:
        pass
    return pd.DataFrame()

def fetch_multi_tf(symbol):
    tfs = {}
    for interval, period in [('1h','1mo'), ('4h','3mo'), ('1d','1y'), ('1wk','2y')]:
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
    if 'volume' not in df.columns or df['volume'].isna().all():
        return pd.Series(index=df.index, dtype=float)
    tp = (df['high'] + df['low'] + df['close']) / 3
    return (tp * df['volume']).cumsum() / df['volume'].cumsum()

def detect_gap(df_daily):
    if len(df_daily) < 2:
        return None
    prev_close = float(df_daily['close'].iloc[-2])
    curr_open = float(df_daily['open'].iloc[-1])
    pct = (curr_open - prev_close) / prev_close * 100
    return {'pct': round(pct, 2), 'direction': 'UP' if pct > 0.1 else 'DOWN' if pct < -0.1 else 'FLAT'}

def detect_white_soldiers(df, period=3):
    if len(df) < period:
        return False
    last3 = df.tail(period)
    return bool(all(last3['close'] > last3['open']) and (last3['close'].iloc[-1] > last3['close'].iloc[-2] > last3['close'].iloc[-3]))

def detect_black_crows(df, period=3):
    if len(df) < period:
        return False
    last3 = df.tail(period)
    return bool(all(last3['close'] < last3['open']) and (last3['close'].iloc[-1] < last3['close'].iloc[-2] < last3['close'].iloc[-3]))

def detect_bullish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    return bool(prev['close'] < prev['open'] and curr['close'] > curr['open'] and curr['open'] < prev['close'] and curr['close'] > prev['open'])

def detect_bearish_engulfing(df):
    if len(df) < 2:
        return False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    return bool(prev['close'] > prev['open'] and curr['close'] < curr['open'] and curr['open'] > prev['close'] and curr['close'] < prev['open'])

def detect_breakout(df, lookback=20):
    if len(df) < lookback + 1:
        return False
    recent_high = float(df['high'].iloc[-lookback-1:-1].max())
    curr_close = float(df['close'].iloc[-1])
    curr_vol = float(df['volume'].iloc[-1]) if 'volume' in df.columns else 0.0
    avg_vol = float(df['volume'].iloc[-lookback-1:-1].mean()) if 'volume' in df.columns else 0.0
    return bool(curr_close > recent_high and avg_vol and curr_vol > avg_vol * 1.2)

def detect_breakdown(df, lookback=20):
    if len(df) < lookback + 1:
        return False
    recent_low = float(df['low'].iloc[-lookback-1:-1].min())
    curr_close = float(df['close'].iloc[-1])
    curr_vol = float(df['volume'].iloc[-1]) if 'volume' in df.columns else 0.0
    avg_vol = float(df['volume'].iloc[-lookback-1:-1].mean()) if 'volume' in df.columns else 0.0
    return bool(curr_close < recent_low and avg_vol and curr_vol > avg_vol * 1.2)

def trend_confirmation(tfs):
    bulls = 0
    bears = 0
    for tf, df in tfs.items():
        if len(df) < 50:
            continue
        ema20 = float(calc_ema(df['close'], 20).iloc[-1])
        ema50 = float(calc_ema(df['close'], 50).iloc[-1])
        if ema20 > ema50:
            bulls += 1
        else:
            bears += 1
    total = bulls + bears
    if total == 0:
        return 'UNKNOWN', 0
    pct = round(max(bulls, bears) / total * 100, 1)
    return ('BULLISH' if bulls > bears else 'BEARISH', pct)

def backtest_simple(df, side='LONG', sl_mult=1.0, tp_mult=2.0, period=90):
    if len(df) < period + 1:
        return {'win_rate': 0.0, 'profit_factor': 0.0, 'avg_r': 0.0, 'trades': 0}
    highs = df['high']
    lows = df['low']
    closes = df['close']
    atr = calc_atr(highs, lows, closes, 14)
    if atr is None or float(atr.iloc[-1]) == 0:
        return {'win_rate': 0.0, 'profit_factor': 0.0, 'avg_r': 0.0, 'trades': 0}
    atr_val = float(atr.iloc[-1])
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    total_r = 0.0
    for i in range(20, min(len(df) - 1, period + 20)):
        entry = float(closes.iloc[i])
        if side == 'LONG':
            sl = entry - sl_mult * atr_val
            tp = entry + tp_mult * atr_val
            for j in range(i + 1, len(df)):
                if float(lows.iloc[j]) <= sl:
                    losses += 1
                    gross_loss += 1.0
                    total_r -= 1.0
                    break
                if float(highs.iloc[j]) >= tp:
                    wins += 1
                    gross_profit += tp_mult
                    total_r += tp_mult
                    break
        else:
            sl = entry + sl_mult * atr_val
            tp = entry - tp_mult * atr_val
            for j in range(i + 1, len(df)):
                if float(highs.iloc[j]) >= sl:
                    losses += 1
                    gross_loss += 1.0
                    total_r -= 1.0
                    break
                if float(lows.iloc[j]) <= tp:
                    wins += 1
                    gross_profit += tp_mult
                    total_r += tp_mult
                    break
    trades = wins + losses
    win_rate = wins / trades if trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
    avg_r = total_r / trades if trades else 0.0
    return {
        'win_rate': round(win_rate, 2),
        'profit_factor': round(profit_factor, 2),
        'avg_r': round(avg_r, 2),
        'trades': trades
    }

def fetch_news(symbol, asset_class):
    try:
        query = f"{symbol} {asset_class} market news today"
        url = f"https://lite.duckduckgo.com/lite/?q={requests.utils.quote(query)}"
        r = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0'})
        text = r.text.lower()
        bull_kw = ['surge','rally','breakout','upgrade','bullish','gain','soar','record','beat','outperform','inflow']
        bear_kw = ['crash','downgrade','bearish','sell-off','hack','ban','lawsuit','miss','underperform','outflow','probe']
        score = sum(text.count(k) for k in bull_kw) - sum(text.count(k) for k in bear_kw)
        sentiment = 'BULLISH' if score > 1 else 'BEARISH' if score < -1 else 'NEUTRAL'
        return sentiment, score
    except Exception:
        return 'NEUTRAL', 0

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
        'scanner_version': 'premarket_dayshift_v3'
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
    'sector_summary': {},
    'scan_errors': []
}

lock = threading.Lock()

def scan_symbol(symbol, asset_class):
    try:
        tfs = fetch_multi_tf(symbol)
        if not tfs or '1h' not in tfs:
            return
        df_1h = tfs['1h']
        df_4h = tfs.get('4h', pd.DataFrame())
        df_1d = tfs.get('1d', pd.DataFrame())
        df_1w = tfs.get('1w', pd.DataFrame())

        gap = detect_gap(df_1d) if len(df_1d) >= 2 else None
        ws = detect_white_soldiers(df_1h)
        bc = detect_black_crows(df_1h)
        be = detect_bullish_engulfing(df_1h)
        bse = detect_bearish_engulfing(df_1h)
        bo = detect_breakout(df_1h)
        bd = detect_breakdown(df_1h)

        trend_label, trend_pct = trend_confirmation(tfs)

        close = df_1h['close']
        rsi = float(calc_rsi(close).iloc[-1]) if len(close) > 14 else 50.0
        atr = float(calc_atr(df_1h['high'], df_1h['low'], close).iloc[-1]) if len(df_1h) > 14 else 0.0
        vwap = float(calc_vwap(df_1h).iloc[-1]) if len(df_1h) > 20 else float(close.iloc[-1])
        ema20 = float(calc_ema(close, 20).iloc[-1]) if len(close) > 20 else float(close.iloc[-1])
        ema50 = float(calc_ema(close, 50).iloc[-1]) if len(close) > 50 else float(close.iloc[-1])

        bullish_signals = sum([ws, be, bo, trend_label == 'BULLISH', ema20 > ema50, rsi < 60])
        bearish_signals = sum([bc, bse, bd, trend_label == 'BEARISH', ema20 < ema50, rsi > 40])

        direction = 'LONG' if bullish_signals > bearish_signals else 'SHORT' if bearish_signals > bullish_signals else 'NEUTRAL'
        price = float(close.iloc[-1])
        atr_val = atr if atr > 0 else price * 0.01
        sl_dist = 1.0 * atr_val
        tp_dist = 2.0 * atr_val

        if direction == 'LONG':
            entry = round(price, 4)
            sl = round(price - sl_dist, 4)
            tp = round(price + tp_dist, 4)
            bt = backtest_simple(df_1h, 'LONG')
        elif direction == 'SHORT':
            entry = round(price, 4)
            sl = round(price + sl_dist, 4)
            tp = round(price - tp_dist, 4)
            bt = backtest_simple(df_1h, 'SHORT')
        else:
            entry = sl = tp = price
            bt = {'win_rate': 0.0, 'profit_factor': 0.0, 'avg_r': 0.0, 'trades': 0}

        rr = round(abs(tp - entry) / abs(entry - sl), 2) if sl != entry else 0.0

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
        if bt.get('profit_factor', 0) >= 1.4: conviction += 1
        if bt.get('avg_r', 0) > 0: conviction += 1
        if abs(gap.get('pct', 0)) > 1.5: conviction += 1
        conviction = min(10.0, max(0.0, conviction))

        if gap and gap['direction'] == 'UP' and gap['pct'] > 1:
            with lock:
                results['gap_leaders']['up'].append({'symbol': symbol, 'asset_class': asset_class, 'gap_pct': gap['pct'], 'price': price})
        elif gap and gap['direction'] == 'DOWN' and gap['pct'] < -1:
            with lock:
                results['gap_leaders']['down'].append({'symbol': symbol, 'asset_class': asset_class, 'gap_pct': gap['pct'], 'price': price})

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

        pf = bt.get('profit_factor', 0.0)
        pf_pass = pf >= 1.4 or (pf == float('inf') and bt.get('win_rate', 0) >= 0.5)
        quality_pass = (
            bt.get('win_rate', 0) >= 0.5 and
            pf_pass and
            bt.get('avg_r', 0) > 0 and
            rr >= 2.0 and
            bt.get('trades', 0) >= 10
        )
        qualified = bool(conviction >= 5 and direction != 'NEUTRAL' and quality_pass)

        news_sent, news_score = fetch_news(symbol, asset_class)
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
            'quality_pass': quality_pass,
            'qualified': qualified,
            'qualified_reason': 'OK' if qualified else f"conv={conviction} wr={bt.get('win_rate',0)} pf={bt.get('profit_factor',0)} rr={rr} trades={bt.get('trades',0)}"
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
    except Exception as e:
        with lock:
            results['scan_errors'].append({'symbol': symbol, 'asset_class': asset_class, 'error': repr(e)})

threads = []
for asset_class, symbols in UNIVERSE.items():
    for sym in symbols:
        t = threading.Thread(target=scan_symbol, args=(sym, asset_class))
        t.start()
        threads.append(t)
        if len(threads) >= 20:
            for t in threads:
                t.join()
            threads = []
for t in threads:
    t.join()

results['qualified_setups'].sort(key=lambda x: (-x['conviction'], -x['backtest']['win_rate']))
results['watchlist'].sort(key=lambda x: (-x['conviction'], -x['backtest']['win_rate']))
results['gap_leaders']['up'].sort(key=lambda x: -x['gap_pct'])
results['gap_leaders']['down'].sort(key=lambda x: x['gap_pct'])

OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
print(f"[SCAN] Saved JSON: {OUT_JSON}")

md = []
md.append(f"# Dayshift All-Sector Scan — {NOW.strftime('%Y-%m-%d %H:%M:%S %Z')}")
md.append(f"Universe: {results['scan_metadata']['universe_size']} symbols across {len(results['scan_metadata']['asset_classes'])} asset classes")
md.append(f"Qualified: {len(results['qualified_setups'])} | Watchlist: {len(results['watchlist'])}")
md.append("")
if results['gap_leaders']['up']:
    md.append("## Gap Up")
    for g in results['gap_leaders']['up'][:20]:
        md.append(f"- {g['symbol']} {g['asset_class']} {g['gap_pct']}%")
if results['gap_leaders']['down']:
    md.append("## Gap Down")
    for g in results['gap_leaders']['down'][:20]:
        md.append(f"- {g['symbol']} {g['asset_class']} {g['gap_pct']}%")
md.append("## Patterns")
md.append(f"- Three White Soldiers: {len(results['white_soldiers'])}")
md.append(f"- Three Black Crows: {len(results['black_crows'])}")
md.append(f"- Breakouts: {len(results['breakouts'])}")
md.append(f"- Breakdowns: {len(results['breakdowns'])}")
md.append("## Top Qualified")
for i, s in enumerate(results['qualified_setups'][:20], 1):
    md.append(f"{i}. {s['symbol']} {s['asset_class']} {s['direction']} conv={s['conviction']} RSI={s['rsi']} RR={s['risk_reward']} WR={s['backtest']['win_rate']} PF={s['backtest']['profit_factor']} trades={s['backtest']['trades']} entry={s['entry']} SL={s['stop_loss']} TP={s['take_profit']}")
md.append("## Sector Summary")
for cls, stats in sorted(results['sector_summary'].items()):
    md.append(f"- {cls}: total={stats['total']} qualified={stats['qualified']}")
md.append("## Scan Errors")
for err in results['scan_errors'][:20]:
    md.append(f"- {err['symbol']} {err['asset_class']}: {err['error']}")
OUT_MD.write_text("\n".join(md))
print(f"[SCAN] Saved Markdown: {OUT_MD}")
print(f"[SCAN] Done. Qualified setups: {len(results['qualified_setups'])}")
print(f"[SCAN] Watchlist items: {len(results['watchlist'])}")
print(f"[SCAN] Scan errors: {len(results['scan_errors'])}")
