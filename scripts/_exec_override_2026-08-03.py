import MetaTrader5 as mt5, json
from pathlib import Path
from datetime import datetime, timezone

TERMINAL=r'REDACTED-PATH'
LOGIN=int(os.environ.get('FTMO_MT5_LOGIN', '0'))
PW=os.environ.get('FTMO_MT5_PASSWORD', '')
SERVER=os.environ.get('FTMO_MT5_SERVER', '')
CAPITAL_LOGIN=int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685'))
CAPITAL_SERVER='Capital.ComBah-Demo'

scan = json.loads(Path('all_sector_scan_2026-08-03.json').read_text())
candidates = scan.get('top_candidates', [])[:15]

# FTMO LEFT
mt5.shutdown()
if not mt5.initialize(TERMINAL, login=LOGIN, password=PW, server=SERVER):
    print('FTMO init fail', mt5.last_error()); raise SystemExit

acc = mt5.account_info()
equity = float(acc.equity)
max_risk = equity * 0.01
print('FTMO equity=', equity, 'max_risk_per_trade=', max_risk)

pos = mt5.positions_get() or []
existing = {(p.symbol, int(p.type)) for p in pos}

def get_vol_meta(sym):
    si = mt5.symbol_info(sym)
    return float(getattr(si, 'volume_min', 0.01)), float(getattr(si, 'volume_step', 0.01))

def normalize_vol(raw, vol_min, vol_step):
    if raw < vol_min:
        raw = vol_min
    steps = int(raw / vol_step)
    return round(max(vol_min, steps * vol_step), 8)

results = []
for c in candidates:
    sym = c['symbol']
    sector = c['sector']
    side = c['side']
    if sym == 'DOTUSD' and side == 'SHORT':
        results.append({'symbol':sym,'side':side,'status':'skipped_thesis_conflict','reason':'live long already open'})
        continue
    if side == 'LONG' and (sym, 0) in existing:
        results.append({'symbol':sym,'side':side,'status':'skipped_duplicate','reason':'existing long ticket'})
        continue
    if side == 'SHORT' and (sym, 1) in existing:
        results.append({'symbol':sym,'side':side,'status':'skipped_duplicate','reason':'existing short ticket'})
        continue

    si = mt5.symbol_info(sym)
    if not si:
        results.append({'symbol':sym,'side':side,'status':'blocked_no_symbol_info'})
        continue
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        results.append({'symbol':sym,'side':side,'status':'blocked_no_quote'})
        continue

    if 'JPY' in sym: digits = 3 if sym in ['USDJPY','EURJPY','GBPJPY'] else 5
    else: digits = 5
    if any(k in sym for k in ['XAU','XAG']): digits = 2
    if any(k in sym for k in ['BTC','ETH','SOL','XRP','DOT','DOGE','LTC']): digits = 2
    if any(k in sym for k in ['US30','US500','NAS100','UK100','GER40']): digits = 1

    # Use live prices, preserve report buffer shape
    if side == 'LONG':
        entry = float(tick.ask)
        atr = float(c['atr14'])
        buf = max(0.5 * atr, 10**(-digits) * 2)
        sl = round(entry - buf, digits)
        tp = round(entry + 2.0 * buf, digits)
        order_type = mt5.ORDER_TYPE_BUY
    else:
        entry = float(tick.bid)
        atr = float(c['atr14'])
        buf = max(0.5 * atr, 10**(-digits) * 2)
        sl = round(entry + buf, digits)
        tp = round(entry - 2.0 * buf, digits)
        order_type = mt5.ORDER_TYPE_SELL

    # Broker minimum stop distance enforcement
    si2 = mt5.symbol_info(sym)
    stop_level = max(0, float(getattr(si2, 'trade_stops_level', 0)) * float(si2.point))
    if side == 'LONG' and sl < entry - stop_level - buf:
        sl = round(entry - stop_level - buf, digits)
    if side == 'SHORT' and sl > entry + stop_level + buf:
        sl = round(entry + stop_level + buf, digits)

    # direction validation
    if side == 'LONG' and not (entry < tp and sl < entry):
        results.append({'symbol':sym,'side':side,'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp})
        continue
    if side == 'SHORT' and not (sl > entry and tp < entry):
        results.append({'symbol':sym,'side':side,'status':'blocked_direction_mismatch','entry':entry,'sl':sl,'tp':tp})
        continue

    risk_per_unit = abs(entry - sl)
    if risk_per_unit <= 0:
        results.append({'symbol':sym,'side':side,'status':'blocked_zero_risk'})
        continue
    vol_min, vol_step = get_vol_meta(sym)
    vol = normalize_vol(max_risk / risk_per_unit, vol_min, vol_step)

    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': float(vol),
        'type': order_type,
        'price': entry,
        'sl': float(sl),
        'tp': float(tp),
        'deviation': 20,
        'magic': 0,
        'comment': 'night_scan_override',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK if state.get('name') == 'CAPITAL_RIGHT' else mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    retcode = int(getattr(res, 'retcode', -1))
    results.append({
        'symbol': sym, 'sector': sector, 'side': side,
        'status': 'executed' if retcode == 10009 else 'failed',
        'retcode': retcode,
        'order_id': int(getattr(res, 'order', 0) or 0),
        'volume': float(vol),
        'entry': entry, 'sl': sl, 'tp': tp,
        'price': entry,
        'comment': getattr(res, 'comment', ''),
    })

# Capital attempt for crypto/commodities
cap_results = []
mt5.shutdown()
ok_cap = mt5.initialize(TERMINAL, login=CAPITAL_LOGIN, password=PW, server=CAPITAL_SERVER)
if ok_cap:
    for c in candidates:
        sym = c['symbol']
        side = c['side']
        if c['sector'] not in ['crypto','commodities']:
            continue
        if sym == 'DOTUSD' and side == 'SHORT':
            continue
        si = mt5.symbol_info(sym)
        if not si:
            cap_results.append({'symbol':sym,'side':side,'status':'blocked_no_symbol_info','broker':'CAPITAL'})
            continue
        mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        if not tick or tick.bid <= 0:
            cap_results.append({'symbol':sym,'side':side,'status':'blocked_no_quote','broker':'CAPITAL'})
            continue
        digits = 2 if any(k in sym for k in ['BTC','ETH','SOL','XRP','DOT','DOGE','XAU','XAG']) else 5
        if side == 'LONG':
            entry = float(tick.ask)
            sl = round(entry - float(c['atr14']) * 0.5, digits)
            tp = round(entry + float(c['atr14']) * 2.0, digits)
            order_type = mt5.ORDER_TYPE_BUY
        else:
            entry = float(tick.bid)
            sl = round(entry + float(c['atr14']) * 0.5, digits)
            tp = round(entry - float(c['atr14']) * 2.0, digits)
            order_type = mt5.ORDER_TYPE_SELL
        vol_min = float(getattr(si, 'volume_min', 0.01))
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': sym,
            'volume': float(vol_min),
            'type': order_type,
            'price': entry,
            'sl': float(sl),
            'tp': float(tp),
            'deviation': 20,
            'magic': 0,
            'comment': 'night_scan_override_capital',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK if state.get('name') == 'CAPITAL_RIGHT' else mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        cap_results.append({
            'symbol': sym, 'side': side, 'broker': 'CAPITAL',
            'status': 'executed' if int(getattr(res,'retcode',-1)) == 10009 else 'failed',
            'retcode': int(getattr(res,'retcode',-1)),
            'order_id': int(getattr(res,'order',0) or 0),
            'volume': float(vol_min),
            'entry': entry, 'sl': sl, 'tp': tp,
            'comment': getattr(res, 'comment', ''),
        })
    mt5.shutdown()
else:
    cap_results = [{'broker':'CAPITAL','status':'init_failed','error':mt5.last_error()}]

out = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'override': True,
    'override_reason': 'operator explicit instruction to set trades from quant report despite 0 high-grade / news block',
    'ftmo_results': results,
    'capital_results': cap_results,
}
out_path = Path('artifacts') / f"execution_override_{datetime.now().strftime('%Y%m%dT%H%MZ')}.json"
out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
print(out_path)
for r in results:
    print(r)
print('---CAPITAL---')
for r in cap_results:
    print(r)