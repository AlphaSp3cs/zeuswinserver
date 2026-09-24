#!/usr/bin/env python3
"""
Execute high-conviction setups across FTMO LEFT and Capital.com RIGHT.
Selects top distinct setups by score and sends market orders with SL/TP.
"""
import json, time
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

FTMO_TERMINAL = r'REDACTED-PATH'
CAP_TERMINAL = r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
TS = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
REPORT = BASE / 'high_conviction_execution_report.md'

scan_path = sorted(BASE.glob('artifacts/high_conviction_scan_*.json'))[-1]
scan = json.loads(scan_path.read_text())

# Flatten and score
rows=[]
for cat, items in scan['universe'].items():
    seen=set()
    for it in items:
        sym=it['symbol']
        if sym in seen or not it.get('side'):
            continue
        seen.add(sym)
        bt=it['backtest']
        score=0
        if bt.get('win_rate',0) >= 0.50: score += 2
        if bt.get('expectancy',0) > 0: score += 2
        rsi=it.get('rsi') or 0
        if 45 <= rsi <= 75: score += 1
        if it.get('atr',0) > 0: score += 1
        rows.append((score, sym, cat, it['side'], it['price'], it['atr'], it['sl_long'], it['tp_long'], it['sl_short'], it['tp_short'], rsi, bt))

# Deduplicate by symbol, keep highest score
best={}
for r in rows:
    sym=r[1]
    if sym not in best or r[0] > best[sym][0]:
        best[sym]=r
selected=sorted(best.values(), key=lambda x: x[0], reverse=True)[:5]

def place(terminal, symbol, side, volume, sl, tp):
    mt5.shutdown()
    time.sleep(1)
    ok=mt5.initialize(terminal)
    if not ok:
        return {'terminal': terminal, 'status':'error','error':'init_failed'}
    info=mt5.symbol_info(symbol)
    if not info or not info.visible:
        mt5.shutdown()
        return {'terminal': terminal, 'status':'error','error':'symbol_not_visible'}
    tick=mt5.symbol_info_tick(symbol)
    if not tick:
        mt5.shutdown()
        return {'terminal': terminal, 'status':'error','error':'no_tick'}
    price=tick.ask if side=='LONG' else tick.bid
    req={
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': mt5.ORDER_TYPE_BUY if side=='LONG' else mt5.ORDER_TYPE_SELL,
        'price': price,
        'sl': round(sl, info.digits),
        'tp': round(tp, info.digits),
        'deviation': 20,
        'magic': 20260804,
        'comment': 'high_conviction',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res=mt5.order_send(req)
    mt5.shutdown()
    if res is None:
        return {'terminal': terminal, 'status':'error','error':'order_send_none'}
    return {'terminal': terminal, 'status':'executed' if res.retcode==mt5.TRADE_RETCODE_DONE else 'failed', 'retcode': int(res.retcode), 'order': int(res.order), 'price': price, 'sl': round(sl, info.digits), 'tp': round(tp, info.digits)}

results=[]
for r in selected:
    score, sym, cat, side, price, atr, sl_l, tp_l, sl_s, tp_s, rsi, bt = r
    sl = sl_l if side == 'LONG' else sl_s
    tp = tp_l if side == 'LONG' else tp_s
    if not sl or not tp:
        continue
    # Determine available terminals for symbol
    terminals=[]
    if sym in ['USDCAD','LTCUSD']:
        terminals.append(FTMO_TERMINAL)
    if sym in ['ETHUSD','LTCUSD','USDCAD']:
        terminals.append(CAP_TERMINAL)
    # Remove duplicate terminal if same broker
    for term in list(dict.fromkeys(terminals)):
        res=place(term, sym, side, 0.01, sl, tp)
        res.update({'symbol': sym, 'side': side, 'score': score, 'atr': atr, 'rsi': rsi, 'win_rate': bt.get('win_rate'), 'expectancy': bt.get('expectancy')})
        results.append(res)
        time.sleep(0.5)

lines=[]
lines.append('# High Conviction Execution Report')
lines.append(f'Generated: {datetime.now(timezone.utc).isoformat()}')
lines.append('')
lines.append('## Selected Setups')
for r in selected:
    score, sym, cat, side, price, atr, sl_l, tp_l, sl_s, tp_s, rsi, bt = r
    sl = sl_l if side == 'LONG' else sl_s
    tp = tp_l if side == 'LONG' else tp_s
    lines.append(f"- {sym} {side} score={score} rsi={rsi} atr={atr} sl={sl} tp={tp} win_rate={bt.get('win_rate')} expectancy={bt.get('expectancy')}")
lines.append('')
lines.append('## Execution Results')
for res in results:
    term_name = res['terminal'].replace('C:\\Program Files\\', '')
    lines.append(f"- {res['symbol']} on {term_name}: {res['status']} retcode={res.get('retcode')} order={res.get('order')} price={res.get('price')} sl={res.get('sl')} tp={res.get('tp')}")
lines.append('')
lines.append('## Notes')
lines.append('Top distinct setups selected by score. Limited to symbols available on FTMO LEFT and/or Capital.com RIGHT.')
lines.append('IBKR/Alpaca/eToro not used due to prior limitations.')

report_text='\n'.join(lines)
REPORT.write_text(report_text, encoding='utf-8')
print('WROTE', REPORT)
print(report_text)