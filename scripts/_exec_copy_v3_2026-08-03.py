import os, json
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

env_path = Path('.env')
for line in env_path.read_text().splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k,v = line.split('=',1)
        os.environ.setdefault(k.strip(), v.strip())

TERMINAL=os.environ.get('CAPITAL_MT5_TERMINAL')
LOGIN=int(os.environ.get('CAPITAL_MT5_LOGIN',0))
PW=os.environ.get('CAPITAL_MT5_PASSWORD')
SERVER=os.environ.get('CAPITAL_MT5_SERVER')

def init_capital():
    mt5.shutdown()
    ok = mt5.initialize(TERMINAL, login=LOGIN, password=PW, server=SERVER)
    if not ok:
        return {'ok': False, 'error': mt5.last_error()}
    acc = mt5.account_info()
    pos = mt5.positions_get() or []
    existing = {(p.symbol, int(p.type)) for p in pos}
    return {'ok': True, 'acc': acc, 'pos': pos, 'existing': existing, 'equity': float(acc.equity) if acc else 0.0}

def digits_for(sym):
    if 'JPY' in sym: return 3 if sym in ['USDJPY','EURJPY','GBPJPY'] else 5
    if any(k in sym for k in ['XAU','XAG']): return 2
    if any(k in sym for k in ['BTC','ETH','SOL','XRP','DOT','DOGE','LTC']): return 2
    return 5

state = init_capital()
print('CAPITAL init=', state['ok'], 'equity=', state.get('equity'), 'positions=', len(state.get('pos',[])))
if not state['ok']:
    raise SystemExit

# Use live FTMO positions source from file
live = []
for p in state['pos']:
    if p.symbol in ['DOTUSD','DOGEUSD','ETHUSD','EURJPY','GBPJPY']:
        live.append({'symbol': p.symbol, 'type': int(p.type), 'volume': float(p.volume)})

# Reconnect FTMO to read live positions accurately
mt5.shutdown()
ftmo_ok = mt5.initialize(os.environ.get('FTMO_MT5_TERMINAL'), login=int(os.environ.get('FTMO_MT5_LOGIN',0)), password=os.environ.get('FTMO_MT5_PASSWORD'), server=os.environ.get('FTMO_MT5_SERVER'))
ftmo_pos = mt5.positions_get() or [] if ftmo_ok else []
ftmo_map = {(p.symbol, int(p.type)): p for p in ftmo_pos}
mt5.shutdown()

results = []
# Re-init capital for order send
state = init_capital()
for item in live:
    sym = item['symbol']
    ptype = item['type']
    side = 'LONG' if ptype == 0 else 'SHORT'
    if (sym, ptype) in state['existing']:
        results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'skipped_duplicate'})
        continue
    si = mt5.symbol_info(sym)
    if not si:
        results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'blocked_no_symbol_info'})
        continue
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'blocked_no_quote'})
        continue
    digits = digits_for(sym)
    entry = float(tick.ask) if ptype == 0 else float(tick.bid)
    # ATR from FTMO live rates
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 14) if ftmo_ok else None
    atr = 0.0
    if rates is not None and len(rates) > 1:
        tr = [max(rates[i]['high']-rates[i]['low'], abs(rates[i]['high']-rates[i]['close']), abs(rates[i]['low']-rates[i]['close'])) for i in range(-14, -1)]
        atr = sum(tr) / len(tr)
    if atr <= 0:
        atr = 10**(-digits) * 20
    buf = max(0.5 * atr, 10**(-digits) * 2)
    if ptype == 0:
        sl = round(entry - buf, digits)
        tp = round(entry + 2.0 * buf, digits)
        otype = mt5.ORDER_TYPE_BUY
    else:
        sl = round(entry + buf, digits)
        tp = round(entry - 2.0 * buf, digits)
        otype = mt5.ORDER_TYPE_SELL
    si2 = mt5.symbol_info(sym)
    stop_level = max(0, float(getattr(si2, 'trade_stops_level', 0)) * float(si2.point))
    if ptype == 0 and sl < entry - stop_level - buf:
        sl = round(entry - stop_level - buf, digits)
    if ptype == 1 and sl > entry + stop_level + buf:
        sl = round(entry + stop_level + buf, digits)
    vol = float(getattr(si, 'volume_min', 0.01))
    # Try FOK with SL/TP, then FOK without SL/TP
    for attempt in range(2):
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': sym,
            'volume': vol,
            'type': otype,
            'price': entry,
            'deviation': 20,
            'magic': 0,
            'comment': 'copy_from_ftmo_v3',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }
        if attempt == 0:
            req['sl'] = float(sl)
            req['tp'] = float(tp)
        res = mt5.order_send(req)
        retcode = int(getattr(res, 'retcode', -1))
        if retcode == 10009:
            results.append({
                'symbol': sym, 'side': side, 'broker': 'CAPITAL_RIGHT',
                'status': 'executed', 'retcode': retcode,
                'order_id': int(getattr(res, 'order', 0) or 0),
                'volume': vol, 'entry': entry, 'sl': sl, 'tp': tp,
                'price': entry, 'attempt': attempt+1,
                'comment': getattr(res, 'comment', ''),
            })
            break
        if attempt == 0:
            continue
        results.append({
            'symbol': sym, 'side': side, 'broker': 'CAPITAL_RIGHT',
            'status': 'failed', 'retcode': retcode,
            'order_id': int(getattr(res, 'order', 0) or 0),
            'volume': vol, 'entry': entry, 'sl': sl, 'tp': tp,
            'price': entry, 'attempt': 2,
            'comment': getattr(res, 'comment', ''),
        })
for r in results:
    print(r)
out_path = Path('artifacts') / f"execution_copy_v3_{datetime.now().strftime('%Y%m%dT%H%MZ')}.json"
out_path.write_text(json.dumps({'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'results': results}, indent=2), encoding='utf-8')
print('WROTE', out_path)
mt5.shutdown()