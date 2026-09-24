
import json, datetime, os, sys
import MetaTrader5 as mt5
from datetime import datetime as dt

# Load credentials
creds_path = r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\broker_creds.json'
with open(creds_path, 'r') as f:
    creds = json.load(f)

ftmo = creds['ftmo']

# Initialize FTMO LEFT
login = int(ftmo['login'])
password = ftmo['password']
server = ftmo['server']
path = ftmo['path']

print("STEP 0: INIT FTMO LEFT")
print(f"  login={login} server={server}")

init_ok = mt5.initialize(path=path, login=login, password=password, server=server)
if not init_ok:
    err = mt5.last_error()
    print(f"  init failed: {err}")
    sys.exit(1)
acc = mt5.account_info()
if acc is None:
    print("  account_info() returned None")
    sys.exit(1)
bound_login = getattr(acc, 'login', None)
print(f"  bound login={bound_login}")
if int(bound_login) != login:
    print(f"  LOGIN MISMATCH: expected {login}, got {bound_login}")
    sys.exit(1)
print("  preflight OK")

# Approved actionables from scan
symbols_map = {
    'XAUUSD': {'entry': 4307.00, 'sl': 4285.96, 'tp': 4349.07, 'rr': 2.0},
    'XAGUSD': {'entry': 62.27, 'sl': 61.76, 'tp': 63.29, 'rr': 2.0},
    'EURJPY': {'entry': 182.18, 'sl': 182.02, 'tp': 182.51, 'rr': 2.0},
    'GBPJPY': {'entry': 212.35, 'sl': 212.16, 'tp': 212.74, 'rr': 2.0},
    'CHFJPY': {'entry': 195.37, 'sl': 195.17, 'tp': 195.76, 'rr': 1.95},
    'PALLADIUM': {'entry': 1370.50, 'sl': 1357.50, 'tp': 1396.50, 'rr': 2.0},
    'PLATINUM': {'entry': 1751.30, 'sl': 1736.30, 'tp': 1781.30, 'rr': 2.0},
}

# Live state
print("\nSTEP 1: LIVE STATE")
positions = mt5.positions_get()
if positions is None:
    positions = []
positions = [p._asdict() for p in positions]
print(f"  open positions={len(positions)}")
for p in positions:
    print(f"    {p.get('symbol')} ticket={p.get('ticket')} type={p.get('type')} volume={p.get('volume')} price={p.get('price')} sl={p.get('sl')} tp={p.get('tp')}")

# Duplicate flatten
by_sym = {}
for p in positions:
    by_sym.setdefault(p.get('symbol'), []).append(p)
for sym, plist in by_sym.items():
    if len(plist) > 1:
        print(f"  duplicate flatten: {sym} count={len(plist)}")
        plist_sorted = sorted(plist, key=lambda x: x.get('ticket', 0))
        keep = plist_sorted[-1]
        for dup in plist_sorted[:-1]:
            tick = mt5.symbol_info_tick(dup['symbol'])
            price = tick.bid if int(dup['type']) == mt5.ORDER_TYPE_BUY else tick.ask
            req = {
                'action': mt5.TRADE_ACTION_DEAL,
                'position': int(dup['ticket']),
                'symbol': dup['symbol'],
                'volume': float(dup['volume']),
                'type': mt5.ORDER_TYPE_SELL if int(dup['type']) == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                'price': float(price),
                'deviation': 10,
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_FOK,
            }
            res = mt5.order_send(req)
            print(f"    closed ticket={dup['ticket']} retcode={getattr(res,'retcode',None)} order={getattr(res,'order',None)}")
        pos2 = mt5.positions_get(symbol=sym)
        if pos2 is None:
            pos2 = []
        print(f"    post-flatten {sym} count={len(pos2)}")

# Symbol visibility/tradeability
print("\nSTEP 2: SYMBOL GATE")
executable = {}
for sym in symbols_map.keys():
    info = mt5.symbol_info(sym)
    if info is None:
        print(f"  {sym}: symbol_info returned None -> broker_unavailable")
        continue
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if tick is None or tick.bid <= 0 or tick.ask <= 0:
        print(f"  {sym}: invalid tick -> broker_unavailable")
        continue
    trade_mode = getattr(info, 'trade_mode', None)
    visible = getattr(info, 'visible', False)
    print(f"  {sym}: visible={visible} trade_mode={trade_mode} bid={tick.bid} ask={tick.ask}")
    executable[sym] = symbols_map[sym]
    executable[sym]['bid'] = float(tick.bid)
    executable[sym]['ask'] = float(tick.ask)
    executable[sym]['trade_mode'] = trade_mode

print(f"\n  executable symbols={list(executable.keys())}")

# Volume discipline
print("\nSTEP 3: VOLUME DISCIPLINE")
equity = float(mt5.account_info().equity)
print(f"  equity={equity}")
risk_cap = equity * 0.08
print(f"  total risk cap={risk_cap}")
for sym, plan in executable.items():
    info = mt5.symbol_info(sym)
    vol_min = float(getattr(info, 'volume_min', 0.01))
    vol_step = float(getattr(info, 'volume_step', 0.01))
    contract = float(getattr(info, 'trade_contract_size', 1.0))
    sl = plan['sl']
    entry = plan['entry']
    risk_per_unit = abs(entry - sl)
    raw_vol = (equity * 0.01) / (risk_per_unit * contract) if risk_per_unit > 0 else 0
    norm = max(vol_min, (int(raw_vol / vol_step) * vol_step) if vol_step else raw_vol)
    norm = round(norm, 2)
    plan['volume'] = norm
    print(f"  {sym}: raw_vol={raw_vol:.4f} norm={norm}")

# Execution
print("\nSTEP 4: EXECUTION")
execution_report = []
for sym, plan in executable.items():
    entry = plan['entry']
    sl = plan['sl']
    tp = plan['tp']
    volume = plan['volume']
    price = float(plan.get('ask', entry))
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': float(volume),
        'type': mt5.ORDER_TYPE_BUY,
        'price': price,
        'sl': float(sl),
        'tp': float(tp),
        'deviation': 20,
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_FOK,
        'comment': 'zeus_auto_exec',
    }
    res = mt5.order_send(req)
    retcode = getattr(res, 'retcode', None)
    order_id = getattr(res, 'order', None)
    deal = getattr(res, 'deal', None)
    print(f"  {sym} LONG {volume} @ {price} SL={sl} TP={tp} -> retcode={retcode} order={order_id} deal={deal}")
    execution_report.append({
        'symbol': sym,
        'direction': 'LONG',
        'volume': volume,
        'entry': price,
        'sl': sl,
        'tp': tp,
        'retcode': retcode,
        'order_id': order_id,
        'deal': deal,
    })

# Verify positions
print("\nSTEP 5: VERIFY")
positions_after = mt5.positions_get()
if positions_after is None:
    positions_after = []
positions_after = [p._asdict() for p in positions_after]
print(f"  post positions={len(positions_after)}")
for p in positions_after:
    print(f"    {p.get('symbol')} ticket={p.get('ticket')} type={p.get('type')} volume={p.get('volume')} price={p.get('price')} sl={p.get('sl')} tp={p.get('tp')}")

# Save report
out_dir = r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm'
os.makedirs(out_dir, exist_ok=True)
ts = dt.utcnow().strftime('%Y-%m-%dT%H%M%SZ')
report_path = os.path.join(out_dir, f'execution_report_{ts}.md')
with open(report_path, 'w') as f:
    f.write('# FTMO LEFT Execution Report\n')
    f.write(f'Timestamp: {ts}\n')
    f.write(f'Executable symbols: {", ".join(executable.keys())}\n\n')
    f.write('## Results\n')
    for r in execution_report:
        f.write(json.dumps(r) + '\n')
print(f"\nReport saved: {report_path}")