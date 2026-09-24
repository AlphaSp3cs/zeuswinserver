#!/usr/bin/env python3
"""
Nightshift all-sector scanner and executor.
Scans: all forex pairs, commodities, indices, crypto on Capital.com RIGHT MT5.
Executes high-conviction setups on FTMO LEFT and Capital.com RIGHT.
Removes duplicates and manages SL/TP.
"""
import json, time, math
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

FTMO_TERMINAL = r'REDACTED-PATH'
CAP_TERMINAL = r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
TS = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
REPORT = BASE / 'nightshift_scan_report.md'

TF = mt5.TIMEFRAME_H1
HIST_BARS = 200

def calc_ema(closes, period):
    ema = [closes[0]]
    k = 2 / (period + 1)
    for c in closes[1:]:
        ema.append(c * k + ema[-1] * (1 - k))
    return ema

def calc_atr(highs, lows, closes, period=14):
    tr = []
    for i in range(1, len(closes)):
        h = max(highs[i], closes[i-1])
        l = min(lows[i], closes[i-1])
        tr.append(h - l)
    if len(tr) < period:
        return sum(tr) / len(tr) if tr else 0.0
    return sum(tr[-period:]) / period

def calc_rsi(closes, period=14):
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def backtest_simple(symbol, rates, side, sl, tp, holding_bars=24):
    wins = 0
    losses = 0
    trades = 0
    closes = [r['close'] for r in rates]
    highs = [r['high'] for r in rates]
    lows = [r['low'] for r in rates]
    for i in range(len(rates) - holding_bars):
        entry = closes[i]
        if side == 'LONG':
            for j in range(i+1, i+1+holding_bars):
                if lows[j] <= sl:
                    losses += 1
                    trades += 1
                    break
                if highs[j] >= tp:
                    wins += 1
                    trades += 1
                    break
        else:
            for j in range(i+1, i+1+holding_bars):
                if highs[j] >= sl:
                    losses += 1
                    trades += 1
                    break
                if lows[j] <= tp:
                    wins += 1
                    trades += 1
                    break
    if trades == 0:
        return 0, 0, 0
    win_rate = wins / trades
    expectancy = (win_rate * (tp - entry)) - ((1 - win_rate) * (entry - sl))
    return win_rate, expectancy, trades

def tradegate(win_rate, expectancy, rsi, price, ema20, ema50, atr):
    reasons = []
    if win_rate < 0.36:
        reasons.append('win_rate_low')
    if expectancy <= 0:
        reasons.append('expectancy_negative')
    if rsi is not None and (rsi < 30 or rsi > 85):
        reasons.append('rsi_extreme')
    if atr == 0:
        reasons.append('atr_zero')
    if ema20 is None or ema50 is None:
        reasons.append('missing_ema')
    return len(reasons) == 0, reasons

# Initialize Capital.com RIGHT
mt5.shutdown()
time.sleep(1)
ok = mt5.initialize(CAP_TERMINAL)
if not ok:
    print('init failed', mt5.last_error())
    exit(1)

symbols = [s.name for s in mt5.symbols_get() if s.visible]
forex = [s for s in symbols if any(x in s for x in ['USD','EUR','GBP','JPY','AUD','NZD','CHF','CAD'])]
commodities = [s for s in symbols if any(x in s for x in ['XAU','XAG','USOIL','UKOIL','NATGAS','GAS','COPPER','WHEAT','CORN','SOY'])]
indices = [s for s in symbols if any(x in s for x in ['US500','DE40','HK50','JP225','UK100','US100','US30'])]
crypto = [s for s in symbols if any(x in s for x in ['BTC','ETH','XRP','SOL','DOGE','DOT','ADA','LINK','BNB','LTC'])]

all_universe = {
    'forex': forex,
    'commodities': commodities,
    'indices': indices,
    'crypto': crypto,
}

scan_results = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'universe': {}}
high_conviction = []

for category, sym_list in all_universe.items():
    scan_results['universe'][category] = []
    for symbol in sym_list:
        rates = mt5.copy_rates_from_pos(symbol, TF, 0, HIST_BARS)
        if rates is None or len(rates) < 50:
            continue
        closes = [r['close'] for r in rates]
        highs = [r['high'] for r in rates]
        lows = [r['low'] for r in rates]
        ema20 = calc_ema(closes, 20)[-1]
        ema50 = calc_ema(closes, 50)[-1]
        atr = calc_atr(highs, lows, closes)
        rsi = calc_rsi(closes)
        price = closes[-1]
        side = None
        if price > ema20 > ema50:
            side = 'LONG'
        elif price < ema20 < ema50:
            side = 'SHORT'
        sl_long = price - 1.5 * atr if side == 'LONG' else None
        tp_long = price + 3.0 * atr if side == 'LONG' else None
        sl_short = price + 1.5 * atr if side == 'SHORT' else None
        tp_short = price - 3.0 * atr if side == 'SHORT' else None
        if side:
            win_rate, expectancy, trades = backtest_simple(symbol, rates, side, sl_long or sl_short, tp_long or tp_short)
        else:
            win_rate, expectancy, trades = 0, 0, 0
        passed, reasons = tradegate(win_rate, expectancy, rsi, price, ema20, ema50, atr)
        entry = {
            'symbol': symbol,
            'price': price,
            'atr': atr,
            'rsi': rsi,
            'ema20': ema20,
            'ema50': ema50,
            'side': side,
            'formations': ['trend_aligned'] if side else [],
            'backtest': {'win_rate': round(win_rate, 2), 'expectancy': round(expectancy, 2), 'trades': trades},
            'tradegate': {'pass': passed, 'reasons': reasons},
            'sl_long': sl_long,
            'tp_long': tp_long,
            'sl_short': sl_short,
            'tp_short': tp_short,
        }
        scan_results['universe'][category].append(entry)
        if passed and side:
            high_conviction.append(entry)
    time.sleep(0.1)

mt5.shutdown()

# Save scan
scan_path = BASE / 'artifacts' / f'nightshift_scan_{TS}.json'
scan_path.write_text(json.dumps(scan_results, indent=2), encoding='utf-8')

# Deduplicate high-conviction
seen = set()
unique = []
for it in high_conviction:
    if it['symbol'] not in seen:
        seen.add(it['symbol'])
        unique.append(it)
high_conviction = unique

# Execute on both brokers
def place(terminal, symbol, side, sl, tp):
    mt5.shutdown()
    time.sleep(0.5)
    ok = mt5.initialize(terminal)
    if not ok:
        return {'terminal': terminal, 'status': 'error', 'error': 'init_failed'}
    info = mt5.symbol_info(symbol)
    if not info or not info.visible:
        mt5.shutdown()
        return {'terminal': terminal, 'status': 'error', 'error': 'symbol_not_visible'}
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        mt5.shutdown()
        return {'terminal': terminal, 'status': 'error', 'error': 'no_tick'}
    price = tick.ask if side == 'LONG' else tick.bid
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': 0.01,
        'type': mt5.ORDER_TYPE_BUY if side == 'LONG' else mt5.ORDER_TYPE_SELL,
        'price': price,
        'sl': round(sl, info.digits),
        'tp': round(tp, info.digits),
        'deviation': 20,
        'magic': 20260804,
        'comment': 'nightshift',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    mt5.shutdown()
    if res is None:
        return {'terminal': terminal, 'status': 'error', 'error': 'order_send_none'}
    return {'terminal': terminal, 'status': 'executed' if res.retcode == mt5.TRADE_RETCODE_DONE else 'failed', 'retcode': int(res.retcode), 'order': int(res.order), 'price': price, 'sl': round(sl, info.digits), 'tp': round(tp, info.digits)}

# Determine available brokers for each symbol
broker_map = {}
for sym in symbols:
    avail = []
    mt5.shutdown()
    time.sleep(0.2)
    ok = mt5.initialize(FTMO_TERMINAL)
    if ok:
        info = mt5.symbol_info(sym)
        if info and info.visible:
            avail.append(FTMO_TERMINAL)
        mt5.shutdown()
    mt5.shutdown()
    time.sleep(0.2)
    ok = mt5.initialize(CAP_TERMINAL)
    if ok:
        info = mt5.symbol_info(sym)
        if info and info.visible:
            avail.append(CAP_TERMINAL)
        mt5.shutdown()
    broker_map[sym] = avail

results = []
for it in high_conviction:
    sym = it['symbol']
    sl = it['sl_long'] if it['side'] == 'LONG' else it['sl_short']
    tp = it['tp_long'] if it['side'] == 'LONG' else it['tp_short']
    for terminal in broker_map.get(sym, []):
        res = place(terminal, sym, it['side'], sl, tp)
        res['symbol'] = sym
        res['side'] = it['side']
        res['rsi'] = it['rsi']
        res['win_rate'] = it['backtest']['win_rate']
        res['expectancy'] = it['backtest']['expectancy']
        results.append(res)
        time.sleep(0.5)

# Build report
lines = []
lines.append('# Nightshift Scan Report — 2026-08-04')
lines.append(f'Generated: {datetime.now(timezone.utc).isoformat()}')
lines.append('')
lines.append('## High Conviction Setups')
if not high_conviction:
    lines.append('No setups passed tradegate.')
else:
    for it in high_conviction:
        sl = it['sl_long'] if it['side'] == 'LONG' else it['sl_short']
        tp = it['tp_long'] if it['side'] == 'LONG' else it['tp_short']
        lines.append(f"- {it['symbol']} {it['side']} | entry={it['price']} | ATR={it['atr']:.5f} | RSI={it['rsi']:.2f} | SL={sl:.5f} | TP={tp:.5f} | win_rate={it['backtest']['win_rate']} | expectancy={it['backtest']['expectancy']}")
lines.append('')
lines.append('## Execution Results')
for res in results:
    term = 'FTMO LEFT' if 'FTMO' in res.get('terminal', '') else 'Capital.com RIGHT'
    lines.append(f"- {res.get('symbol')} on {term}: {res.get('status')} retcode={res.get('retcode')} order={res.get('order')} price={res.get('price')} sl={res.get('sl')} tp={res.get('tp')}")
lines.append('')
lines.append('## Scan Summary')
for cat, items in scan_results['universe'].items():
    total = len(items)
    candidates = sum(1 for i in items if i['side'])
    high = sum(1 for i in items if i['tradegate']['pass'])
    lines.append(f"- {cat}: {total} scanned, {candidates} candidates, {high} high-conviction")
lines.append('')
lines.append('## Notes')
lines.append('All SL/TP zones are ATR-based. Use limit entries where possible.')
lines.append('Cross-broker execution attempted on FTMO LEFT and Capital.com RIGHT.')

report_text = '\n'.join(lines)
REPORT.write_text(report_text, encoding='utf-8')
print('WROTE', scan_path)
print('WROTE', REPORT)
print(json.dumps({'high_conviction_count': len(high_conviction), 'high_conviction_symbols': [h['symbol'] for h in high_conviction]}, indent=2))
print(report_text)