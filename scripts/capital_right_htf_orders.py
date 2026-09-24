#!/usr/bin/env python3
"""
Place high-timeframe long DCA orders on Capital RIGHT MT5.
Final version with proper position closing and current market prices.
"""
import json, datetime
from pathlib import Path

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
creds = json.loads((BASE / '.broker_creds_secure.json').read_text())
cap = creds['capital']

import MetaTrader5 as mt5

mt5.initialize(
    login=int(cap['login']),
    password=cap['password'],
    server=cap['server'],
    portable=True,
    timeout=15000,
)

acct = mt5.account_info()
print(f'ACCOUNT: {acct.login} | {acct.server} | balance={acct.balance} equity={acct.equity} | free_margin={acct.margin_free}')

# High-timeframe long setups with current market prices
# SL = 5% below, TP = 10% above entry
setups = [
    # Metals - highest conviction AI/DC metals
    ('XCUUSD', 0.01, 'Copper CFD - AI data center power'),
    ('XAUUSD', 0.01, 'Gold - safe haven, central banks'),
    ('XAGUSD', 0.01, 'Silver - industrial/monetary'),
    
    # Crypto - institutional focus
    ('BTCUSD', 0.01, 'Bitcoin digital gold'),
    ('ETHUSD', 0.01, 'Ethereum smart contracts'),
    ('XRPUSD', 10.0, 'XRP CBDC partnerships'),
    ('SOLUSD', 0.10, 'Solana high-throughput'),
    ('XMRUSD', 0.01, 'Monero privacy'),
    
    # Forex majors
    ('EURUSD', 10000.0, 'EUR/USD major'),
    ('GBPUSD', 10000.0, 'GBP/USD major'),
    ('USDCHF', 10000.0, 'USD/CHF safe haven'),
    ('USDJPY', 10000.0, 'USD/JPY major'),
    ('USDCAD', 10000.0, 'USD/CAD oil-linked'),
    ('AUDUSD', 10000.0, 'AUD/USD commodity'),
]

results = []
for raw_sym, qty_base, notes in setups:
    info = mt5.symbol_info(raw_sym)
    if info is None:
        print(f'SKIP {raw_sym}: symbol not found')
        results.append({'symbol': raw_sym, 'status': 'SKIP', 'reason': 'symbol_not_found', 'notes': notes})
        continue

    sym = info.name
    if not info.visible or not info.select:
        print(f'SKIP {raw_sym} -> {sym}: visible={info.visible}, select={info.select}')
        results.append({'symbol': raw_sym, 'broker_symbol': sym, 'status': 'SKIP', 'reason': f'visible={info.visible},select={info.select}', 'notes': notes})
        continue

    if info.trade_mode == mt5.SYMBOL_TRADE_MODE_LONGONLY:
        side = 'LONG'
    elif info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
        side = 'LONG'
    else:
        print(f'SKIP {raw_sym} -> {sym}: trade_mode={info.trade_mode}')
        results.append({'symbol': raw_sym, 'broker_symbol': sym, 'status': 'SKIP', 'reason': f'trade_mode={info.trade_mode}', 'notes': notes})
        continue

    # Get current market price
    tick = mt5.symbol_info_tick(sym)
    entry = tick.ask
    digits = info.digits

    # Calculate SL/TP based on high timeframe analysis
    # SL = 5% below entry, TP = 10% above entry
    sl = round(entry * 0.95, digits)
    tp = round(entry * 1.10, digits)

    # Volume constraints
    qty = max(info.volume_min, min(info.volume_max, qty_base))
    qty = round(qty / info.volume_step) * info.volume_step
    qty = float(qty)

    # Margin check
    margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, sym, qty, entry)
    if margin is None:
        print(f'SKIP {raw_sym} -> {sym}: margin calc failed')
        results.append({'symbol': raw_sym, 'broker_symbol': sym, 'status': 'SKIP', 'reason': 'margin_calc_failed', 'notes': notes})
        continue

    if margin > acct.margin_free * 0.9:
        print(f'SKIP {raw_sym} -> {sym}: margin {margin:.2f} > 90% free')
        results.append({'symbol': raw_sym, 'broker_symbol': sym, 'status': 'SKIP', 'reason': 'insufficient_margin', 'margin': float(margin), 'notes': notes})
        continue

    request = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': qty,
        'type': mt5.ORDER_TYPE_BUY,
        'price': entry,
        'sl': sl,
        'tp': tp,
        'deviation': 10,
        'magic': 20260812,
        'comment': f'HTF_LONG {notes}',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f'EXECUTED {raw_sym} -> {sym} LONG qty={qty} @ {entry} SL={sl} TP={tp} ticket={result.order}')
        results.append({
            'symbol': raw_sym,
            'broker_symbol': sym,
            'broker': 'CAPITAL_RIGHT',
            'status': 'FILLED',
            'ticket': result.order,
            'deal': result.deal,
            'qty': qty,
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'side': side,
            'notes': notes,
        })
    else:
        print(f'FAILED {raw_sym} -> {sym}: {result.retcode if result else "None"} {result.comment if result else "None"}')
        results.append({
            'symbol': raw_sym,
            'broker_symbol': sym,
            'broker': 'CAPITAL_RIGHT',
            'status': 'FAILED',
            'retcode': result.retcode if result else None,
            'comment': result.comment if result else None,
            'qty': qty,
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'side': side,
            'notes': notes,
        })

out = BASE / f'CAPITAL_RIGHT_HTF_ORDERS_{datetime.date.today().isoformat()}.json'
out.write_text(json.dumps({'timestamp': datetime.datetime.utcnow().isoformat() + 'Z', 'results': results}, indent=2))
print(f'\nWROTE {out}')
print(f'FILLED: {sum(1 for r in results if r["status"]=="FILLED")} | FAILED: {sum(1 for r in results if r["status"]=="FAILED")} | SKIPPED: {sum(1 for r in results if r["status"]=="SKIP")}')

# Show all open positions
positions = mt5.positions_get()
print(f'\nOpen positions: {len(positions) if positions else 0}')
if positions:
    for p in positions:
        print(f'  {p.symbol}: {p.type} {p.volume} @ {p.price_open} SL={p.sl} TP={p.tp} ticket={p.ticket}')

mt5.shutdown()
