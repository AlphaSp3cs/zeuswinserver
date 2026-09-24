#!/usr/bin/env python3
"""monitor_capital.py - Capital.com MT5 position/quote monitor."""
import MetaTrader5 as mt5
from pathlib import Path
from datetime import datetime

PATH = r'C:\Program Files\Capital.com MetaTrader 5	erminal64.exe'
LOG = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/monitor_capital_log.txt')
MAGIC = 20260727

def main():
    lines = [f'
=== CAPITAL MONITOR {datetime.now().isoformat()} ===']
    ok = mt5.initialize(path=PATH)
    lines.append(f'initialize={ok} last_error={mt5.last_error()}')
    if ok:
        ai = mt5.account_info()
        if ai:
            lines.append(f'account={ai.login} balance={ai.balance} equity={ai.equity} profit={ai.profit}')
        positions = mt5.positions_get() or []
        lines.append(f'positions={len(positions)}')
        symbols = set()
        for p in positions:
            symbols.add(p.symbol)
            lines.append(f'POS {p.ticket} {p.symbol} type={p.type} vol={p.volume} open={p.price_open} sl={getattr(p,"sl",None)} tp={getattr(p,"tp",None)} profit={round(p.profit,2)} comment={getattr(p,"comment","")}')
        for sym in sorted(symbols):
            try:
                t = mt5.symbol_info_tick(sym)
                if t:
                    lines.append(f'QUOTE {sym} bid={t.bid} ask={t.ask}')
            except Exception as e:
                lines.append(f'QUOTE_ERR {sym} {e}')
        orders = mt5.orders_get() or []
        lines.append(f'orders={len(orders)}')
        for o in orders:
            lines.append(f'ORDER {o.ticket} {o.symbol} type={o.type} vol={o.volume_current} price={o.price_open} comment={getattr(o,"comment","")}')
        mt5.shutdown()
    else:
        lines.append('NO_CONNECTION')
    LOG.write_text(LOG.read_text() if LOG.exists() else '' + '
'.join(lines) + '
', encoding='utf-8')
    print('
'.join(lines))

if __name__ == '__main__':
    main()
