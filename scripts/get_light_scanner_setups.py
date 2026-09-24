#!/usr/bin/env python3
"""
get_light_scanner_setups.py
- Scans the universe using the light scanner logic (same as periodic_sector_scan_and_trade_execution_light.py)
- Outputs top candidates with entry, SL, TP (no order placement)
- Incorporates symbol weights from backtested trades to bias scan toward historically winning symbols
"""
import json, sys, time, traceback, os
from pathlib import Path
from datetime import datetime, timezone

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
SCAN_OUT = BASE / 'workflow' / f'light_scanner_setups_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
sys.path.insert(0, str(BASE / 'scripts'))
from mt5_connect import connect as mt5_connect, shutdown as mt5_shutdown
import MetaTrader5 as mt5

# Path to symbol weights from backtest
WEIGHTS_PATH = Path(os.path.expanduser('~/AppData/Local/hermes/broker_trades/symbol_weights.json'))

def load_symbol_weights():
    """Load symbol weights from JSON file. Returns dict symbol->weight (default 1.0)."""
    if WEIGHTS_PATH.exists():
        try:
            return json.loads(WEIGHTS_PATH.read_text())
        except Exception as e:
            print(f"Warning: Could not load symbol weights: {e}")
    return {}

UNIVERSE = [
    'EURUSD','GBPUSD','USDCHF','USDJPY','USDCAD','AUDUSD','NZDUSD','EURGBP','EURJPY','GBPJPY',
    'XAUUSD','XAGUSD','UKOIL.CASH','USOIL.CASH','NATGAS.CASH',
    'US30.CASH','US500.CASH','NAS100.CASH','UK100.CASH','GER40.CASH','HK50.CASH','JP225.CASH',
    'BTCUSD','ETHUSD','SOLUSD','XRPUSD','ADAUSD','DOGEUSD','DOTUSD','ETCUSD','LTCUSD',
    'AAPL','AMZN','GOOG','MSFT','TSLA','NVDA','META','NFLX','AMD','INTC','JPM','BAC','DIS','WMT','V','BA','RTX','LMT','PLTR','IBM','SNOW','ASML','XOM','CVX','FDX',
    'SPY','QQQ','IWM','DIA','TLT','IEF','HYG','LQD','GLD','SLV','USO','UNG','DBA',
    'ES','NQ','YM','RTY','CL','GC','SI'
]

def digits_for_sym(sym):
    s = sym.upper()
    if any(k in s for k in ['JPY','JP225']): return 3
    if any(k in s for k in ['XAU','XAG','XPT','XPD']): return 2
    if any(k in s for k in ['BTC','ETH']): return 2
    if any(k in s for k in ['US30','US500','NAS100','UK100','GER40','HK50','ES','NQ','YM','RTY']): return 1
    return 5

def round_price(sym, price, digits=None):
    d = digits if digits is not None else digits_for_sym(sym)
    return round(float(price), d)

def ema(arr, n):
    if len(arr) < n: return None
    k = 2.0 / (n + 1.0)
    e = sum(arr[:n]) / float(n)
    out = [e]
    for v in arr[n:]:
        e = float(v) * k + e * (1.0 - k)
        out.append(e)
    return out

def rsi14(closes):
    if len(closes) < 15: return None
    g = [max(0.0, c2 - c1) for c1, c2 in zip(closes, closes[1:])]
    l = [max(0.0, c1 - c2) for c1, c2 in zip(closes, closes[1:])]
    ag = sum(g[-14:]) / 14.0
    al = sum(l[-14:]) / 14.0
    if al == 0.0: return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)

def atr14(highs, lows, closes):
    if len(closes) < 15: return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(float(highs[i]) - float(lows[i]), abs(float(highs[i]) - float(closes[i - 1])), abs(float(lows[i]) - float(closes[i - 1])))
        trs.append(tr)
    return sum(trs[-14:]) / 14.0

def build_feasible_universe(conn):
    feasible = []
    for sym in UNIVERSE:
        si = conn.symbol_info(sym)
        if not si: continue
        conn.symbol_select(sym, True)
        tick = conn.symbol_info_tick(sym)
        if tick and tick.bid > 0 and tick.ask > 0:
            feasible.append(sym)
    return feasible

def scan_symbol(conn, sym):
    rates = conn.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 120)
    if rates is None or len(rates) < 70:
        return None
    closes = [float(r[4]) for r in rates]
    highs = [float(r[2]) for r in rates]
    lows = [float(r[3]) for r in rates]
    last = closes[-1]
    rsi = rsi14(closes)
    atr = atr14(highs, lows, closes)
    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    vwap50 = sum((highs[i] + lows[i] + closes[i]) / 3.0 * float(rates[i][5]) for i in range(-50, 0)) / sum(float(rates[i][5]) for i in range(-50, 0)) if len(rates) >= 50 else None
    tick = conn.symbol_info_tick(sym)
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        return None
    if any(v is None for v in [last, rsi, atr, e20, e50, vwap50]) or atr <= 0:
        return None
    return {
        'symbol': sym, 'last': last, 'bid': float(tick.bid), 'ask': float(tick.ask),
        'rsi14': rsi, 'atr14': atr, 'ema20': e20[-1], 'ema50': e50[-1], 'vwap50': vwap50
    }

def score_candidate(r):
    sym = r['symbol']; last = r['last']; rsi = r['rsi14']; atr = r['atr14']
    e20 = r['ema20']; e50 = r['ema50']; vwap50 = r['vwap50']
    digits = digits_for_sym(sym)
    pt = 10**(-digits)
    buf = max(0.5 * atr, 2.0 * pt)
    score = 0
    side = None
    sl = tp = None
    if rsi < 35 and last < e20 < e50 and last < vwap50:
        side = 'buy'
        sl = round_price(sym, last - buf, digits)
        tp = round_price(sym, last + 2.0 * buf, digits)
        rr = abs(tp - last) / abs(last - sl) if abs(last - sl) > 0 else 0.0
        if rr >= 1.5:
            score = (35.0 - rsi) + max(0.0, (e20 - last) / atr) + max(0.0, (vwap50 - last) / atr)
    if rsi > 65 and last > e20 > e50 and last > vwap50:
        side = 'sell'
        sl = round_price(sym, last + buf, digits)
        tp = round_price(sym, last - 2.0 * buf, digits)
        rr = abs(tp - last) / abs(last - sl) if abs(last - sl) > 0 else 0.0
        if rr >= 1.5:
            s = (rsi - 65.0) + max(0.0, (last - e20) / atr) + max(0.0, (last - vwap50) / atr)
            if s > score:
                score = s
                side = 'sell'
                sl = round_price(sym, last + buf, digits)
                tp = round_price(sym, last - 2.0 * buf, digits)
    if side and score > 0:
        return {'symbol': sym, 'side': side, 'score': score, 'entry': last, 'sl': sl, 'tp': tp,
                'rsi14': rsi, 'atr14': atr, 'bid': r['bid'], 'ask': r['ask']}
    return None

def main():
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    print(f'[{ts}] Light scanner setups start')

    # Load symbol weights
    symbol_weights = load_symbol_weights()
    if symbol_weights:
        print(f"Loaded symbol weights for {len(symbol_weights)} symbols")
    else:
        print("No symbol weights found, using default weight 1.0 for all symbols")

    # Try FTMO first, then Capital
    ftmo = cap = None
    try:
        ftmo = mt5_connect('ftmo')
        print('FTMO connected')
    except Exception as e:
        print(f'FTMO connect failed: {e}')
    try:
        cap = mt5_connect('capital')
        print('Capital connected')
    except Exception as e:
        print(f'Capital connect failed: {e}')

    scanner = ftmo or cap
    if not scanner:
        print('No MT5 broker available for scanning.')
        return

    feasible = build_feasible_universe(scanner)
    print(f'Feasible symbols: {len(feasible)}')

    candidates = []
    for sym in feasible:
        try:
            r = scan_symbol(scanner, sym)
            if not r: continue
            c = score_candidate(r)
            if c:
                # Apply symbol weight
                weight = symbol_weights.get(sym, 1.0)
                c['score'] = c['score'] * weight
                c['weight'] = weight
                candidates.append(c)
        except Exception as e:
            print(f'Error scanning {sym}: {e}')
            pass

    candidates.sort(key=lambda x: x['score'], reverse=True)
    top_candidates = candidates[:10]  # top 10
    print(f'Top candidates: {len(top_candidates)}')

    # Prepare output
    out_data = {
        'ts': ts,
        'scanner': 'ftmo' if ftmo else 'capital',
        'feasible_count': len(feasible),
        'candidate_count': len(candidates),
        'setups': []
    }
    for c in top_candidates:
        out_data['setups'].append({
            'symbol': c['symbol'],
            'side': c['side'],
            'entry': round(c['entry'], 5),
            'sl': round(c['sl'], 5),
            'tp': round(c['tp'], 5),
            'score': round(c['score'], 2),
            'weight': round(c.get('weight', 1.0), 3),
            'rsi14': round(c['rsi14'], 2),
            'atr14': round(c['atr14'], 5),
            'bid': c['bid'],
            'ask': c['ask']
        })

    SCAN_OUT.write_text(json.dumps(out_data, indent=2), encoding='utf-8')
    print(f'WROTE setups: {SCAN_OUT}')

    # Print setups
    for s in out_data['setups']:
        print(f"{s['symbol']} {s['side'].upper()} entry={s['entry']} SL={s['sl']} TP={s['tp']} score={s['score']} weight={s['weight']}")

    mt5_shutdown()
    print('=== DONE ===')

if __name__ == '__main__':
    main()