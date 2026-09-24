import MetaTrader5 as mt5
from pathlib import Path
from dotenv import dotenv_values
cfg={k:v for k,v in dotenv_values('.env').items() if v is not None}
mt5.shutdown()
ok=mt5.initialize(path=cfg.get('CAPITAL_MT5_TERMINAL'), login=int(cfg.get('CAPITAL_MT5_LOGIN')), server=cfg.get('CAPITAL_MT5_SERVER'), password=cfg.get('CAPITAL_MT5_PASSWORD'), portable=True)
print('init', ok, mt5.last_error() if not ok else '')
if not ok: raise SystemExit(1)
info = mt5.symbols_get()
print('symbols_total', len(info))
mode2=[]
for s in info:
    mode = int(getattr(s, 'trade_mode', 0) or 0)
    if mode == 2:
        mode2.append({'symbol': s.name, 'visible': s.visible, 'select': s.select})
print('mode2_count', len(mode2))
for x in mode2[:200]:
    print(x['symbol'], 'visible=', x['visible'], 'select=', x['select'])
for x in mode2[200:400]:
    print(x['symbol'], 'visible=', x['visible'], 'select=', x['select'])
mt5.shutdown()
