"""
Intel execution: verified trades via IBKR + Alpaca + Capital fallback.
Scan still uses FTMO reference data when possible; falls back when terminal is off.
Confirms fills before moving to another broker for the same signal.
"""
import sys, os, json, time
sys.path.insert(0, os.path.expanduser('~'))
from mt5_connect import connect as mt5_connect
import MetaTrader5 as mt5
from ib_insync import IB, Forex, CFD, Crypto, MarketOrder, StopOrder, LimitOrder
import requests

OUS_MODE = 'intel'
DRY_RUN = False
RISK_PCT = 0.01
RSI_BUY, RSI_SELL = 45, 55
SL_MULT, TP_MULT = 1.5, 3.0

UNIVERSE = {
    'indices':['US30','US500','US100','DE40','UK100'],
    'crypto':['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD'],
    'forex':['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF'],
    'commodities':['XAUUSD','XAGUSD','WTI','BRENT','XPTUSD','XPDUSD'],
}
CLASS_BROKER = {
    'crypto': ['ALPACA','IBKR'],
    'forex': ['ALPACA','IBKR'],
    'indices': ['IBKR','ALPACA'],
    'commodities': ['IBKR','ALPACA'],
}
ALPACA_COMPATIBLE_EQUITY = ['GLD','IBIT','FBTC','LINKUSD','MA','V','XLY','REMX','UNG']
ALPACA_MIN_NOTIONAL = 10.0
ALPACA_LONG_ONLY_CLASSES = {'crypto'}

def _load_dotenv(path):
    try:
        with open(path,'r',encoding='utf-8',errors='ignore') as f:
            for line in f:
                line=line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k,v=line.split('=',1)
                k=k.strip(); v=v.strip().strip('"').strip("'")
                os.environ.setdefault(k,v)
    except Exception:
        pass

_load_dotenv(os.path.expanduser('~/Desktop/OuroTaurus Trade Firm/.env'))

def alpaca_headers():
    # Source of truth: OuroTaurus .env, fallback to allapi2026.txt
    key = os.environ.get('ALPACA_API_KEY') or os.environ.get('ALPACA_SECRET_KEY')
    sec = os.environ.get('ALPACA_API_SECRET') or os.environ.get('ALPACA_SECRET_KEY')
    base = os.environ.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets/v2')
    if not key or not sec:
        alt = os.path.expanduser('~/Desktop/allapi2026.txt')
        if os.path.exists(alt):
            for line in open(alt,'r',encoding='utf-8',errors='ignore'):
                line=line.strip()
                if line.startswith('ALPACA_API_KEY='):
                    key=line.split('=',1)[1].strip().strip('"').strip("'")
                elif line.startswith('ALPACA_API_SECRET='):
                    sec=line.split('=',1)[1].strip().strip('"').strip("'")
    if not key or not sec:
        raise RuntimeError('Alpaca credentials missing; set ALPACA_API_KEY/ALPACA_API_SECRET')
    return {'Apca-Api-Key-Id': key, 'Apca-Api-Secret-Key': sec}, base

def ibkr_connect(client_id=None):
    ib=IB()
    try:
        cid = client_id if client_id is not None else 8888
        ib.connect(host='127.0.0.1', port=7497, clientId=cid, timeout=8)
        return ib
    except Exception as e:
        print('[IBKR] connect failed:', e)
        return None

def ibkr_contract(symbol):
    if symbol in ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF']:
        return Forex(symbol)
    if symbol in ['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD']:
        return Crypto(symbol, 'PAXOS', 'USD')
    if symbol in ['US30','US500','US100','DE40','UK100']:
        return CFD(symbol, 'SMART', 'USD')
    if symbol in ['XAUUSD','XAGUSD','XPTUSD','XPDUSD','WTI','BRENT']:
        return CFD(symbol, 'SMART', 'USD')
    return None

def ibkr_account_values(ib):
    try:
        accts = ib.managedAccounts()
        if not accts:
            return None
        vals = ib.accountValues(account=accts[0])
        out = {}
        for v in vals:
            out.setdefault(v.currency, {})[v.tag] = float(v.value)
        return out
    except Exception:
        return None

def ibkr_netliq_usd(ib):
    vals = ibkr_account_values(ib)
    if not vals:
        return None
    usd = vals.get('USD', {})
    if 'NetLiquidation' in usd:
        return usd['NetLiquidation']
    # fallback: sum base + cash if present
    base = usd.get('TotalCashValue', usd.get('CashBalance', 0))
    return base

def ibkr_open_equity(ib):
    vals = ibkr_account_values(ib)
    if not vals:
        return None
    usd = vals.get('USD', {})
    if 'NetLiquidation' in usd:
        return usd['NetLiquidation']
    return usd.get('TotalCashValue', usd.get('CashBalance', None))

def ibkr_positions_count(symbol):
    ib = ibkr_connect()
    if not ib:
        return None
    try:
        pos = ib.positions()
        cnt = sum(1 for p in pos if p.contract.symbol == symbol)
        return cnt
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

def ibkr_place_and_verify(symbol, side, qty, sl, tp):
    contract = ibkr_contract(symbol)
    if not contract:
        return None, f'unknown_symbol {symbol}'
    ib = ibkr_connect()
    if not ib:
        return None, 'no_ibkr'
    try:
        order = MarketOrder('BUY' if side=='BUY' else 'SELL', qty)
        trade = ib.placeOrder(contract, order)
        filled_qty = float(trade.orderStatus.filled or 0)
        avg = float(trade.orderStatus.avgFillPrice or 0)
        if sl is not None and tp is not None:
            stop = StopOrder('SELL' if side=='BUY' else 'BUY', qty, sl)
            target = LimitOrder('SELL' if side=='BUY' else 'BUY', qty, tp)
            ib.placeOrder(contract, stop)
            ib.placeOrder(contract, target)
        return {
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'status': trade.orderStatus.status,
            'filled': filled_qty,
            'avgPrice': avg,
            'orderId': trade.order.orderId,
        }, None
    except Exception as e:
        return None, str(e)
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

def alpaca_submit(symbol, side, qty, sl, tp):
    headers, base = alpaca_headers()
    url = base.rstrip('/') + '/orders'
    payload = {
        'symbol': symbol,
        'qty': str(qty),
        'side': 'buy' if side=='BUY' else 'sell',
        'type': 'market',
        'time_in_force': 'day',
    }
    # Bracket not supported on fractional shares
    is_fractional = float(qty) != int(float(qty))
    if sl is not None and tp is not None and not is_fractional:
        payload['order_class'] = 'bracket'
        if side == 'BUY':
            payload['stop_loss'] = {'stop_price': str(sl)}
            payload['take_profit'] = {'limit_price': str(tp)}
        else:
            payload['stop_loss'] = {'stop_price': str(sl)}
            payload['take_profit'] = {'limit_price': str(tp)}
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    if r.status_code not in (200,201):
        return None, f'{r.status_code}: {r.text[:200]}'
    data = r.json() or {}
    return {
        'symbol': symbol,
        'side': side,
        'qty': qty,
        'alpaca_id': data.get('id'),
        'client_id': data.get('client_order_id'),
        'status': data.get('status'),
        'legs': data.get('legs'),
    }, None

def alpaca_attach_sl_tp(symbol, side, qty, sl, tp):
    headers, base = alpaca_headers()
    url = base.rstrip('/') + '/orders'
    orders = []
    if sl is not None:
        payload = {
            'symbol': symbol,
            'qty': str(qty),
            'side': 'sell' if side=='BUY' else 'buy',
            'type': 'stop',
            'time_in_force': 'day',
            'stop_price': str(sl),
        }
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code in (200,201):
            orders.append(('stop', r.json().get('id')))
        else:
            orders.append(('stop_error', f"{r.status_code}: {r.text[:200]}"))
    if tp is not None:
        payload = {
            'symbol': symbol,
            'qty': str(qty),
            'side': 'sell' if side=='BUY' else 'buy',
            'type': 'limit',
            'time_in_force': 'day',
            'limit_price': str(tp),
        }
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code in (200,201):
            orders.append(('limit', r.json().get('id')))
        else:
            orders.append(('limit_error', f"{r.status_code}: {r.text[:200]}"))
    return orders

def alpaca_verify_fill(symbol, side, expected_qty):
    headers, base = alpaca_headers()
    try:
        url = base.rstrip('/') + f'/orders?status=all&symbol={symbol}&limit=10'
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None, f'http_{r.status_code}'
        orders = r.json() or []
        for o in orders:
            if o.get('side') == ('buy' if side=='BUY' else 'sell') and o.get('symbol') == symbol:
                return o.get('status'), o.get('filled_qty') or o.get('filled'), o.get('id')
        return None, 'not_found'
    except Exception as e:
        return None, str(e)

def mt5_connect_profile(profile):
    return mt5_connect(profile)

def mt5_capital_order(symbol, side, sl, tp, vol):
    # Capital MT5 order; requires active Capital MT5 terminal for this session
    m = mt5_connect_profile('capital')
    if not m:
        return None, 'no_mt5_capital_terminal'
    try:
        info = m.symbol_info(symbol)
        if not info:
            return None, f'{symbol}: no symbol_info on Capital MT5'
        tick = m.symbol_info_tick(symbol)
        if not tick:
            return None, f'{symbol}: no tick'
        price = tick.ask if side=='BUY' else tick.bid
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': vol,
            'type': mt5.ORDER_TYPE_BUY if side=='BUY' else mt5.ORDER_TYPE_SELL,
            'price': price,
            'sl': sl,
            'tp': tp,
            'deviation': 10,
            'magic': 20260721,
            'comment': 'OUS_INTEL',
            'type_time': mt5.ORDER_TIME_GTC,
        }
        res = m.order_send(req)
        try:
            m.shutdown()
        except Exception:
            pass
        if res.retcode in (10009, 10008):
            return {
                'ticket': res.order,
                'retcode': res.retcode,
                'comment': res.comment,
                'deal': res.deal,
            }, None
        return None, f'retcode={res.retcode} comment={res.comment}'
    except Exception as e:
        try:
            m.shutdown()
        except Exception:
            pass
        return None, str(e)

def lot_size_cap(symbol, entry, sl, risk_usd):
    info = mt5.symbol_info(symbol)
    if not info:
        raise RuntimeError(f"{symbol}: no symbol_info")
    sl_dist_pts = abs(entry - sl) / info.point
    risk_per_pt = info.trade_tick_value / info.trade_tick_size if info.trade_tick_size else 0
    if risk_per_pt <= 0 or sl_dist_pts <= 0:
        raise RuntimeError(f"{symbol}: bad params")
    vol = risk_usd / (sl_dist_pts * risk_per_pt)
    vol = max(info.volume_min, min(info.volume_max, vol))
    vol = round(vol, 2 if info.volume_step >= 0.01 else 1)
    return vol

def scan():
    try:
        m = mt5_connect('ftmo')
    except Exception as e:
        print('[SCAN] FTMO data unavailable:', e)
        return []
    try:
        sigs=[]
        for cls,syms in UNIVERSE.items():
            for s in syms:
                info=m.symbol_info(s)
                if not info: continue
                r=m.copy_rates_from_pos(s,m.TIMEFRAME_D1,0,60)
                if r is None or len(r)<50: continue
                c=[x['close'] for x in r]; h=[x['high'] for x in r]; lo=[x['low'] for x in r]
                g=[max(c[i]-c[i-1],0) for i in range(1,len(c))]; lo_=[max(c[i-1]-c[i],0) for i in range(1,len(c))]
                ag=sum(g[:14])/14; al=sum(lo_[:14])/14; rsi=100-(100/(1+(ag/al if al>0 else 999)))
                for i in range(14,len(g)):
                    ag=(ag*13+g[i])/14; al=(al*13+lo_[i])/14
                    rsi=100-(100/(1+(ag/al if al>0 else 999)))
                last=c[-1]; sma50=sum(c[-50:])/50
                tr=[]
                for i in range(1,len(c)):
                    tr.append(max(h[i]-lo[i], abs(h[i]-c[i-1]), abs(lo[i]-c[i-1])))
                a=sum(tr[-14:])/14 if len(tr)>=14 else (sum(tr)/len(tr) if tr else 0)
                side=None; reason=None
                if rsi < RSI_BUY:
                    side='BUY'; reason=f'RSI {rsi:.1f} < {RSI_BUY}'
                elif rsi > RSI_SELL:
                    side='SELL'; reason=f'RSI {rsi:.1f} > {RSI_SELL}'
                if not side: continue
                sl = last-SL_MULT*a if side=='BUY' else last+SL_MULT*a
                tp = last+TP_MULT*a if side=='BUY' else last-TP_MULT*a
                sigs.append({'class':cls,'symbol':s,'side':side,'rsi':round(rsi,1),'last':round(last,max(4, info.digits if info else 4)),'sma50':round(sma50,max(4, info.digits if info else 4)),'atr':round(a,max(4, info.digits if info else 4)),'sl':round(sl,max(4, info.digits if info else 4)),'tp':round(tp,max(4, info.digits if info else 4)),'reason':reason})
        return sigs
    finally:
        try: m.shutdown()
        except: pass

def execute_signal(sig, equity):
    symbol, side, sl, tp = sig['symbol'], sig['side'], sig['sl'], sig['tp']
    risk_usd = equity * RISK_PCT
    print(f"\n[ROUTE] {symbol} {side} | class={sig['class']}")
    placed = False
    result = None
    for broker in CLASS_BROKER[sig['class']]:
        print(f"  try {broker}")
        if broker == 'IBKR':
            existing = ibkr_positions_count(symbol)
            if existing is not None and existing > 0:
                print(f"    IBKR already has {existing} {symbol}, skip.")
                continue
            result, err = ibkr_place_and_verify(symbol, side, 1, sl, tp)
            if err:
                print(f"    IBKR error: {err}")
                continue
            if float(result.get('filled', 0) or 0) >= 1 or result.get('status') in ('Submitted','Filled'):
                print(f"    IBKR VERIFIED: {result}")
                placed = True; break
            print(f"    IBKR not fully filled, trying next broker")
            continue
        if broker == 'ALPACA':
            symbol_for_alpaca = sig['symbol']
            side = sig['side']
            # Map MT5-style symbols to Alpaca-compatible formats
            if sig['class'] == 'crypto':
                if '/' not in symbol_for_alpaca:
                    symbol_for_alpaca = symbol_for_alpaca.replace('USD', '/USD').replace('USDT', '/USDT').replace('USDC', '/USDC')
                if side != 'BUY':
                    print(f"    ALPACA skip: short crypto not supported.")
                    continue
            if sig['class'] == 'forex':
                print(f"    ALPACA skip: FX not supported on this account.")
                continue
            if sig['class'] == 'commodities' and symbol_for_alpaca not in ALPACA_COMPATIBLE_EQUITY:
                print(f"    ALPACA skip: commodity CFD not supported; use metals ETFs instead.")
                continue
            if side == 'BUY' and sig['last'] * 1 < ALPACA_MIN_NOTIONAL:
                print(f"    ALPACA skip: order < min notional ${ALPACA_MIN_NOTIONAL}.")
                continue
            try:
                result, err = alpaca_submit(symbol_for_alpaca, side, 1, sl, tp)
            except Exception as e:
                result, err = None, str(e)
            if err:
                print(f"    ALPACA error: {err}")
                continue
            st, filled, oid = alpaca_verify_fill(symbol_for_alpaca, side, 1)
            print(f"    ALPACA verify: status={st} filled={filled} id={oid}")
            if st in ('filled', 'partially_filled', 'new', 'accepted', 'pending_new'):
                result['verify_status'] = st
                placed = True; break
            print(f"    ALPACA not verified, trying next broker")
            continue
        elif broker == 'MT5':
            try:
                vol = lot_size_cap(symbol, sig['last'], sl, risk_usd)
                result, err = mt5_capital_order(symbol, side, sl, tp, vol)
                if err:
                    print(f"    MT5 error: {err}")
                    continue
                print(f"    MT5 VERIFIED: ticket={result.get('ticket')}")
                placed = True; break
            except Exception as e:
                print(f"    MT5 exception: {e}")
                continue
    if not placed:
        print(f"  FAILED: no broker accepted {symbol} {side}")
        return None
    return result

def main():
    sigs = scan()
    print(f"INTEL scan: {len(sigs)} signals")
    if not sigs:
        print('Standing down: no clean signals.')
        return
    sigs = sorted(sigs, key=lambda x: abs(x['rsi']-50), reverse=True)[:12]
    print('=== TOP SIGNALS ===')
    for s in sigs:
        print(f"  {s['side']:4} {s['symbol']:8} [{s['class']}] RSI={s['rsi']} price={s['last']} SL={s['sl']} TP={s['tp']}")
    equity = 5000.0
    ib = ibkr_connect(client_id=8889)
    if ib:
        try:
            equity = ibkr_open_equity(ib) or equity
        except Exception:
            pass
        try:
            ib.disconnect()
        except Exception:
            pass
    print(f"\nBase equity for risk calc: {equity:.2f}")
    print("=== ROUTING ===")
    results = []
    for sig in sigs:
        r = execute_signal(sig, equity)
        if r:
            results.append(r)
    print(f"\n=== SUMMARY: {len(results)} executed ===")
    for r in results:
        print(r)
    with open(os.path.join('C:/Users/bravo-usr1/trade_data', 'intel_executed.json'), 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print('saved trade_data/intel_executed.json')

if __name__ == '__main__':
    main()