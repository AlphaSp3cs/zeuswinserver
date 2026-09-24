
import MetaTrader5 as mt5, json
from pathlib import Path
from dotenv import dotenv_values
from datetime import datetime, timezone

cfg={k:v for k,v in dotenv_values('.env').items() if v is not None}
path = cfg.get('CAPITAL_MT5_TERMINAL')
login = int(cfg.get('CAPITAL_MT5_LOGIN'))
server = cfg.get('CAPITAL_MT5_SERVER')
password = cfg.get('CAPITAL_MT5_PASSWORD')

mt5.shutdown()
ok = mt5.initialize(path=path, login=login, server=server, password=password, portable=True)
print('init', ok, mt5.last_error() if not ok else '')
if not ok:
    raise SystemExit(1)

positions = mt5.positions_get() or []
by_key = {}
for p in positions:
    side = 'LONG' if p.type == mt5.POSITION_TYPE_BUY else 'SHORT'
    key = (p.symbol, side)
    by_key.setdefault(key, []).append({
        'ticket': int(p.ticket), 'volume': float(p.volume), 'profit': float(p.profit),
        'sl': float(p.sl) if p.sl else None, 'tp': float(p.tp) if p.tp else None,
        'comment': p.comment, 'magic': p.magic, 'time': int(p.time)
    })

duplicates = {k: v for k, v in by_key.items() if len(v) > 1}
print('duplicate_keys', len(duplicates))
results = []
for key, tickets in duplicates.items():
    tickets_sorted = sorted(tickets, key=lambda x: x['time'])
    keep = tickets_sorted[0]
    close_list = tickets_sorted[1:]
    tick = mt5.symbol_info_tick(key[0])
    if tick is None:
        print('NO_TICK', key[0])
        continue
    price = float(tick.bid if key[1] == 'LONG' else tick.ask)
    for t in close_list:
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'position': t['ticket'],
            'symbol': key[0],
            'volume': t['volume'],
            'type': mt5.ORDER_TYPE_SELL if key[1] == 'LONG' else mt5.ORDER_TYPE_BUY,
            'price': price,
            'deviation': 20,
            'magic': 20260806,
            'comment': 'zeus_dedupe',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK
        }
        res = mt5.order_send(req)
        results.append({
            'symbol': key[0], 'side': key[1], 'close_ticket': t['ticket'], 'keep_ticket': keep['ticket'],
            'volume': t['volume'], 'retcode': int(res.retcode) if res else None,
            'order': int(res.order) if res and hasattr(res, 'order') else None,
            'comment': str(res.comment) if res else None
        })
    print('DEDUPE', key, 'keep', keep['ticket'], 'close', [x['ticket'] for x in close_list], 'results', results[-len(close_list):])

pos_after = mt5.positions_get() or []
by_key_after = {}
for p in pos_after:
    side = 'LONG' if p.type == mt5.POSITION_TYPE_BUY else 'SHORT'
    key = (p.symbol, side)
    by_key_after.setdefault(key, []).append(int(p.ticket))
duplicates_after = {k: v for k, v in by_key_after.items() if len(v) > 1}
print('remaining_duplicates', len(duplicates_after))
print('positions_after', len(pos_after))
report = {
    'asof_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    'results': results,
    'remaining_duplicates': duplicates_after,
    'positions_after_count': len(pos_after)
}
Path('capital_dedupe_report_2026-08-06.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print('WROTE capital_dedupe_report_2026-08-06.json')
mt5.shutdown()
