#!/usr/bin/env python3
"""
Nightshift scan: indices, forex, metals, crypto. No stocks/ETFs/bonds/options/ags.
Uses verified broker prices as primary source. Multi-timeframe trend confirmation.
"""
import json, datetime, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'
HTF_DB = BASE / 'htf' / 'htf_scan.db'
OUT = WORKFLOW / f'nightshift_scan_{datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'

BROKER_PATHS = {
    'capital': r"C:\Program Files\Capital.com MetaTrader 5\terminal64.exe",
    'ftmo': r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe",
}

UNIVERSE = {
    '^DJI': 'Indices', '^IXIC': 'Indices', '^GSPC': 'Indices', '^RUT': 'Indices',
    '^VIX': 'Indices', '^VXN': 'Indices', 'DX-Y.NYB': 'Indices',
    'US30': 'Indices', 'US100': 'Indices', 'US500': 'Indices', 'DXY': 'Indices',
    '^FTSE': 'Indices', '^GDAXI': 'Indices', '^FCHI': 'Indices', '^IBEX': 'Indices',
    '^AEX': 'Indices', '^SSMI': 'Indices', '^STOXX50E': 'Indices',
    '^N225': 'Indices', '^HSI': 'Indices', '^AXJO': 'Indices', '^STI': 'Indices',
    'ES=F': 'Indices', 'NQ=F': 'Indices', 'YM=F': 'Indices', 'RTY=F': 'Indices',
    'EURUSD': 'Forex', 'GBPUSD': 'Forex', 'USDJPY': 'Forex', 'AUDUSD': 'Forex',
    'USDCAD': 'Forex', 'USDCHF': 'Forex', 'NZDUSD': 'Forex',
    'EURJPY': 'Forex', 'EURGBP': 'Forex', 'GBPJPY': 'Forex',
    'AUDJPY': 'Forex', 'AUDCAD': 'Forex', 'CADJPY': 'Forex',
    'CHFJPY': 'Forex', 'NZDJPY': 'Forex', 'EURCHF': 'Forex', 'EURCAD': 'Forex',
    'EURAUD': 'Forex', 'GBPCHF': 'Forex', 'GBPAUD': 'Forex', 'GBPCAD': 'Forex',
    'GBPNZD': 'Forex', 'NZDCHF': 'Forex', 'NZDCAD': 'Forex',
    'USDTRY': 'Forex', 'USDZAR': 'Forex', 'USDMXN': 'Forex', 'USDCNY': 'Forex',
    'USDSGD': 'Forex', 'USDHKD': 'Forex', 'USDSEK': 'Forex', 'USDNOK': 'Forex',
    'XAUUSD': 'Precious_Metals', 'XAGUSD': 'Precious_Metals',
    'HG=F': 'Metals',
    'BTC-USD': 'Crypto', 'ETH-USD': 'Crypto', 'SOL-USD': 'Crypto', 'XRP-USD': 'Crypto',
    'AVAX-USD': 'Crypto', 'LINK-USD': 'Crypto', 'ADA-USD': 'Crypto', 'DOGE-USD': 'Crypto',
}

SECTOR_BROKER = {
    'Indices': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Forex': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Precious_Metals': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Metals': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Crypto': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'KRAKEN', 'ALPACA'],
}

BROKER_ONLY = {
    'US30', 'US100', 'US500', 'DXY', 'XAUUSD', 'XAGUSD',
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD',
    'EURJPY', 'EURGBP', 'GBPJPY', 'AUDJPY', 'AUDCAD', 'CADJPY',
    'CHFJPY', 'NZDJPY', 'EURCHF', 'EURCAD', 'EURAUD', 'GBPCHF', 'GBPAUD',
    'GBPCAD', 'GBPNZD', 'NZDCHF', 'NZDCAD',
    'USDTRY', 'USDZAR', 'USDMXN', 'USDCNY',
    'USDSGD', 'USDHKD', 'USDSEK', 'USDNOK',
}
YF_DELISTED = {'^GDAXI', '^AXJO', '^STI'}

def init_mt5():
    for name, path in BROKER_PATHS.items():
        try:
            mt5.shutdown()
        except Exception:
            pass
        ok = mt5.initialize(path)
        if ok:
            return True
    return False

def fetch_broker(symbol, timeframe=mt5.TIMEFRAME_D1, count=200):
    for name, path in BROKER_PATHS.items():
        try:
            mt5.shutdown()
        except Exception:
            pass
        ok = mt5.initialize(path)
        if not ok:
            continue
        try:
            info = mt5.symbol_info(symbol)
            if not info or not getattr(info, 'visible', False):
                continue
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is None or len(rates) < 20:
                continue
            df = pd.DataFrame(rates)
            df = df.rename(columns={c: c.lower() for c in df.columns})
            if 'volume' not in df.columns:
                for candidate in ['tick_volume', 'real_volume']:
                    if candidate in df.columns:
                        df = df.rename(columns={candidate: 'volume'})
                        break
            df = df[['open', 'high', 'low', 'close', 'volume']].dropna(subset=['close'])
            return df
        except Exception:
            continue
    return pd.DataFrame()

def fetch_yf(symbol, period='60d', interval='1d'):
    import yfinance as yf
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            try:
                df = df.xs(symbol, level=1, axis=1)
                if isinstance(df, pd.Series):
                    df = df.to_frame()
            except Exception:
                try:
                    df = df.droplevel(0, axis=1)
                except Exception:
                    return pd.DataFrame()
        df = df.rename(columns=str.lower)
        needed = {'open', 'high', 'low', 'close'}
        if not needed.issubset(set(df.columns)):
            return pd.DataFrame()
        cols = ['open', 'high', 'low', 'close'] + (['volume'] if 'volume' in df.columns else [])
        df = df[cols].dropna(subset=['close'])
        return df
    except Exception:
        return pd.DataFrame()

def fetch_data(symbol):
    if symbol in BROKER_ONLY or symbol in YF_DELISTED:
        return fetch_broker(symbol), 'broker'
    df = fetch_yf(symbol)
    if not df.empty and len(df) >= 20:
        return df, 'yfinance'
    df = fetch_broker(symbol)
    return df, 'broker' if not df.empty else 'none'

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    ag = np.mean(gains[:period])
    al = np.mean(losses[:period])
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al <= 0:
        return 100.0 if ag > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + ag / al)

def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - closes[:-1])
    tr3 = np.abs(lows[1:] - closes[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    return float(np.mean(tr[-period:]))

def trend_alignment(symbol):
    timeframes = [
        (mt5.TIMEFRAME_H1, '1H'),
        (mt5.TIMEFRAME_H4, '4H'),
        (mt5.TIMEFRAME_D1, '1D'),
    ]
    trends = []
    for tf, label in timeframes:
        df = fetch_broker(symbol, timeframe=tf, count=60)
        if df.empty or len(df) < 20:
            continue
        closes = df['close'].values
        sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
        last = float(closes[-1])
        if sma20 and sma50 and last:
            if last > sma20 > sma50:
                trends.append('BULL')
            elif last < sma20 < sma50:
                trends.append('BEAR')
            else:
                trends.append('MIXED')
        else:
            trends.append('MIXED')
    if not trends:
        return None
    if all(t == 'BULL' for t in trends):
        return 'BULL'
    if all(t == 'BEAR' for t in trends):
        return 'BEAR'
    if trends.count('BULL') >= 2:
        return 'BULL'
    if trends.count('BEAR') >= 2:
        return 'BEAR'
    return 'MIXED'

def conviction_score(rsi_val, atr_val, last, sma20, sma50, trend, backtest_score, backtested=False):
    score = 0.0
    # Reward moderate RSI aligned with trend, penalize extremes
    if trend == 'BULL':
        if 40 <= rsi_val <= 60:
            score += 2.0
        elif 30 <= rsi_val < 40 or 60 < rsi_val <= 70:
            score += 1.0
        elif rsi_val > 75:
            score -= 1.0  # overbought penalty
    elif trend == 'BEAR':
        if 40 <= rsi_val <= 60:
            score += 2.0
        elif 30 <= rsi_val <= 40 or 70 > rsi_val >= 60:
            score += 1.0
        elif rsi_val < 25:
            score -= 1.0  # oversold penalty
    if trend == 'BULL' and last and sma20 and sma50 and last > sma20 > sma50:
        score += 2.0
    elif trend == 'BEAR' and last and sma20 and sma50 and last < sma20 < sma50:
        score += 2.0
    if atr_val and last:
        atr_pct = (atr_val / last) * 100 if last else 0
        if 0.5 <= atr_pct <= 3.0:
            score += 1.0
        elif atr_pct > 5.0:
            score -= 0.5  # excessive volatility penalty
    if backtested:
        if backtest_score and backtest_score >= 80:
            score += 3.0
        elif backtest_score and backtest_score >= 60:
            score += 2.0
        elif backtest_score and backtest_score >= 40:
            score += 1.0
    return round(score, 2)

# Load backtest data
CONVICTION_DB = {}
if HTF_DB.exists():
    try:
        con = sqlite3.connect(str(HTF_DB))
        cur = con.cursor()
        cur.execute('SELECT symbol, side, tech_score, fund_score, news_score, backtest_score, conviction, grade, backtested, entry, sl, tp, rr FROM htf_conviction WHERE asof=(SELECT max(asof) FROM htf_conviction)')
        for row in cur.fetchall():
            CONVICTION_DB[row[0]] = {
                'side': row[1], 'tech_score': row[2], 'fund_score': row[3], 'news_score': row[4],
                'backtest_score': row[5], 'conviction': row[6], 'grade': row[7], 'backtested': bool(row[8]),
                'entry': row[9], 'sl': row[10], 'tp': row[11], 'rr': row[12]
            }
        con.close()
    except Exception as e:
        print('DB load warning', e)

# Main scan
results = {
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'session': 'nightshift',
    'scope': 'indices, forex, precious_metals, metals, crypto',
    'universe_size': len(UNIVERSE),
    'sectors': {},
    'viable_setups': [],
}

print('Initializing MT5...')
mt5_ready = init_mt5()
print('MT5 ready:', mt5_ready)

for symbol, sector in UNIVERSE.items():
    brokers = SECTOR_BROKER.get(sector, [])
    df, source = fetch_data(symbol)
    if df.empty or len(df) < 20:
        results['sectors'][symbol] = {
            'symbol': symbol, 'sector': sector, 'broker_routing': brokers,
            'data_source': source, 'status': 'NO_DATA'
        }
        print(f'  NO_DATA {symbol}')
        continue

    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    last = float(closes[-1])
    r = rsi(closes)
    a = atr(highs, lows, closes)
    sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
    sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None

    cb = CONVICTION_DB.get(symbol, {})
    bt_score = cb.get('backtest_score')
    bt_grade = cb.get('grade')
    bt_backtested = cb.get('backtested', False)

    rec = {
        'symbol': symbol,
        'sector': sector,
        'broker_routing': brokers,
        'data_source': source,
        'last': round(last, 6),
        'rsi': round(r, 2),
        'atr': round(a, 6) if a is not None else None,
        'sma20': round(sma20, 6) if sma20 else None,
        'sma50': round(sma50, 6) if sma50 else None,
        'trend': None,
        'backtest_grade': bt_grade,
        'backtest_score': bt_score,
        'backtested': bt_backtested,
        'conviction': 0.0,
        'viable': False,
        'reason': [],
    }
    results['sectors'][symbol] = rec

# Second pass: compute trend for broker-accessible symbols only
print('Computing multi-timeframe trends...')
for symbol in UNIVERSE.keys():
    rec = results['sectors'].get(symbol)
    if not rec or rec.get('status') == 'NO_DATA':
        continue
    if symbol in BROKER_ONLY or symbol in {'^DJI','^IXIC','^GSPC','^RUT','^VIX','^VXN','US30','US100','US500','DXY','XAUUSD','XAGUSD','EURUSD=X','GBPUSD=X','USDJPY=X','AUDUSD=X','USDCAD=X','USDCHF=X','NZDUSD=X','GBPUSD=X','EURJPY=X','GBPJPY=X'}:
        trend = trend_alignment(symbol)
        rec['trend'] = trend
        r = rec.get('rsi', 50)
        a = rec.get('atr')
        last = rec.get('last')
        sma20 = rec.get('sma20')
        sma50 = rec.get('sma50')
        conv = conviction_score(r, a, last, sma20, sma50, trend, rec.get('backtest_score'), rec.get('backtested'))
        rec['conviction'] = conv

        viable = False
        reason = []
        if r < 30:
            viable = True
            reason.append('RSI_OVERSOLD')
        elif r > 70:
            viable = True
            reason.append('RSI_OVERBOUGHT')
        # Trend confirmation
        if trend == 'BULL' and last and sma20 and sma50 and last > sma20 > sma50:
            viable = True
            reason.append('BULL_TREND')
        elif trend == 'BEAR' and last and sma20 and sma50 and last < sma20 < sma50:
            viable = True
            reason.append('BEAR_TREND')
        if a is None or a == 0:
            viable = False
            reason = [x for x in reason if x not in ('RSI_OVERSOLD', 'RSI_OVERBOUGHT')]
        # Confidence downgrade for broker-only symbols without aligned trend
        if symbol in BROKER_ONLY and viable and trend == 'MIXED':
            reason.append('LOW_CONFIDENCE')
        rec['viable'] = viable
        rec['reason'] = reason
        if viable:
            results['viable_setups'].append(rec)
        print(f'  {symbol:12} {rec.get("sector",""):18} last={last:10.4f} rsi={r:6.2f} trend={str(trend):6} conv={conv:4} viable={viable} src={rec.get("data_source")}')

results['viable_setups'] = sorted(results['viable_setups'], key=lambda x: x['conviction'], reverse=True)
results['viable_count'] = len(results['viable_setups'])
results['scanned_count'] = len([k for k, v in results['sectors'].items() if v.get('status') != 'NO_DATA'])

OUT.write_text(json.dumps(results, indent=2), encoding='utf-8')
print('\nWROTE', OUT)
print('SCANNED', results['scanned_count'], 'VIABLE', results['viable_count'])
print('Top 15:')
for x in results['viable_setups'][:15]:
    print(f"  {x['symbol']:12} {x['sector']:18} last={x['last']:10.4f} rsi={x['rsi']:6.2f} trend={str(x.get('trend')):6} conv={x['conviction']:4} src={x['data_source']}")
