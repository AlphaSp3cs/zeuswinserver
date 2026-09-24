import MetaTrader5 as mt5, json
from pathlib import Path
from dotenv import dotenv_values
from datetime import datetime, timezone
cfg={k:v for k,v in dotenv_values('.env').items() if v is not None}
path=cfg.get('CAPITAL_MT5_TERMINAL')
login=int(cfg.get('CAPITAL_MT5_LOGIN'))
server=cfg.get('CAPITAL_MT5_SERVER')
password=cfg.get('CAPITAL_MT5_PASSWORD')
mt5.shutdown()
ok=mt5.initialize(path=path, login=login, server=server, password=password, portable=True)
print('init', ok, mt5.last_error() if not ok else '')
if not ok: raise SystemExit(1)
acc=mt5.account_info()
print('login', acc.login, 'equity', float(acc.equity), 'free', float(acc.margin_free), 'server', acc.server)
positions = mt5.positions_get() or []
print('positions_count', len(positions))
by_key={}
for p in positions:
    side='LONG' if p.type==mt5.POSITION_TYPE_BUY else 'SHORT'
    key=(p.symbol, side)
    by_key.setdefault(key, []).append({
        'ticket': int(p.ticket), 'volume': float(p.volume), 'profit': float(p.profit),
        'sl': float(p.sl) if p.sl else None, 'tp': float(p.tp) if p.tp else None,
        'comment': p.comment, 'magic': p.magic, 'time': int(p.time)
    })
dups={k:v for k,v in by_key.items() if len(v)>1}
print('duplicate_keys', len(dups))
for k,v in dups.items():
    print('DUP', k, [x['ticket'] for x in v])
mt5.shutdown()
