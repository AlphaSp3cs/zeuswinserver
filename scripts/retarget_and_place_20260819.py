#!/usr/bin/env python3
"""
retarget_and_place_20260819.py
Retarget existing open positions and place missing ones to match the approved ticket.
"""
import json, datetime, traceback
from pathlib import Path

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
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

# Exact ticket values from sector ticket
ticket_map = {
    'ETHUSD': {'entry': 1913.0, 'sl': 1836.61, 'tp': 2065.78},
    'ADAUSD': {'entry': 0.165, 'sl': 0.16319, 'tp': 0.16862},
    'DOGEUSD': {'entry': 0.0707452, 'sl': 0.07027026, 'tp': 0.07169507},
}

positions = mt5.positions_get()
print(f'Open positions before: {len(positions) if positions else 0}')
if positions:
    for p in positions:
        print(f'  {p.symbol}: type={p.type} vol={p.volume} @ {p.price_open} SL={p.sl} TP={p.tp} ticket={p.ticket}')

results = []
open_symbols = {p.symbol for p in (positions or [])}

# Retarget existing positions
for sym, vals in ticket_map.items():
    if sym in open_symbols:
        for p in positions:
            if p.symbol == sym:
                # Only modify if SL/TP differ
                if abs(p.sl - vals['sl']) > 1e-6 or abs(p.tp - vals['tp']) > 1e-6:
                    request = {
                        'action': mt5.TRADE_ACTION_SLTP,
                        'symbol': sym,
                        'position': p.ticket,
                        'sl': vals['sl'],
                        'tp': vals['tp'],
                    }
                    res = mt5.order_send(request)
                    status = 'RETARGETED' if res and res.retcode == mt5.TRADE_RETCODE_DONE else f'FAILED:{res.retcode if res else "None"}'
                    print(f'RETARGET {sym}: ticket={p.ticket} SL={vals["sl"]} TP={vals["tp"]} -> {status}')
                    results.append({
                        'symbol': sym,
                        'action': 'retarget',
                        'ticket': p.ticket,
                        'sl': vals['sl'],
                        'tp': vals['tp'],
                        'status': status,
                    })
                else:
                    print(f'SKIP {sym}: SL/TP already match ticket')
                    results.append({'symbol': sym, 'action': 'retarget', 'status': 'skipped_already_match'})
                break
    else:
        # Place new order
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            print(f'SKIP {sym}: symbol/tick not available')
            results.append({'symbol': sym, 'action': 'place', 'status': 'SKIP', 'reason': 'symbol_or_tick_unavailable'})
            continue

        size_usd = 1250.0
        qty = max(info.volume_min, min(info.volume_max, size_usd / max(vals['entry'], 0.0001)))
        qty = round(qty / info.volume_step) * info.volume_step
        qty = float(qty)

        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': sym,
            'volume': qty,
            'type': order_type,
            'price': price,
            'sl': vals['sl'],
            'tp': vals['tp'],
            'deviation': 10,
            'magic': 20260819,
            'comment': 'SECTOR_TICKET LONG',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f'PLACED {sym}: qty={qty} @ {price} SL={vals["sl"]} TP={vals["tp"]} ticket={res.order}')
            results.append({
                'symbol': sym,
                'action': 'place',
                'broker': 'CAPITAL_RIGHT',
                'status': 'FILLED',
                'ticket': res.order,
                'deal': res.deal,
                'qty': qty,
                'entry': price,
                'sl': vals['sl'],
                'tp': vals['tp'],
                'side': 'LONG',
            })
        else:
            print(f'FAILED {sym}: {res.retcode if res else "None"} {res.comment if res else "None"}')
            results.append({
                'symbol': sym,
                'action': 'place',
                'broker': 'CAPITAL_RIGHT',
                'status': 'FAILED',
                'retcode': res.retcode if res else None,
                'comment': res.comment if res else None,
                'entry': price,
                'sl': vals['sl'],
                'tp': vals['tp'],
            })

out = BASE / f'executed_sector_ticket_{datetime.datetime.utcnow().strftime("%Y%m%dT%H%MZ")}.json'
out.write_text(json.dumps({'timestamp': datetime.datetime.utcnow().isoformat() + 'Z', 'results': results}, indent=2), encoding='utf-8')
print(f'\nWROTE {out}')

positions_after = mt5.positions_get()
print(f'Open positions after: {len(positions_after) if positions_after else 0}')
if positions_after:
    for p in positions_after:
        print(f'  {p.symbol}: type={p.type} vol={p.volume} @ {p.price_open} SL={p.sl} TP={p.tp} ticket={p.ticket} profit={p.profit}')

mt5.shutdown()
