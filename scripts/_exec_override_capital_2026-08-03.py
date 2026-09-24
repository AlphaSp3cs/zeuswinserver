import os, json
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

env_path = Path('.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k,v = line.split('=',1)
            os.environ.setdefault(k.strip(), v.strip())

TERMINAL=os.environ.get('CAPITAL_MT5_TERMINAL')
LOGIN=int(os.environ.get('CAPITAL_MT5_LOGIN',0))
PW=os.environ.get('CAPITAL_MT5_PASSWORD')
SERVER=os.environ.get('CAPITAL_MT5_SERVER')
candidates = json.loads(Path('all_sector_scan_2026-08-03.json').read_text()).get('top_candidates', [])[:15]

def digits_for(sym):
    if 'JPY' in sym: return 3 if sym in ['USDJPY','EURJPY','GBPJPY'] else 5
    if any(k in sym for k in ['XAU','XAG']): return 2
    if any(k in sym for k in ['BTC','ETH','SOL','XRP','DOT','DOGE','LTC']): return 2
    if any(k in sym for k in ['US30','US500','NAS100','UK100','GER40']): return 1
    return 5

mt5.shutdown()
if not mt5.initialize(TERMINAL, login=LOGIN, password=PW, server=SERVER):
    print('init fail', mt5.last_error()); raise SystemExit
acc = mt5.account_info()
equity = float(acc.equity)
pos = mt5.positions_get() or []
existing = {(p.symbol, int(p.type)) for p in pos}
print('CAPITAL equity=', equity, 'positions=', len(pos))

results = []
for c in candidates:
    sym = c['symbol']
    sector = c['sector']
    side = c['side']
    si = mt5.symbol_info(sym)
    if not si:
        results.append({'symbol':sym,'side':side,'status':'blocked_no_symbol_info','broker':'CAPITAL_RIGHT'})
        continue
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        results.append({'symbol':sym,'side':side,'status':'blocked_no_quote','broker':'CAPITAL_RIGHT'})
        continue
    digits = digits_for(sym)
    atr = float(c['atr14'])
    entry = float(c['entry'])
    buf = max(0.5 * atr, 10**(-digits) * 2)
    if side == 'LONG':
        if (sym, 0) in existing:
            results.append({'symbol':sym,'side':side,'status':'skipped_duplicate','reason':'existing long','broker':'CAPITAL_RIGHT'})
            continue
        sl = round(entry - buf, digits)
        tp = round(entry + 2.0 * buf, digits)
        otype = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        if (sym, 1) in existing:
            results.append({'symbol':sym,'side':side,'status':'skipped_duplicate','reason':'existing short','broker':'CAPITAL_RIGHT'})
            continue
        sl = round(entry + buf, digits)
        tp = round(entry - 2.0 * buf, digits)
        otype = mt5.ORDER_TYPE_SELL
        price = tick.bid
    si2 = mt5.symbol_info(sym)
    stop_level = max(0, float(getattr(si2, 'trade_stops_level', 0)) * float(si2.point))
    if side == 'LONG' and sl < entry - stop_level - buf:
        sl = round(entry - stop_level - buf, digits)
    if side == 'SHORT' and sl > entry + stop_level + buf:
        sl = round(entry + stop_level + buf, digits)
    if side == 'LONG' and not (entry < tp and sl < entry):
        results.append({'symbol':sym,'side':side,'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp,'broker':'CAPITAL_RIGHT'})
        continue
    if side == 'SHORT' and not (entry > sl and tp < entry):
        results.append({'symbol':sym,'side':side,'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp,'broker':'CAPITAL_RIGHT'})
        continue
    vol_min = float(getattr(si, 'volume_min', 0.01))
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': float(vol_min),
        'type': otype,
        'price': price,
        'sl': float(sl),
        'tp': float(tp),
        'deviation': 20,
        'magic': 0,
        'comment': 'night_scan_override_capital',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK,
    }
    res = mt5.order_send(req)
    retcode = int(getattr(res, 'retcode', -1))
    results.append({
        'symbol': sym, 'sector': sector, 'side': side,
        'status': 'executed' if retcode == 10009 else 'failed',
        'retcode': retcode,
        'order_id': int(getattr(res, 'order', 0) or 0),
        'volume': float(vol_min),
        'entry': entry, 'sl': sl, 'tp': tp,
        'price': price,
        'comment': getattr(res, 'comment', ''),
        'broker': 'CAPITAL_RIGHT',
    })
for r in results:
    print(r)
out = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'broker': 'CAPITAL_RIGHT',
    'equity': equity,
    'results': results,
}
out_path = Path('artifacts') / f"execution_override_capital_{datetime.now().strftime('%Y%m%dT%H%MZ')}.json"
out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
print('WROTE', out_path)
mt5.shutdown()
