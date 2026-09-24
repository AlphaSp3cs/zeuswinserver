#!/usr/bin/env python3
"""
IBKR options placement: try multiple exchanges for chain lookup,
then place nearest ATM calls for 2026-09-15.
"""
import json, sys, time
from pathlib import Path
from datetime import datetime, timezone
from ib_insync import IB, Stock, Option

ROOT = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
ARTIFACTS = ROOT / 'artifacts'
TS = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')
OUT = ARTIFACTS / f'ibkr_options_{TS}.json'

plan = [
    {'underlying': 'NVDA', 'direction': 'LONG_CALL', 'strike': 118.75, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'JPM',  'direction': 'LONG_CALL', 'strike': 185.25, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'SPY',  'direction': 'LONG_CALL', 'strike': 547.41, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'QQQ',  'direction': 'LONG_CALL', 'strike': 473.57, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'AAPL', 'direction': 'LONG_CALL', 'strike': 213.75, 'expiry': '20260915', 'qty': 1},
]

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=2002, timeout=20)
print('CONNECTED clientId=2002')

results = []
for leg in plan:
    sym = leg['underlying']
    stk = Stock(sym, 'SMART', 'USD')
    ib.qualifyContracts(stk)
    conid = stk.conId
    print(f'\n{sym} conId={conid}')

    # Try multiple option exchanges for chain lookup
    exchanges = ['SMART', 'CBOE', 'AMEX', 'ARCA', 'ISE', 'PHLX', 'NASDAQ']
    chains = []
    for ex in exchanges:
        try:
            params = ib.reqSecDefOptParams(sym, ex, 'STK', conid)
            if params:
                chains.extend(params)
                print(f'  chain {ex}: {len(params)} param groups')
                break
        except Exception as e:
            print(f'  chain {ex}: {e}')

    if not chains:
        results.append({'underlying': sym, 'status': 'NO_CHAIN', 'leg': leg})
        continue

    # flatten expirations/strikes
    target_exp = leg['expiry']
    target_strike = leg['strike']
    right = 'C'
    candidates = []
    for p in chains:
        if target_exp in p.expirations:
            for strike in p.strikes:
                candidates.append((float(strike), right, p.exchange, target_exp))
    if not candidates:
        # fallback: nearest expiry
        for p in chains:
            if p.expirations:
                exp = sorted(p.expirations)[0]
                for strike in p.strikes:
                    candidates.append((float(strike), right, p.exchange, exp))
    print(f'  candidates around {target_strike}: {len(candidates)}')

    # pick nearest strike to target
    candidates.sort(key=lambda x: abs(x[0]-target_strike))
    chosen = candidates[0] if candidates else None
    if not chosen:
        results.append({'underlying': sym, 'status': 'NO_STRIKE', 'leg': leg})
        continue

    opt = Option(sym, chosen[2], chosen[0], chosen[2], 'USD', right=right)
    ib.qualifyContracts(opt)
    print(f'  chosen {opt.conId} {opt.exchange} strike={opt.strike} expiry={opt.lastTradeDateOrContractMonth}')
    try:
        order = ib.Order()
        order.action = 'BUY'
        order.orderType = 'MKT'
        order.totalQuantity = leg['qty']
        order.transmit = True
        trade = ib.placeOrder(opt, order)
        print(f'  order placed id={trade.order.orderId} status={trade.orderStatus.status}')
        results.append({
            'underlying': sym,
            'status': 'PLACED',
            'conId': opt.conId,
            'exchange': opt.exchange,
            'strike': opt.strike,
            'expiry': opt.lastTradeDateOrContractMonth,
            'right': opt.right,
            'orderId': trade.order.orderId,
            'orderStatus': trade.orderStatus.status,
            'leg': leg,
        })
    except Exception as e:
        print(f'  order failed: {e}')
        results.append({'underlying': sym, 'status': 'ORDER_FAILED', 'error': str(e), 'leg': leg, 'opt': str(opt)})

ib.disconnect()
print('\nDISCONNECTED')
out = {'ts': datetime.now(timezone.utc).isoformat(), 'gateway': '127.0.0.1:4002', 'results': results}
OUT.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
print(f'WROTE {OUT}')
print(json.dumps(results, indent=2, default=str))
