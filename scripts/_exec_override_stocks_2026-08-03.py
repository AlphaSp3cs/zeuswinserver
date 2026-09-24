import MetaTrader5 as mt5, json
from pathlib import Path
from datetime import datetime, timezone

TERMINAL=r'REDACTED-PATH'
LOGIN=int(os.environ.get('FTMO_MT5_LOGIN', '0'))
PW=os.environ.get('FTMO_MT5_PASSWORD', '')
SERVER=os.environ.get('FTMO_MT5_SERVER', '')
CAPITAL_LOGIN=int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685'))
CAPITAL_SERVER='Capital.ComBah-Demo'

STOCKS = ['AMZN','MSFT','GOOG','AAPL','WMT','DIS','CVX','BAC','JPM','LMT']

def init_broker(terminal, login, password, server):
    mt5.shutdown()
    ok = mt5.initialize(terminal, login=login, password=password, server=server)
    if ok:
        acc = mt5.account_info()
        pos = mt5.positions_get() or []
        return {
            'init': True,
            'account': acc.login if acc else None,
            'equity': float(acc.equity) if acc else 0.0,
            'positions': pos,
            'existing': {(p.symbol, int(p.type)) for p in pos},
        }
    else:
        return {'init': False, 'error': mt5.last_error(), 'positions': [], 'existing': set()}

def vol_meta(sym, si):
    return float(getattr(si, 'volume_min', 0.01)), float(getattr(si, 'volume_step', 0.01))

def round_price(sym, price, digits):
    return round(float(price), digits)

def digits_for(sym):
    if 'JPY' in sym: return 3 if sym in ['USDJPY','EURJPY','GBPJPY'] else 5
    if any(k in sym for k in ['XAU','XAG']): return 2
    if any(k in sym for k in ['BTC','ETH','SOL','XRP','DOT','DOGE','LTC']): return 2
    if any(k in sym for k in ['US30','US500','NAS100','UK100','GER40']): return 1
    return 5

def place_order(broker_name, sym, side, entry, atr, existing_set, max_risk):
    si = mt5.symbol_info(sym)
    if not si:
        return {'symbol':sym,'side':side,'broker':broker_name,'status':'blocked_no_symbol_info'}
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        return {'symbol':sym,'side':side,'broker':broker_name,'status':'blocked_no_quote'}
    digits = digits_for(sym)
    buf = max(0.5 * atr, 10**(-digits) * 2)
    if side == 'LONG':
        if (sym, 0) in existing_set:
            return {'symbol':sym,'side':side,'broker':broker_name,'status':'skipped_duplicate','reason':'existing long'}
        sl = round_price(sym, entry - buf, digits)
        tp = round_price(sym, entry + 2.0 * buf, digits)
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        if (sym, 1) in existing_set:
            return {'symbol':sym,'side':side,'broker':broker_name,'status':'skipped_duplicate','reason':'existing short'}
        sl = round_price(sym, entry + buf, digits)
        tp = round_price(sym, entry - 2.0 * buf, digits)
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    # direction check
    if side == 'LONG' and not (entry < tp and sl < entry):
        return {'symbol':sym,'side':side,'broker':broker_name,'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp}
    if side == 'SHORT' and not (entry > sl and tp < entry):
        return {'symbol':sym,'side':side,'broker':broker_name,'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp}
    # stop distance
    si2 = mt5.symbol_info(sym)
    stop_level = max(0, float(getattr(si2, 'trade_stops_level', 0)) * float(si2.point))
    if side == 'LONG' and sl < entry - stop_level - buf:
        sl = round_price(sym, entry - stop_level - buf, digits)
    if side == 'SHORT' and sl > entry + stop_level + buf:
        sl = round_price(sym, entry + stop_level + buf, digits)
    risk_per_unit = abs(entry - sl)
    if risk_per_unit <= 0:
        return {'symbol':sym,'side':side,'broker':broker_name,'status':'blocked_zero_risk'}
    vol_min, vol_step = vol_meta(sym, si)
    raw_vol = max_risk / risk_per_unit
    steps = int(raw_vol / vol_step)
    vol = round(max(vol_min, steps * vol_step), 8)
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': float(vol),
        'type': order_type,
        'price': price,
        'sl': float(sl),
        'tp': float(tp),
        'deviation': 20,
        'magic': 0,
        'comment': 'stock_override',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    retcode = int(getattr(res, 'retcode', -1))
    return {
        'symbol': sym, 'side': side, 'broker': broker_name,
        'status': 'executed' if retcode == 10009 else 'failed',
        'retcode': retcode,
        'order_id': int(getattr(res, 'order', 0) or 0),
        'volume': float(vol),
        'entry': entry, 'sl': sl, 'tp': tp,
        'price': price,
        'comment': getattr(res, 'comment', ''),
    }

# Load candidates
scan = json.loads(Path('all_sector_scan_2026-08-03.json').read_text())
candidates = [c for c in scan.get('top_candidates', [])[:15] if c['symbol'] in STOCKS]

ftmo_state = init_broker(TERMINAL, LOGIN, PW, SERVER)
print('FTMO init=', ftmo_state['init'], 'equity=', ftmo_state.get('equity'), 'positions=', len(ftmo_state.get('positions',[])))

cap_state = init_broker(TERMINAL, CAPITAL_LOGIN, PW, CAPITAL_SERVER)
print('CAPITAL init=', cap_state['init'], 'error=', cap_state.get('error'))

ftmo_results = []
cap_results = []
max_risk = ftmo_state.get('equity', 0.0) * 0.01 if ftmo_state.get('equity') else 0.0

for c in candidates:
    sym = c['symbol']
    sector = c['sector']
    side = c['side']
    atr = float(c['atr14'])
    # FTMO attempt
    if ftmo_state['init']:
        entry_ftmo = float(c['entry'])  # use report entry as reference; live tick used inside
        r = place_order('FTMO_LEFT', sym, side, entry_ftmo, atr, ftmo_state['existing'], max_risk)
        ftmo_results.append(r)
    # Capital attempt
    if cap_state['init']:
        entry_cap = float(c['entry'])
        r = place_order('CAPITAL_RIGHT', sym, side, entry_cap, atr, cap_state['existing'], max_risk)
        cap_results.append(r)
    else:
        cap_results.append({'symbol':sym,'side':side,'broker':'CAPITAL_RIGHT','status':'broker_unavailable','error':cap_state.get('error')})

out = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'override': True,
    'scope': 'stocks_only',
    'ftmo': {'init': ftmo_state['init'], 'equity': ftmo_state.get('equity'), 'results': ftmo_results},
    'capital': {'init': cap_state['init'], 'error': cap_state.get('error'), 'results': cap_results},
}
out_path = Path('artifacts') / f"execution_override_stocks_{datetime.now().strftime('%Y%m%dT%H%MZ')}.json"
out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
print('WROTE', out_path)
for r in ftmo_results:
    print(r)
print('---CAPITAL---')
for r in cap_results:
    print(r)