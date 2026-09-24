import os, json, math, requests
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

# Load .env if present
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
IBKR_HOST=os.environ.get('IBKR_HOST','127.0.0.1')
IBKR_PORT=int(os.environ.get('IBKR_PORT','7497'))

SCAN_PATH = Path('all_sector_scan_2026-08-03.json')
candidates = json.loads(SCAN_PATH.read_text()).get('top_candidates', [])[:15]

def digits_for(sym):
    if 'JPY' in sym: return 3 if sym in ['USDJPY','EURJPY','GBPJPY'] else 5
    if any(k in sym for k in ['XAU','XAG']): return 2
    if any(k in sym for k in ['BTC','ETH','SOL','XRP','DOT','DOGE','LTC']): return 2
    if any(k in sym for k in ['US30','US500','NAS100','UK100','GER40']): return 1
    return 5

def init_mt5(terminal, login, password, server):
    mt5.shutdown()
    ok = mt5.initialize(terminal, login=login, password=password, server=server)
    if ok:
        acc = mt5.account_info()
        pos = mt5.positions_get() or []
        existing = {(p.symbol, int(p.type)) for p in pos}
        return {'ok': True, 'acc': acc, 'pos': pos, 'existing': existing, 'equity': float(acc.equity) if acc else 0.0}
    return {'ok': False, 'error': mt5.last_error()}

def ensure_broker(state):
    if not state['ok']:
        return False
    ti = mt5.terminal_info()
    if ti and getattr(ti, 'login', 0) == state['acc'].login:
        return True
    mt5.shutdown()
    ok = mt5.initialize(state['terminal'], login=state['login'], password=state['password'], server=state['server'])
    state['ok'] = ok
    if ok:
        state['acc'] = mt5.account_info()
        state['pos'] = mt5.positions_get() or []
        state['existing'] = {(p.symbol, int(p.type)) for p in state['pos']}
        state['equity'] = float(state['acc'].equity) if state['acc'] else 0.0
    return ok

def place_mt5(state, sym, side, entry, atr, max_risk, comment):
    if not ensure_broker(state):
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
    risk_per_unit = abs(entry - sl)
    if risk_per_unit <= 0:
        return {'symbol':sym,'side':side,'broker':state.get('name'),'status':'blocked_zero_risk'}
    vol_min = float(getattr(si, 'volume_min', 0.01))
    vol_step = float(getattr(si, 'volume_step', vol_min))
    vol = max(vol_min, int((max_risk / risk_per_unit) / vol_step) * vol_step)
    vol = round(vol, 8)
    # Capital RIGHT requires FOK; others use IOC
    filling = mt5.ORDER_FILLING_FOK if state.get('name') == 'CAPITAL_RIGHT' else mt5.ORDER_FILLING_IOC
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': float(vol),
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
    return {
        'symbol': sym, 'side': side, 'broker': state.get('name'),
        'status': 'executed' if retcode == 10009 else 'failed',
        'retcode': retcode,
        'order_id': int(getattr(res, 'order', 0) or 0),
        'volume': float(vol),
        'entry': entry, 'sl': sl, 'tp': tp,
        'price': price,
        'comment': getattr(res, 'comment', ''),
    }

# Initialize brokers
ftmo_state = init_mt5(TERMINAL, FTMO_LOGIN, FTMO_PW, FTMO_SERVER)
ftmo_state['name'] = 'FTMO_LEFT'
ftmo_state['terminal'] = TERMINAL
ftmo_state['login'] = FTMO_LOGIN
ftmo_state['password'] = FTMO_PW
ftmo_state['server'] = FTMO_SERVER
print('FTMO', ftmo_state['ok'], ftmo_state.get('equity'), len(ftmo_state.get('pos',[])))

cap_state = init_mt5(CAP_TERMINAL, CAP_LOGIN, CAP_PW, CAP_SERVER)
cap_state['name'] = 'CAPITAL_RIGHT'
cap_state['terminal'] = CAP_TERMINAL
cap_state['login'] = CAP_LOGIN
cap_state['password'] = CAP_PW
cap_state['server'] = CAP_SERVER
print('CAPITAL', cap_state['ok'], cap_state.get('equity'), len(cap_state.get('pos',[])))

# Alpaca account snapshot
try:
    ah = {'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET}
    ar = requests.get(ALPACA_BASE + '/account', headers=ah, timeout=20)
    alpaca_account = ar.json() if ar.ok else {}
    alpaca_bp = float(alpaca_account.get('buying_power', 0) or 0)
    alpaca_cash = float(alpaca_account.get('cash', 0) or 0)
    print('ALPACA buying_power=', alpaca_bp, 'cash=', alpaca_cash)
except Exception as e:
    alpaca_account = {}
    alpaca_bp = 0.0
    alpaca_cash = 0.0
    print('ALPACA error', e)

# IBKR init
ibkr_state = {'ok': False}
try:
    from ib_insync import IB
    ib = IB()
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=99, timeout=20, readonly=True)
    ibkr_state = {'ok': True, 'ib': ib, 'account': ib.managedAccounts()[0] if ib.managedAccounts() else None}
    print('IBKR ok', ibkr_state.get('account'))
except Exception as e:
    ibkr_state = {'ok': False, 'error': str(e)}
    print('IBKR fail', e)

# Copy FTMO live profitable positions to Capital RIGHT
copy_results = []
if ftmo_state['ok'] and cap_state['ok']:
    cap_syms = {s.name for s in mt5.symbols_get() if s.visible}
    for p in ftmo_state['pos']:
        sym = p.symbol
        side = 'LONG' if int(p.type) == 0 else 'SHORT'
        if sym not in cap_syms:
            copy_results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'symbol_unavailable'})
            continue
        if (sym, int(p.type)) in cap_state['existing']:
            copy_results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'skipped_duplicate'})
            continue
        si = mt5.symbol_info(sym)
        digits = digits_for(sym)
        tick = mt5.symbol_info_tick(sym)
        if not tick or tick.bid <= 0:
            copy_results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'no_quote'})
            continue
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
        buf = max(0.5 * atr, 10**(-digits) * 2)
        if int(p.type) == 0:
            sl = round(entry - buf, digits)
            tp = round(entry + 2.0 * buf, digits)
            otype = mt5.ORDER_TYPE_BUY
        else:
            sl = round(entry + buf, digits)
            tp = round(entry - 2.0 * buf, digits)
            otype = mt5.ORDER_TYPE_SELL
        si2 = mt5.symbol_info(sym)
        stop_level = max(0, float(getattr(si2, 'trade_stops_level', 0)) * float(si2.point))
        if int(p.type)==0 and sl < entry - stop_level - buf:
            sl = round(entry - stop_level - buf, digits)
        if int(p.type)==1 and sl > entry + stop_level + buf:
            sl = round(entry + stop_level + buf, digits)
        vol = float(getattr(si, 'volume_min', 0.01))
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': sym,
            'volume': vol,
            'type': otype,
            'price': entry,
            'sl': float(sl),
            'tp': float(tp),
            'deviation': 20,
            'magic': 0,
            'comment': 'copy_from_ftmo',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        retcode = int(getattr(res, 'retcode', -1))
        copy_results.append({
            'symbol': sym, 'side': side, 'broker': 'CAPITAL_RIGHT',
            'status': 'executed' if retcode == 10009 else 'failed',
            'retcode': retcode,
            'order_id': int(getattr(res, 'order', 0) or 0),
            'volume': vol, 'entry': entry, 'sl': sl, 'tp': tp,
            'comment': getattr(res, 'comment', ''),
        })
else:
    copy_results = [{'broker':'CAPITAL_RIGHT','status':'skipped','reason':f"ftmo={ftmo_state['ok']} cap={cap_state['ok']}"}]
print('COPY_RESULTS')
for r in copy_results:
    print(r)

# Override 15 candidates on FTMO and Capital
override_results = []
for c in candidates:
    sym = c['symbol']
    sector = c['sector']
    side = c['side']
    atr = float(c['atr14'])
    entry = float(c['entry'])
    ftmo_r = place_mt5(ftmo_state, sym, side, entry, atr, ftmo_state.get('equity',0.0)*0.01, 'night_scan_override')
    cap_r = place_mt5(cap_state, sym, side, entry, atr, cap_state.get('equity',0.0)*0.01, 'night_scan_override_capital')
    override_results.append({'symbol':sym,'sector':sector,'side':side,'ftmo':ftmo_r,'capital':cap_r})
print('OVERRIDE_RESULTS')
for r in override_results:
    print(r)

# Alpaca micro placement for equities if buying power allows
alpaca_results = []
if alpaca_bp >= 10:
    equities = [c for c in candidates if c['sector'] == 'stocks']
    h = {'APCA-API-KEY-ID': ALPACA_KEY, 'APCA-API-SECRET-KEY': ALPACA_SECRET, 'Content-Type': 'application/json'}
    for c in equities[:3]:
        qty = 1
        side = c['side']
        sym = c['symbol']
        order = {
            'symbol': sym,
            'qty': qty,
            'side': 'buy' if side=='LONG' else 'sell',
            'type': 'market',
            'time_in_force': 'day',
        }
        try:
            r = requests.post(ALPACA_BASE + '/orders', headers=h, json=order, timeout=20)
            if r.ok:
                j = r.json()
                alpaca_results.append({'symbol':sym,'side':side,'status':'submitted','id':j.get('id'),'qty':qty})
            else:
                alpaca_results.append({'symbol':sym,'side':side,'status':'failed','code':r.status_code,'text':r.text[:200]})
        except Exception as e:
            alpaca_results.append({'symbol':sym,'side':side,'status':'error','error':str(e)})
else:
    alpaca_results = [{'status':'skipped','reason':f'buying_power={alpaca_bp}'}]
print('ALPACA_RESULTS')
for r in alpaca_results:
    print(r)

# Disconnect
if ibkr_state.get('ok'):
    try:
        ibkr_state['ib'].disconnect()
    except Exception:
        pass

out = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'ftmo': {'init': ftmo_state['ok'], 'equity': ftmo_state.get('equity'), 'copy': copy_results},
    'capital': {'init': cap_state['ok'], 'equity': cap_state.get('equity'), 'copy': copy_results},
    'override': override_results,
    'alpaca': {'buying_power': alpaca_bp, 'cash': alpaca_cash, 'results': alpaca_results},
    'ibkr': {'init': ibkr_state['ok']},
}
out_path = Path('artifacts') / f"execution_multi_broker_{datetime.now().strftime('%Y%m%dT%H%MZ')}.json"
out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
print('WROTE', out_path)