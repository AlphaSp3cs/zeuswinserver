import os, json, requests
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

env_path = Path('.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k,v = line.split('=',1)
            os.environ.setdefault(k.strip(), v.strip())

TERMINAL=os.environ.get('FTMO_MT5_TERMINAL')
FTMO_LOGIN=int(os.environ.get('FTMO_MT5_LOGIN',0))
FTMO_PW=os.environ.get('FTMO_MT5_PASSWORD')
FTMO_SERVER=os.environ.get('FTMO_MT5_SERVER')
CAP_TERMINAL=os.environ.get('CAPITAL_MT5_TERMINAL')
CAP_LOGIN=int(os.environ.get('CAPITAL_MT5_LOGIN',0))
CAP_PW=os.environ.get('CAPITAL_MT5_PASSWORD')
CAP_SERVER=os.environ.get('CAPITAL_MT5_SERVER')
ALPACA_BASE=os.environ.get('ALPACA_BASE_URL','https://paper-api.alpaca.markets/v2')
ALPACA_KEY=os.environ.get('ALPACA_API_KEY_ID')
ALPACA_SECRET=os.environ.get('ALPACA_API_SECRET_KEY')

def init_mt5(terminal, login, password, server):
    mt5.shutdown()
    ok = mt5.initialize(terminal, login=login, password=password, server=server)
    if ok:
        acc = mt5.account_info()
        pos = mt5.positions_get() or []
        existing = {(p.symbol, int(p.type)) for p in pos}
        return {'ok': True, 'acc': acc, 'pos': pos, 'existing': existing, 'equity': float(acc.equity) if acc else 0.0}
    return {'ok': False, 'error': mt5.last_error()}

def digits_for(sym):
    if 'JPY' in sym: return 3 if sym in ['USDJPY','EURJPY','GBPJPY'] else 5
    if any(k in sym for k in ['XAU','XAG']): return 2
    if any(k in sym for k in ['BTC','ETH','SOL','XRP','DOT','DOGE','LTC']): return 2
    if any(k in sym for k in ['US30','US500','NAS100','UK100','GER40']): return 1
    return 5

def place_mt5_copy(state, sym, side, entry, atr, comment):
    if not state['ok']:
        return {'broker': state.get('name'), 'status': 'broker_unavailable'}
    si = mt5.symbol_info(sym)
    if not si:
        return {'symbol':sym,'side':side,'broker':state.get('name'),'status':'blocked_no_symbol_info'}
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        return {'symbol':sym,'side':side,'broker':state.get('name'),'status':'blocked_no_quote'}
    digits = digits_for(sym)
    buf = max(0.5 * atr, 10**(-digits) * 2)
    if side == 'LONG':
        if (sym, 0) in state['existing']:
            return {'symbol':sym,'side':side,'broker':state.get('name'),'status':'skipped_duplicate','reason':'existing long'}
        sl = round(entry - buf, digits)
        tp = round(entry + 2.0 * buf, digits)
        otype = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        if (sym, 1) in state['existing']:
            return {'symbol':sym,'side':side,'broker':state.get('name'),'status':'skipped_duplicate','reason':'existing short'}
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
        return {'symbol':sym,'side':side,'broker':state.get('name'),'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp}
    if side == 'SHORT' and not (entry > sl and tp < entry):
        return {'symbol':sym,'side':side,'broker':state.get('name'),'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp}
    vol = float(getattr(si, 'volume_min', 0.01))
    # Try FOK then IOC then market-only retry without SL/TP if broker rejects filling mode
    for filling in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC]:
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': sym,
            'volume': vol,
            'type': otype,
            'price': price,
            'sl': float(sl),
            'tp': float(tp),
            'deviation': 20,
            'magic': 0,
            'comment': comment,
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': filling,
        }
        res = mt5.order_send(req)
        retcode = int(getattr(res, 'retcode', -1))
        if retcode == 10009:
            return {
                'symbol': sym, 'side': side, 'broker': state.get('name'),
                'status': 'executed', 'retcode': retcode,
                'order_id': int(getattr(res, 'order', 0) or 0),
                'volume': vol, 'entry': entry, 'sl': sl, 'tp': tp,
                'price': price, 'comment': getattr(res, 'comment', ''),
            }
    # Fallback: retry without SL/TP once
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': vol,
        'type': otype,
        'price': price,
        'deviation': 20,
        'magic': 0,
        'comment': comment + '_nosl',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK if state.get('name') == 'CAPITAL_RIGHT' else mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    retcode = int(getattr(res, 'retcode', -1))
    return {
        'symbol': sym, 'side': side, 'broker': state.get('name'),
        'status': 'executed' if retcode == 10009 else 'failed',
        'retcode': retcode,
        'order_id': int(getattr(res, 'order', 0) or 0),
        'volume': vol, 'entry': entry, 'sl': sl, 'tp': tp,
        'price': price, 'comment': getattr(res, 'comment', ''),
    }

# Init brokers
ftmo_state = init_mt5(TERMINAL, FTMO_LOGIN, FTMO_PW, FTMO_SERVER)
ftmo_state['name'] = 'FTMO_LEFT'
cap_state = init_mt5(CAP_TERMINAL, CAP_LOGIN, CAP_PW, CAP_SERVER)
cap_state['name'] = 'CAPITAL_RIGHT'

print('FTMO', ftmo_state['ok'], ftmo_state.get('equity'), len(ftmo_state.get('pos',[])))
print('CAPITAL', cap_state['ok'], cap_state.get('equity'), len(cap_state.get('pos',[])))

# Retry copy with filling-mode fallback
copy_results = []
if ftmo_state['ok'] and cap_state['ok']:
    for p in ftmo_state['pos']:
        sym = p.symbol
        side = 'LONG' if int(p.type) == 0 else 'SHORT'
        if sym == 'DOTUSD':
            # special-case: skip thesis conflict
            continue
        si = mt5.symbol_info(sym)
        if not si:
            copy_results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'blocked_no_symbol_info'})
            continue
        digits = digits_for(sym)
        tick = mt5.symbol_info_tick(sym)
        entry = float(tick.ask) if int(p.type)==0 else float(tick.bid)
        atr = 0.0
        try:
            r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 14)
            if r is not None and len(r) > 1:
                tr = [max(r[i]['high']-r[i]['low'], abs(r[i]['high']-r[i]['close']), abs(r[i]['low']-r[i]['close'])) for i in range(-14, -1)]
                atr = sum(tr) / len(tr)
        except Exception:
            pass
        if atr <= 0:
            atr = 10**(-digits) * 20
        copy_results.append(place_mt5_copy(cap_state, sym, side, entry, atr, 'copy_from_ftmo_v2'))
else:
    copy_results = [{'broker':'CAPITAL_RIGHT','status':'skipped','reason':f"ftmo={ftmo_state['ok']} cap={cap_state['ok']}"}]
print('COPY_RESULTS_V2')
for r in copy_results:
    print(r)

# Alpaca LONG-only eligible candidates
alpaca_results = []
try:
    ah = {'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET}
    ar = requests.get(ALPACA_BASE + '/account', headers=ah, timeout=20)
    alpaca_account = ar.json() if ar.ok else {}
    alpaca_bp = float(alpaca_account.get('buying_power', 0) or 0)
    alpaca_cash = float(alpaca_account.get('cash', 0) or 0)
except Exception:
    alpaca_account = {}
    alpaca_bp = 0.0
    alpaca_cash = 0.0

if alpaca_bp >= 10:
    # Submit only LONG equity candidates from scan
    longs = [c for c in json.loads(Path('all_sector_scan_2026-08-03.json').read_text()).get('top_candidates', [])[:15] if c['sector']=='stocks' and c['side']=='LONG']
    h = {'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET, 'Content-Type': 'application/json'}
    for c in longs:
        sym = c['symbol']
        order = {'symbol': sym, 'qty': 1, 'side': 'buy', 'type': 'market', 'time_in_force': 'day'}
        try:
            r = requests.post(ALPACA_BASE + '/orders', headers=h, json=order, timeout=20)
            if r.ok:
                j = r.json()
                alpaca_results.append({'symbol':sym,'side':'LONG','status':'submitted','id':j.get('id'),'qty':1})
            else:
                alpaca_results.append({'symbol':sym,'side':'LONG','status':'failed','code':r.status_code,'text':r.text[:200]})
        except Exception as e:
            alpaca_results.append({'symbol':sym,'side':'LONG','status':'error','error':str(e)})
else:
    alpaca_results = [{'status':'skipped','reason':f'buying_power={alpaca_bp}'}]
print('ALPACA_RESULTS')
for r in alpaca_results:
    print(r)

out = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'copy_v2': copy_results,
    'alpaca': {'buying_power': alpaca_bp, 'cash': alpaca_cash, 'results': alpaca_results},
}
out_path = Path('artifacts') / f"execution_copy_v2_{datetime.now().strftime('%Y%m%dT%H%MZ')}.json"
out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
print('WROTE', out_path)