#!/usr/bin/env python3
"""
execute_sector_ticket_20260819.py
Execute exact tickets from sector_sorted_execution_ticket_20260819T1218Z.json
on CAPITAL-RIGHT MT5 for the backtested crypto setups.
"""
import json, datetime, traceback
from pathlib import Path

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
TICKET_PATH = BASE / 'workflow' / 'sector_sorted_execution_ticket_20260819T1218Z.json'
creds = json.loads((BASE / '.broker_creds_secure.json').read_text(encoding='utf-8'))
cap = creds['capital']

import MetaTrader5 as mt5

mt5.initialize(
    login=int(cap['login']),
    password=cap['password'],
    server=cap['server'],
    path=cap.get('path') or r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe',
    portable=True,
    timeout=15000,
)

acct = mt5.account_info()
print(f'ACCOUNT: {acct.login} | {acct.server} | balance={acct.balance} equity={acct.equity} | free_margin={acct.margin_free}')

ticket_data = json.loads(TICKET_PATH.read_text(encoding='utf-8'))
setups = []
for sector in ['momentum_penny', 'regular_crypto']:
    setups.extend(ticket_data.get('sectors', {}).get(sector, []))

results = []
for setup in setups:
    sym = setup['symbol']
    bias = setup['bias']
    entry = float(setup['entry'])
    sl = float(setup['sl'])
    tp = float(setup['tp'])
    size_usd = float(setup.get('size_usd', 1250.0))
    composite = setup.get('composite')
    bt_pass = setup.get('bt_pass')

    # Map symbol to Capital MT5 crypto symbol
    broker_sym = sym.replace('/USD', 'USD').replace('-USD', 'USD').replace('USD', 'USD')
    if broker_sym in ('ETH/USD', 'ETHUSD'):
        broker_sym = 'ETHUSD'
    elif broker_sym in ('ADAUSD', 'ADA/USD'):
        broker_sym = 'ADAUSD'
    else:
        print(f'SKIP {sym}: unsupported for CAPITAL-RIGHT MT5')
        results.append({'symbol': sym, 'status': 'SKIP', 'reason': 'unsupported_symbol'})
        continue

    info = mt5.symbol_info(broker_sym)
    if info is None:
        print(f'SKIP {sym} -> {broker_sym}: symbol not found')
        results.append({'symbol': sym, 'broker_symbol': broker_sym, 'status': 'SKIP', 'reason': 'symbol_not_found'})
        continue

    if not info.visible or not info.select:
        print(f'SKIP {sym} -> {broker_sym}: visible={info.visible}, select={info.select}')
        results.append({'symbol': sym, 'broker_symbol': broker_sym, 'status': 'SKIP', 'reason': f'visible={info.visible},select={info.select}'})
        continue

    if info.trade_mode not in (mt5.SYMBOL_TRADE_MODE_LONGONLY, mt5.SYMBOL_TRADE_MODE_FULL):
        print(f'SKIP {sym} -> {broker_sym}: trade_mode={info.trade_mode}')
        results.append({'symbol': sym, 'broker_symbol': broker_sym, 'status': 'SKIP', 'reason': f'trade_mode={info.trade_mode}'})
        continue

    tick = mt5.symbol_info_tick(broker_sym)
    if tick is None:
        print(f'SKIP {sym} -> {broker_sym}: no tick data')
        results.append({'symbol': sym, 'broker_symbol': broker_sym, 'status': 'SKIP', 'reason': 'no_tick'})
        continue

    # Size in units based on current ask and fixed USD size
    ask = tick.ask
    qty = max(info.volume_min, min(info.volume_max, size_usd / max(ask, 0.0001)))
    qty = round(qty / info.volume_step) * info.volume_step
    qty = float(qty)

    margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, broker_sym, qty, ask)
    if margin is None:
        print(f'SKIP {sym}: margin calc failed')
        results.append({'symbol': sym, 'broker_symbol': broker_sym, 'status': 'SKIP', 'reason': 'margin_calc_failed'})
        continue

    if margin > acct.margin_free * 0.9:
        print(f'SKIP {sym}: margin {margin:.2f} > 90% free')
        results.append({'symbol': sym, 'broker_symbol': broker_sym, 'status': 'SKIP', 'reason': 'insufficient_margin', 'margin': float(margin)})
        continue

    order_type = mt5.ORDER_TYPE_BUY if bias.upper() == 'LONG' else mt5.ORDER_TYPE_SELL
    request = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': broker_sym,
        'volume': qty,
        'type': order_type,
        'price': ask,
        'sl': sl,
        'tp': tp,
        'deviation': 10,
        'magic': 20260819,
        'comment': f'SECTOR_TICKET {bias} composite={composite} bt={bt_pass}',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f'EXECUTED {sym} -> {broker_sym} {bias} qty={qty} @ {ask} SL={sl} TP={tp} ticket={result.order}')
        results.append({
            'symbol': sym,
            'broker_symbol': broker_sym,
            'broker': 'CAPITAL_RIGHT',
            'status': 'FILLED',
            'ticket': result.order,
            'deal': result.deal,
            'qty': qty,
            'entry': ask,
            'sl': sl,
            'tp': tp,
            'side': bias.upper(),
            'composite': composite,
            'bt_pass': bt_pass,
        })
    else:
        print(f'FAILED {sym} -> {broker_sym}: {result.retcode if result else "None"} {result.comment if result else "None"}')
        results.append({
            'symbol': sym,
            'broker_symbol': broker_sym,
            'broker': 'CAPITAL_RIGHT',
            'status': 'FAILED',
            'retcode': result.retcode if result else None,
            'comment': result.comment if result else None,
            'qty': qty,
            'entry': ask,
            'sl': sl,
            'tp': tp,
            'side': bias.upper(),
            'composite': composite,
            'bt_pass': bt_pass,
        })

out = BASE / f'executed_sector_ticket_{datetime.datetime.utcnow().strftime("%Y%m%dT%H%MZ")}.json'
out.write_text(json.dumps({'timestamp': datetime.datetime.utcnow().isoformat() + 'Z', 'results': results}, indent=2), encoding='utf-8')
print(f'\nWROTE {out}')
print(f'FILLED: {sum(1 for r in results if r["status"]=="FILLED")} | FAILED: {sum(1 for r in results if r["status"]=="FAILED")} | SKIPPED: {sum(1 for r in results if r["status"]=="SKIP")}')

positions = mt5.positions_get()
print(f'\nOpen positions: {len(positions) if positions else 0}')
if positions:
    for p in positions:
        print(f'  {p.symbol}: {p.type} {p.volume} @ {p.price_open} SL={p.sl} TP={p.tp} ticket={p.ticket}')

mt5.shutdown()
