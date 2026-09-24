#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
sys.path.insert(0, str(ROOT / 'scripts'))
from mt5_connect import connect as mt5_connect, shutdown as mt5_shutdown
import MetaTrader5 as mt5

ftmo = mt5_connect('ftmo')
pos = ftmo.positions_get()
print('positions', len(pos) if pos else 0)
for p in (pos or []):
    print(p.ticket, p.symbol, p.volume, p.type, p.price_open, getattr(p,'sl',0), getattr(p,'tp',0), p.profit)
print('last_error', mt5.last_error())
mt5.shutdown()
