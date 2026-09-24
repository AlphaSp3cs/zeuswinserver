#!/usr/bin/env python3
"""
practice_trades_capital_right.py
Place small practice trades on Capital.com MT5 RIGHT based on master graded setups.
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone

import MetaTrader5 as mt5

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
SCANDATA = Path(r'C:\Users\bravo-usr1\Desktop\scandata')
CRED = {
    'path': r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe',
    'login': int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685')),
    'password': os.environ.get('CAPITAL_MT5_PASSWORD', ''),
    'server': os.environ.get('CAPITAL_MT5_SERVER', 'Capital.ComBah-Demo'),
}

SETUPS = [
    {
        'symbol': 'ADAUSD',
        'side': 'LONG',
        'composite_score': 66,
        'source': 'master_grader',
        'volume': 0.01,
        'tp_pct': 0.05,
        'sl_pct': -0.05,
    },
    {
        'symbol': 'DOGEUSD',
        'side': 'LONG',
        'composite_score': 66,
        'source': 'master_grader',
        'volume': 0.01,
        'tp_pct': 0.05,
        'sl_pct': -0.05,
    },
]


def init():
    ok = mt5.initialize(**CRED)
    if not ok:
        raise RuntimeError(f'MT5 init failed: {mt5.last_error()}')
    acc = mt5.account_info()
    if acc is None:
        raise RuntimeError('account_info() returned None')
    return acc


def get_tick(symbol):
    if not mt5.symbol_select(symbol, True):
        return None
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        return None
    return {
        'symbol': symbol,
        'bid': tick.bid,
        'ask': tick.ask,
        'digits': info.digits,
        'volume_min': info.volume_min,
        'volume_step': info.volume_step,
    }


def size_for(symbol, equity, price):
    # 1% equity per ticket, minimum volume, account for contract size
    target = equity * 0.01
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    contract = info.trade_contract_size or 1.0
    # notional = price * volume * contract  => volume = target / (price * contract)
    raw = target / (price * contract) if price > 0 else 0
    step = info.volume_step or 0.01
    vol = max(info.volume_min, round((raw / step) * step, 4))
    # skip if minimum ticket notional is too large for equity
    min_notional = (info.volume_min * contract * price) if price else 0
    if min_notional > equity * 0.05:
        return None
    return round(vol, 4)


def build_order(symbol, side, tick, vol, entry, sl, tp):
    if side == 'LONG':
        otype = mt5.ORDER_TYPE_BUY_LIMIT
    else:
        otype = mt5.ORDER_TYPE_SELL_LIMIT
    return {
        'action': mt5.TRADE_ACTION_PENDING,
        'symbol': symbol,
        'volume': vol,
        'type': otype,
        'price': entry,
        'sl': sl,
        'tp': tp,
        'deviation': 20,
        'magic': 20260816,
        'comment': 'Zeus-practice-right',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_RETURN,
    }


def main():
    dry_run = '--dryrun' in sys.argv
    acc = init()
    print(f"CONNECTED login={acc.login} bal={acc.balance:.2f} eq={acc.equity:.2f} trade_mode={acc.trade_mode}")
    open_pos = mt5.positions_get() or []
    open_syms = {p.symbol for p in open_pos}
    print(f'OPEN POSITIONS: {len(open_pos)} | symbols={sorted(open_syms)}')

    results = []
    for setup in SETUPS:
        sym = setup['symbol']
        tick = get_tick(sym)
        if tick is None:
            results.append({**setup, 'status': 'SKIP', 'reason': 'symbol/tick unavailable'})
            print(f"SKIP {sym}: unavailable")
            continue
        if sym in open_syms:
            results.append({**setup, 'status': 'SKIP', 'reason': 'already open'})
            print(f"SKIP {sym}: already open")
            continue
        price = tick['ask'] if setup['side'] == 'LONG' else tick['bid']
        entry = round(price * (1 + setup.get('entry_offset_pct', 0.0)), tick['digits'])
        tp = round(price * (1 + setup['tp_pct']), tick['digits'])
        sl = round(price * (1 + setup['sl_pct']), tick['digits'])
        vol = setup.get('volume') or size_for(sym, acc.equity, price)
        if vol is None or vol <= 0:
            results.append({**setup, 'status': 'SKIP', 'reason': 'invalid size'})
            print(f"SKIP {sym}: invalid size")
            continue
        req = build_order(sym, setup['side'], tick, vol, entry, sl, tp)
        print(f"{'[DRYRUN] ' if dry_run else ''}PLACE {setup['side']} LIMIT {sym} vol={vol} entry={entry} sl={sl} tp={tp}")
        if dry_run:
            results.append({**setup, 'status': 'DRYRUN', 'volume': vol, 'entry': entry, 'sl': sl, 'tp': tp})
            continue
        r = mt5.order_send(req)
        res = {
            **setup,
            'status': 'PLACED' if r.retcode == 10009 else 'FAILED',
            'retcode': r.retcode,
            'order': r.order,
            'comment': r.comment,
            'volume': vol,
            'entry': entry,
            'sl': sl,
            'tp': tp,
        }
        results.append(res)
        print(f"     -> retcode={r.retcode} order={r.order} {r.comment}")

    mt5.shutdown()
    out = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'broker': 'capital_right',
        'account': acc.login,
        'equity': acc.equity,
        'dry_run': dry_run,
        'results': results,
    }
    out_path = SCANDATA / f'practice_trades_capital_right_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
    print(f'Wrote {out_path}')


if __name__ == '__main__':
    main()
