
import MetaTrader5 as mt5, json
from pathlib import Path
from dotenv import dotenv_values
cfg={k:v for k,v in dotenv_values('.env').items() if v is not None}
path = cfg.get('CAPITAL_MT5_TERMINAL')
login = int(cfg.get('CAPITAL_MT5_LOGIN'))
server = cfg.get('CAPITAL_MT5_SERVER')
password = cfg.get('CAPITAL_MT5_PASSWORD')
try:
    mt5.shutdown()
except Exception:
    pass
ok = mt5.initialize(path=path, login=login, server=server, password=password, portable=True)
out={'init': ok, 'last_error': mt5.last_error() if not ok else None}
if ok:
    acc = mt5.account_info()
    out['login'] = acc.login if acc else None
    out['equity'] = float(acc.equity) if acc else None
    out['margin_free'] = float(acc.margin_free) if acc else None
    out['server'] = acc.server if acc else None
    positions = mt5.positions_get() or []
    out['positions'] = []
    for p in positions:
        out['positions'].append({
            'symbol': p.symbol, 'ticket': int(p.ticket), 'type': int(p.type), 'volume': float(p.volume),
            'profit': round(float(p.profit),2), 'sl': float(p.sl) if p.sl else None, 'tp': float(p.tp) if p.tp else None,
            'comment': p.comment, 'magic': p.magic
        })
    out['positions_count'] = len(positions)
    symbols = ['CORN','LTCUSD','SOYBEAN','AVAXUSD','HK50','BNBUSD','SHIBUSD','COTTON','EURUSD','GBPUSD','XAUUSD','US30','US100']
    out['symbols'] = {}
    for sym in symbols:
        info = mt5.symbol_info(sym)
        if not info:
            out['symbols'][sym] = None
            continue
        out['symbols'][sym] = {
            'trade_mode': int(getattr(info, 'trade_mode', 0) or 0),
            'volume_step': float(getattr(info, 'volume_step', 0) or 0),
            'volume_min': float(getattr(info, 'volume_min', 0) or 0),
            'contract_size': float(getattr(info, 'trade_contract_size', 0) or 0),
            'digits': int(getattr(info, 'digits', 0) or 0),
            'point': float(getattr(info, 'point', 0) or 0)
        }
    mt5.shutdown()
print(json.dumps(out, indent=2))
