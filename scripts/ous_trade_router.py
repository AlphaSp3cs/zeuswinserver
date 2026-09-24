"""
OUS TRADE ROUTER v2 — broker-agnostic.
Add a broker once here, then use it everywhere.
"""

import sys, os, datetime, requests, json
from pathlib import Path
import MetaTrader5 as mt5
from ib_insync import IB, Crypto, Forex, Stock, CFD, MarketOrder, LimitOrder

BASE = Path(__file__).resolve().parent.parent

OUT='C:/Users/bravo-usr1/trade_data'
SIGNAL_LOG='C:/Users/bravo-usr1/executed_signals.json'
DRY_RUN = os.environ.get('DRY_RUN','true').lower() in ('1','true','yes','y')
RISK_PCT=0.01
DCA_MODE = True
DCA_CAP_PCT = 0.02
RSI_BUY  = int(os.environ.get('RSI_BUY','45'))
RSI_SELL = int(os.environ.get('RSI_SELL','55'))
_FTMO_RSI_BUY  = int(os.environ.get('FTMO_RSI_BUY', RSI_BUY))
_FTMO_RSI_SELL = int(os.environ.get('FTMO_RSI_SELL', RSI_SELL))

OUS_MODE = os.environ.get('OUS_MODE', 'intel').lower()
if OUS_MODE not in ('ftmo','intel'):
    raise ValueError(f"OUS_MODE must be 'ftmo' or 'intel', got {OUS_MODE!r}")

sys.path.insert(0, os.path.expanduser('~'))
from mt5_connect import connect as mt5_connect

UNIVERSE = {
 'indices':['US30','US500','US100','DE40','UK100'],
 'crypto':['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD'],
 'forex':['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF','NZDUSD','USDCAD'],
 'commodities':['XAUUSD','XAGUSD','WTI','BRENT','XPTUSD','XPDUSD'],
 'futures':['ES','NQ','YM','GC','SI','ZN','ZB','CL','NG'],
 'asian_indices':['JP225','HK50'],
}

# ---------------------------------------------------------------------------
# BROKER DEFINITIONS — add one section per broker to expand
# ---------------------------------------------------------------------------

BROKER = {
    'FTMO': {
        'type': 'mt5',
        'profile': 'ftmo',
        'classes': ['crypto','forex','commodities','indices','asian_indices'],
    },
    'CAPITAL': {
        'type': 'mt5',
        'profile': 'capital',
        'classes': ['crypto','forex','commodities','indices','asian_indices'],
        'bin': r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe',
        'login': 1028685,
        'server': 'Capital.ComBah-Demo',
    },
    'ALPACA': {
        'type': 'alpaca',
        'classes': ['indices','crypto','forex'],
        'base': 'https://paper-api.alpaca.markets/v2',
    },
    'IBKR': {
        'type': 'ibkr',
        'classes': ['crypto','forex','indices','commodities','futures'],
        'host': '127.0.0.1',
        'port': 4002,
        'client_id': 2002,
        'paper_acct': 'DUN644847',
    },
    'OANDA': {
        'type': 'oanda',
        'classes': ['crypto','forex','commodities','indices'],
    },
    'ETORO': {
        'type': 'etoro',
        'classes': ['crypto','forex','commodities','indices'],
        'base': 'https://public-api.etoro.com',
        'api_key': '',
        'user_key': '',
        'short_transaction': 'SHORT',
        'long_transaction': 'LONG',
    },
}

# Runtime mode routing
if OUS_MODE == 'ftmo':
    SCAN_BROKERS = ['FTMO']
    EXEC_BROKERS = ['FTMO']
else:
    SCAN_BROKERS = ['FTMO']
    EXEC_BROKERS = ['FTMO', 'CAPITAL', 'ALPACA', 'IBKR', 'OANDA', 'ETORO']

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _load_dotenv(path):
    try:
        with open(path,'r',encoding='utf-8',errors='ignore') as f:
            for line in f:
                line=line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k,v=line.split('=',1); k=k.strip(); v=v.strip().strip('"').strip("'")
                os.environ.setdefault(k,v)
    except Exception:
        pass

_load_dotenv(os.path.expanduser('~/Desktop/OuroTaurus Trade Firm/.env'))

def _alpaca_creds():
    alt = os.path.expanduser('~/Desktop/OuroTaurus Trade Firm/allapi2026.txt')
    key = os.environ.get('ALPACA_API_KEY') or os.environ.get('ALPACA_SECRET_KEY')
    sec = os.environ.get('ALPACA_API_SECRET') or os.environ.get('ALPACA_SECRET_KEY')
    if not key and os.path.exists(alt):
        for line in open(alt,'r',encoding='utf-8',errors='ignore'):
            line=line.strip()
            if line.startswith('ALPACA_API_KEY='): key=line.split('=',1)[1].strip().strip('"').strip("'")
            elif line.startswith('ALPACA_API_SECRET='): sec=line.split('=',1)[1].strip().strip('"').strip("'")
    if not key or not sec:
        raise RuntimeError('Alpaca credentials missing')
    return key, sec

def _broker_for_class(cls):
    return [b for b in EXEC_BROKERS if cls in BROKER[b]['classes']]

# ---------------------------------------------------------------------------
# CONNECTORS — one function per broker type
# ---------------------------------------------------------------------------

def _mt5_connect(profile):
    return mt5_connect(profile)

def _ibkr_connect(client_id=None):
    ib=IB()
    try:
        cid = client_id if client_id is not None else 9000
        ib.connect(host=BROKER['IBKR']['host'], port=BROKER['IBKR']['port'], clientId=cid, timeout=8)
        return ib
    except Exception as e:
        print('[IBKR] connect failed:', e)
        return None

def _oanda_creds():
    data = BROKER.get('OANDA', {})
    api_key = data.get('api_key') or os.environ.get('OANDA_API_KEY')
    account_id = data.get('practice_account_id') or os.environ.get('OANDA_ACCOUNT_ID')
    base_url = data.get('base_url') or 'https://api-fxpractice.oanda.com/v3'
    if not api_key or not account_id:
        raise RuntimeError('Oanda credentials missing')
    return api_key, account_id, base_url

def _oanda_connect():
    api_key, account_id, base_url = _oanda_creds()
    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept-Datetime-Format': 'RFC3339',
    })
    return session, account_id, base_url

def _etoro_creds():
    data = BROKER.get('ETORO', {})
    api_key = data.get('api_key') or os.environ.get('ETORO_API_KEY')
    user_key = data.get('user_key') or os.environ.get('ETORO_USER_KEY')
    base_url = (data.get('base') or os.environ.get('ETORO_BASE_URL') or 'https://public-api.etoro.com').rstrip('/')
    mode = (data.get('mode') or os.environ.get('ETORO_MODE') or 'demo').lower().strip()
    if mode not in ('demo','live'):
        mode = 'demo'
    if not api_key or not user_key:
        secure_path = BASE / '.broker_creds_secure.json'
        if secure_path.exists():
            try:
                secure = json.loads(secure_path.read_text(encoding='utf-8'))
                etoro = secure.get('etoro') or secure.get('ETORO') or {}
                api_key = api_key or etoro.get('api_key', '')
                user_key = user_key or etoro.get('user_key', '')
                mode = mode or str(etoro.get('mode', '')).lower().strip()
            except Exception:
                pass
    if not api_key or not user_key:
        raise RuntimeError('eToro credentials missing')
    return api_key, user_key, base_url, mode

def _etoro_connect():
    api_key, user_key, base_url, mode = _etoro_creds()
    session = requests.Session()
    session.headers.update({
        'x-request-id': str(__import__('uuid').uuid4()),
        'x-api-key': api_key,
        'x-user-key': user_key,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })
    return session, base_url, mode

def etoro_transaction_type(side: str) -> str:
    side = (side or '').upper()
    if side == 'SELL':
        return BROKER.get('ETORO', {}).get('short_transaction', 'SHORT')
    return BROKER.get('ETORO', {}).get('long_transaction', 'LONG')

def etoro_fill(symbol, side, qty, sl, tp, last):
    _order_safe_sltp(symbol, side, qty, sl, tp, last)
    session, base_url, mode = _etoro_connect()
    symbol_norm = symbol.upper()
    tx_type = etoro_transaction_type(side)
    payload = {
        'action': 'open',
        'transaction': tx_type,
        'instrumentID': int(qty),
        'orderType': 'mkt',
        'leverage': 1,
        'amount': float(last),
        'orderCurrency': 'usd',
        'stopLossRate': float(sl),
        'takeProfitRate': float(tp),
    }
    try:
        r = session.post(f"{base_url}/api/v2/trading/execution/{mode}/orders", json=payload, timeout=15)
        if r.status_code in (200, 201):
            data = r.json() if hasattr(r, 'content') else {}
            order_id = data.get('orderId') if isinstance(data, dict) else None
            return True, {'broker': 'ETORO', 'status': 'OK', 'retcode': r.status_code, 'ticket': order_id, 'mode': mode, 'tx_type': tx_type}
        return False, {'broker': 'ETORO', 'status': 'FAIL', 'reason': r.text[:400], 'retcode': r.status_code, 'mode': mode, 'tx_type': tx_type}
    except Exception as e:
        return False, {'broker': 'ETORO', 'status': 'FAIL', 'reason': f'exception={e}', 'mode': mode, 'tx_type': tx_type}
    finally:
        try:
            session.close()
        except Exception:
            pass

# ---------------------------------------------------------------------------
# SCAN — unified, uses first scan broker's MT5
# ---------------------------------------------------------------------------

def scan():
    m = _mt5_connect(BROKER[SCAN_BROKERS[0]]['profile'])
    sigs=[]
    try:
        for cls,syms in UNIVERSE.items():
            # Skip classes not supported by the scan broker
            if cls == 'futures' or cls == 'asian_indices':
                if not any(cls in BROKER[b].get('classes', []) for b in SCAN_BROKERS):
                    continue
            for s in syms:
                info=m.symbol_info(s)
                if not info: continue
                r=m.copy_rates_from_pos(s, m.TIMEFRAME_D1,0,60)
                if r is None or len(r)<50: continue
                c=[x['close'] for x in r]; h=[x['high'] for x in r]; lo=[x['low'] for x in r]
                rsi_,sma50,atr=rsi_sma_atr(c,h,lo)
                last=c[-1]; dig=info.digits or 4
                side=None; reason=None
                ftmo = (OUS_MODE == 'ftmo')
                buy_rsi = _FTMO_RSI_BUY if ftmo else RSI_BUY
                sell_rsi = _FTMO_RSI_SELL if ftmo else RSI_SELL
                if rsi_ < buy_rsi and last > sma50:
                    side='BUY'; reason=f"RSI {rsi_:.1f} oversold + above SMA50"
                elif rsi_ > sell_rsi and last < sma50:
                    side='SELL'; reason=f"RSI {rsi_:.1f} overbought + below SMA50"
                if not side:
                    # SMA20 crossover trigger
                    if len(c) >= 21:
                        sma20 = sum(c[-20:])/20
                        prev_sma20 = sum(c[-21:-1])/20
                        if sma20 > sma50 and prev_sma20 <= sma50 and last > sma50:
                            side='BUY'; reason=f"SMA20 crossed above SMA50 @ {last:.{dig}f}"
                        elif sma20 < sma50 and prev_sma20 >= sma50 and last < sma50:
                            side='SELL'; reason=f"SMA20 crossed below SMA50 @ {last:.{dig}f}"
                if not side:
                    # ATR expansion breakout trigger
                    if len(c) >= 21 and len(h) >= 21 and len(lo) >= 21:
                        tr = [max(h[i]-lo[i], abs(h[i]-c[i-1]), abs(lo[i]-c[i-1])) for i in range(-20, 0)]
                        current_atr = sum(tr) / len(tr)
                        bb_upper = sum(c[-20:])/20 + 2*(max(c[-20:])-min(c[-20:]))
                        bb_lower = sum(c[-20:])/20 - 2*(max(c[-20:])-min(c[-20:]))
                        if last > bb_upper and atr > current_atr * 1.2:
                            side='BUY'; reason=f"BB upper breakout + ATR expansion @ {last:.{dig}f}"
                        elif last < bb_lower and atr > current_atr * 1.2:
                            side='SELL'; reason=f"BB lower breakout + ATR expansion @ {last:.{dig}f}"
                if not side: continue
                sl = last-1.2*atr if side=='BUY' else last+1.2*atr
                tp = last+2.4*atr if side=='BUY' else last-2.4*atr
                sigs.append({'class':cls,'symbol':s,'side':side,'rsi':round(rsi_,1),
                             'last':round(last,dig),'sma50':round(sma50,dig),
                             'atr':round(atr,dig),'sl':round(sl,dig),'tp':round(tp,dig),
                             'reason':reason})
        return sigs
    finally:
        try: m.shutdown()
        except Exception: pass

# ---------------------------------------------------------------------------
# ROUTE / FILL
# ---------------------------------------------------------------------------

def broker_equity(broker_name):
    b = BROKER[broker_name]
    try:
        if b['type'] == 'mt5':
            m = _mt5_connect(b['profile'])
            eq = m.account_info().equity if m.account_info() else 0
            m.shutdown()
            return float(eq or 0)
        if broker_name == 'IBKR':
            ib = _ibkr_connect()
            if not ib: return 0.0
            try:
                acct = ib.managedAccounts()[0]
                sm = ib.accountSummary(acct)
                vals = {}
                for row in sm:
                    vals[row.tag] = row.value
                eq = float(vals.get('NetLiquidation', 0))
                ib.disconnect()
                return eq
            except Exception:
                try: ib.disconnect()
                except Exception: pass
                return 0.0
        if broker_name == 'ALPACA':
            return 477.0
        if broker_name == 'OANDA':
            s, acct, base = _oanda_connect()
            try:
                r = s.get(f"{base}/accounts/{acct}/summary", timeout=10)
                if r.status_code == 200:
                    return float(r.json().get('account', {}).get('balance', 0) or 0)
            except Exception:
                pass
            return 0.0
        if broker_name == 'ETORO':
            try:
                session, base_url, mode = _etoro_connect()
                r = session.get(f"{base_url}/v1/accounts/{mode}/balance", timeout=10)
                if r.status_code == 200:
                    data = r.json() if hasattr(r, 'content') else {}
                    return float(data.get('equity', data.get('balance', 0)) or 0)
            except Exception:
                pass
            return 0.0
    except Exception:
        return 0.0
    return 0.0

def existing_exposure(symbol):
    exp={}
    for broker_name in EXEC_BROKERS:
        b = BROKER[broker_name]
        try:
            if b['type'] == 'mt5':
                m = _mt5_connect(b['profile'])
                for pos in m.positions_get():
                    if pos.symbol == symbol:
                        exp[broker_name] = exp.get(broker_name,0) + pos.volume
                m.shutdown()
            elif broker_name == 'IBKR':
                ib = _ibkr_connect(client_id=hash(symbol)%900+9001)
                if not ib: continue
                for p in ib.positions():
                    if getattr(p.contract,'symbol',None) == symbol:
                        exp[broker_name] = exp.get(broker_name,0) + float(p.position)
                ib.disconnect()
            elif broker_name == 'ALPACA':
                k,s = _alpaca_creds()
                r=requests.get(f"{b['base']}/positions", auth=(k,s), timeout=10)
                for p in r.json():
                    if p.get('symbol') == symbol:
                        exp[broker_name] = exp.get(broker_name,0) + float(p.get('qty',0))
            elif broker_name == 'OANDA':
                s, acct, base = _oanda_connect()
                r = s.get(f"{base}/accounts/{acct}/openPositions", timeout=10)
                if r.status_code == 200:
                    sym_norm = symbol.replace('/','_').upper()
                    for p in r.json().get('positions', []):
                        if p.get('instrument') == sym_norm:
                            exp[broker_name] = exp.get(broker_name,0) + float(p.get('long',{}).get('units') or p.get('short',{}).get('units') or 0)
            elif broker_name == 'ETORO':
                session, base_url, mode = _etoro_connect()
                r = session.get(f"{base_url}/v1/positions/{mode}", timeout=10)
                if r.status_code == 200:
                    sym_norm = symbol.upper()
                    for p in r.json().get('positions', []) if isinstance(r.json(), list) else []:
                        if str(p.get('symbol', '')).upper() == sym_norm:
                            exp[broker_name] = exp.get(broker_name,0) + float(p.get('units', p.get('quantity', 0)) or 0)
        except Exception:
            pass
    return exp

def _order_safe_sltp(symbol, side, qty, sl, tp, last):
    if sl is None or tp is None or not isinstance(sl, (int, float)) or not isinstance(tp, (int, float)):
        raise ValueError(f'Bad SL/TP for {symbol} {side}: sl={sl} tp={tp}')
    if float(sl) <= 0 or float(tp) <= 0:
        raise ValueError(f'Non-positive SL/TP for {symbol} {side}: sl={sl} tp={tp}')
    if abs(float(last) - float(sl)) <= 0:
        raise ValueError(f'Zero SL distance for {symbol} {side}: last={last} sl={sl} tp={tp}')

def _mt5_fill_strict(profile, symbol, side, qty, sl, tp, last):
    _order_safe_sltp(symbol, side, qty, sl, tp, last)
    m = _mt5_connect(profile)
    tag = profile.upper()
    try:
        tick = m.symbol_info_tick(symbol)
        if not tick:
            return False, {'broker': tag, 'status': 'FAIL', 'reason': 'no_symbol_info'}
        price = tick.ask if side=='BUY' else tick.bid
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': float(qty),
            'type': mt5.ORDER_TYPE_BUY if side=='BUY' else mt5.ORDER_TYPE_SELL,
            'price': price,
            'sl': float(sl),
            'tp': float(tp),
            'deviation': 10,
            'magic': 20260721,
            'comment': 'OUS-router',
            'type_time': mt5.ORDER_TIME_GTC,
        }
        res = m.order_send(req)
        rc = getattr(res, 'retcode', None)
        comment = getattr(res, 'comment', '')
        ticket = getattr(res, 'order', None)
        deal = getattr(res, 'deal', None)
        if ticket and rc in (10009, 10008):
            return True, {'broker': tag, 'status': 'OK', 'retcode': rc, 'ticket': ticket, 'deal': deal}
        return False, {'broker': tag, 'status': 'FAIL', 'reason': f'retcode={rc} {comment}', 'retcode': rc}
    except Exception as e:
        return False, {'broker': tag, 'status': 'FAIL', 'reason': f'exception={e}'}
    finally:
        try: m.shutdown()
        except Exception: pass

def alpaca_fill_strict(symbol, side, qty, sl, tp, last):
    _order_safe_sltp(symbol, side, qty, sl, tp, last)
    b = BROKER['ALPACA']
    k,s = _alpaca_creds()
    headers = {'Apca-Api-Key-Id': k, 'Apca-Api-Secret-Key': s}
    url = b['base'].rstrip('/') + '/orders'
    payload = {
        'symbol': symbol,
        'qty': str(qty),
        'side': 'buy' if side=='BUY' else 'sell',
        'type': 'market',
        'time_in_force': 'day',
        'extended_hours': False,
    }
    is_fractional = float(qty) != int(float(qty))
    if sl is not None and tp is not None and not is_fractional:
        payload['order_class'] = 'bracket'
        payload['stop_loss'] = {'stop_price': str(sl)}
        payload['take_profit'] = {'limit_price': str(tp)}
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    if r.status_code in (200, 201):
        data = r.json() if hasattr(r, 'content') else {}
        oid = data.get('id') if isinstance(data, dict) else None
        return True, {'broker': 'ALPACA', 'status': 'OK', 'retcode': r.status_code, 'ticket': oid}
    if is_fractional:
        r2 = requests.post(url, headers=headers, json=payload, timeout=10)
        if r2.status_code in (200, 201):
            data2 = r2.json() if hasattr(r2, 'content') else {}
            oid2 = data2.get('id') if isinstance(data2, dict) else None
            child = []
            if sl:
                child.append(requests.post(url, headers=headers, json={
                    'symbol': symbol, 'qty': str(qty), 'side': 'sell' if side=='BUY' else 'buy',
                    'type': 'stop', 'time_in_force': 'day', 'stop_price': str(sl),
                }, timeout=10))
            if tp:
                child.append(requests.post(url, headers=headers, json={
                    'symbol': symbol, 'qty': str(qty), 'side': 'sell' if side=='BUY' else 'buy',
                    'type': 'limit', 'time_in_force': 'day', 'limit_price': str(tp),
                }, timeout=10))
            return True, {'broker': 'ALPACA', 'status': 'OK_FRAC_REARM', 'retcode': r2.status_code, 'ticket': oid2, 'child': [x.status_code for x in child]}
    return False, {'broker': 'ALPACA', 'status': 'FAIL', 'reason': r.text[:300], 'retcode': r.status_code}

def alpaca_fill(symbol, side, qty, sl, tp, last):
    ok, result = alpaca_fill_strict(symbol, side, qty, sl, tp, last)
    return ok, result

def ibkr_fill(symbol, side, qty, sl, tp, last):
    _order_safe_sltp(symbol, side, qty, sl, tp, last)
    b = BROKER['IBKR']
    ib = _ibkr_connect(client_id=hash(symbol)%900+9001)
    if not ib: return False, {'broker': 'IBKR', 'status': 'FAIL', 'reason': 'no_connection'}
    try:
        if symbol in ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF','NZDUSD','USDCAD']:
            c=Forex(symbol)
        elif symbol in ['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD']:
            c=Crypto(symbol[:3],'PAXOS','USD')
        elif symbol in ['US30','US500','US100','DE40','UK100']:
            c=CFD(symbol,'SMART','USD')
        elif symbol in ['XAUUSD','XAGUSD','XPTUSD','XPDUSD']:
            c=CFD(symbol,'SMART','USD')
        else:
            c=Forex(symbol)
        ib.qualifyContracts(c)
        order = MarketOrder('BUY' if side=='BUY' else 'SELL', qty)
        order.transmit = True
        trade = ib.placeOrder(c, order)
        time.sleep(2)
        filled = getattr(trade.orderStatus, 'filled', 0) or 0
        if filled > 0:
            return True, {'broker': 'IBKR', 'status': 'OK', 'retcode': None, 'ticket': getattr(trade, 'orderId', None)}
        ords = ib.bracketOrder(action='BUY' if side=='BUY' else 'SELL', quantity=qty,
                                limitPrice=last, stopPrice=sl, takeProfitPrice=tp,
                                transmit=True)
        for o in ords:
            ib.placeOrder(c, o)
        time.sleep(2)
        return True, {'broker': 'IBKR', 'status': 'OK_BRACKET', 'retcode': None}
    except Exception as e:
        return False, {'broker': 'IBKR', 'status': 'FAIL', 'reason': f'exception={e}', 'retcode': None}
    finally:
        try: ib.disconnect()
        except Exception: pass

def oanda_fill(symbol, side, qty, sl, tp, last):
    _order_safe_sltp(symbol, side, qty, sl, tp, last)
    s, acct, base = _oanda_connect()
    instrument = symbol.replace('/','_').upper()
    units = str(int(qty)) if side == 'BUY' else str(-int(qty))
    payload = {
        'order': {
            'units': units,
            'instrument': instrument,
            'timeInForce': 'GTC',
            'type': 'MARKET',
            'positionFill': 'DEFAULT',
        }
    }
    if sl is not None and tp is not None:
        payload['order']['stopLossOnFill'] = {'timeInForce': 'GTC', 'price': f'{float(sl):.5f}'}
        payload['order']['takeProfitOnFill'] = {'timeInForce': 'GTC', 'price': f'{float(tp):.5f}'}
    r = s.post(f"{base}/accounts/{acct}/orders", json=payload, timeout=10)
    if r.status_code in (200, 201):
        data = r.json() if hasattr(r, 'content') else {}
        order_id = data.get('orderCreateTransaction', {}).get('id') if isinstance(data, dict) else None
        return True, {'broker': 'OANDA', 'status': 'OK', 'retcode': r.status_code, 'ticket': order_id}
    return False, {'broker': 'OANDA', 'status': 'FAIL', 'reason': r.text[:300], 'retcode': r.status_code}

# ---------------------------------------------------------------------------
# PLAN / EXECUTE
# ---------------------------------------------------------------------------

def plan_fill(sig):
    planned=[]
    cls = sig['class']
    last = sig['last']; side = sig['side']; sl=sig['sl']; tp=sig['tp']
    brokers = _broker_for_class(cls)
    if not brokers:
        return planned

    # CHALLENGE LOSS RULES — guard before any order is placed
    symbol = sig['symbol']
    # skip if SL non-positive / ATR zero
    if sl is None or tp is None or abs(last - sl) <= 0:
        print(f"SKIP {symbol} {side}: bad SL/TP")
        return planned

    exp = existing_exposure(symbol) if DCA_MODE else {}
    has_opposite = False
    for broker_name, vol in exp.items():
        m = mt5_connect(BROKER[broker_name]['profile'])
        try:
            for pos in m.positions_get() or []:
                if pos.symbol == symbol:
                    pos_side = 'buy' if pos.type == 0 else 'sell'
                    if pos_side != side.lower():
                        has_opposite = True
                        break
        except Exception:
            pass
        try:
            m.shutdown()
        except Exception:
            pass
        if has_opposite:
            break
    if has_opposite:
        print(f"SKIP {symbol} {side}: opposite position already open")
        return planned

    total_risk = sum(abs(v) for v in exp.values()) * RISK_PCT
    remaining = max(0.0, DCA_CAP_PCT - total_risk)
    for broker_name in brokers:
        eq = broker_equity(broker_name)
        if eq <= 0:
            planned.append({'broker':broker_name,'action':'SKIP','why':'no equity / unreachable'})
            continue

        base_risk = RISK_PCT
        if DCA_MODE and broker_name in [k for k,v in exp.items()]:
            base_risk = min(remaining, RISK_PCT)
            remaining -= base_risk

        notional = eq * base_risk
        if notional <= 0:
            planned.append({'broker':broker_name,'action':'SKIP','why':'notional<=0'})
            continue

        # Determine qty / volume per broker
        if BROKER[broker_name]['type'] == 'mt5':
            profile = BROKER[broker_name]['profile']
            m = mt5_connect(profile)
            try:
                info=m.symbol_info(symbol)
                tick=m.symbol_info_tick(symbol)
                if not info or not tick:
                    planned.append({'broker':broker_name,'action':'SKIP','why':'no symbol info'})
                    m.shutdown(); continue
                price = tick.ask if side=='BUY' else tick.bid
                sl_dist = abs(price - sl)
                if sl_dist <= 0:
                    planned.append({'broker':broker_name,'action':'SKIP','why':'zero SL distance'})
                    m.shutdown(); continue
                risk_per_pt = info.trade_tick_value / info.trade_tick_size if info.trade_tick_size else 0
                if risk_per_pt <= 0:
                    planned.append({'broker':broker_name,'action':'SKIP','why':'bad contract specs'})
                    m.shutdown(); continue
                vol = notional / (sl_dist / info.point * risk_per_pt)
                vol = max(info.volume_min, min(info.volume_max, round(vol, 2 if info.volume_step >= 0.01 else 1)))
                if (vol / info.volume_max) > 0.5:
                    planned.append({'broker':broker_name,'action':'SKIP','why':f'oversized {vol}/{info.volume_max}'})
                    m.shutdown(); continue
                qty = vol
            finally:
                m.shutdown()
        elif broker_name == 'ALPACA':
            qty = round(notional / last, 4)
            if qty < 0.001:
                planned.append({'broker':broker_name,'action':'SKIP','why':'qty below Alpaca minimum'})
                continue
        elif broker_name == 'IBKR':
            qty = max(1, int(notional / last))
        elif broker_name == 'OANDA':
            qty = max(1, int(notional / last))
        elif broker_name == 'ETORO':
            qty = round(notional / last, 4)
        else:
            qty = 0

        planned.append({'broker':broker_name,'action':'PLACE' if not DRY_RUN else 'DRYRUN',
                        'notional':round(notional,2),'qty':qty,
                        'entry':last,'sl':sl,'tp':tp,'risk_pct':base_risk,'equity':round(eq,2)})
        if not DRY_RUN:
            result = None
            if broker_name in ('FTMO','CAPITAL'):
                ok, result = _mt5_fill_strict(BROKER[broker_name]['profile'], symbol, side, qty, sl, tp, last)
            elif broker_name == 'ETORO':
                ok, result = etoro_fill(symbol, side, qty, sl, tp, last)
            elif broker_name == 'ALPACA':
                ok, result = alpaca_fill(symbol, side, qty, sl, tp, last)
            elif broker_name == 'IBKR':
                ok, result = ibkr_fill(symbol, side, qty, sl, tp, last)
            elif broker_name == 'OANDA':
                ok, result = oanda_fill(symbol, side, qty, sl, tp, last)
            else:
                ok = False
                result = None
            status = result.get('status') if isinstance(result, dict) else ('OK' if ok else 'FAIL')
            planned[-1]['result'] = status
            if isinstance(result, dict):
                for k in ('ticket','deal','retcode','reason'):
                    if result.get(k) is not None:
                        planned[-1][k] = result.get(k)
    return planned

# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------

def rsi_sma_atr(closes, highs, lows):
    n=len(closes)
    g=[max(closes[i]-closes[i-1],0) for i in range(1,n)]
    l=[max(closes[i-1]-closes[i],0) for i in range(1,n)]
    ag=sum(g[:14])/14; al=sum(l[:14])/14
    rsi=100-(100/(1+(ag/al if al>0 else 999)))
    for i in range(15,n):
        ag=(ag*13+g[i-1])/14; al=(al*13+l[i-1])/14
        rsi=100-(100/(1+(ag/al if al>0 else 999)))
    sma50=sum(closes[-50:])/50
    tr=[max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,n)]
    atr=sum(tr[-14:])/14
    return rsi, sma50, atr

# ---------------------------------------------------------------------------
# MULTI-TECHNIQUE SCANNER
# ---------------------------------------------------------------------------

def multi_technique_scan():
    m = _mt5_connect(BROKER[SCAN_BROKERS[0]]['profile'])
    sigs=[]
    try:
        for cls,syms in UNIVERSE.items():
            for s in syms:
                info=m.symbol_info(s)
                if not info: continue
                r=m.copy_rates_from_pos(s, m.TIMEFRAME_D1,0,60)
                if r is None or len(r)<50: continue
                c=[x['close'] for x in r]; h=[x['high'] for x in r]; lo=[x['low'] for x in r]
                vol=[x['real_volume'] for x in r]
                last=c[-1]
                for strategy in ['BB_BREAKOUT_UP','BB_BREAKOUT_DOWN','SMA_CROSS_UP','SMA_CROSS_DOWN','ATR_EXPANSION']:
                    side=None
                    if strategy=='BB_BREAKOUT_UP':
                        upper=sum(c[-20:])/20 + 2*(max(c[-20:])-min(c[-20:]))
                        if last > upper: side='BUY'; reason='break above upper BB'
                    elif strategy=='BB_BREAKOUT_DOWN':
                        lower=sum(c[-20:])/20 - 2*(max(c[-20:])-min(c[-20:]))
                        if last < lower: side='SELL'; reason='break below lower BB'
                    elif strategy=='SMA_CROSS_UP':
                        sma20=sum(c[-20:])/20; sma50=sum(c[-50:])/50
                        if sma20 > sma50 and c[-2] < sum(c[-21:-1])/20: side='BUY'; reason='SMA20 crossed above SMA50'
                    elif strategy=='SMA_CROSS_DOWN':
                        sma20=sum(c[-20:])/20; sma50=sum(c[-50:])/50
                        if sma20 < sma50 and c[-2] > sum(c[-21:-1])/20: side='SELL'; reason='SMA20 crossed below SMA50'
                    if not side: continue
                    _,_,atr_val=rsi_sma_atr(c,h,lo)
                    sl = last - 1.2*atr_val if side=='BUY' else last + 1.2*atr_val
                    tp = last + 2.4*atr_val if side=='BUY' else last - 2.4*atr_val
                    dig=info.digits or 4
                    sigs.append({'class':cls,'symbol':s,'side':side,'last':round(last,dig),
                                 'atr':round(atr_val,dig),'sl':round(sl,dig),'tp':round(tp,dig),
                                 'reason':reason,'strategy':strategy})
        import json
        os.makedirs(OUT, exist_ok=True)
        with open(f'{OUT}/multi_technique_signals.json','w') as f:
            json.dump(sigs, f, indent=2)
        return sigs
    finally:
        try: m.shutdown()
        except Exception: pass

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print('='*90)
    print(f'OUS TRADE ROUTER v2 | MODE={OUS_MODE} | DRY_RUN={DRY_RUN}')
    print(f'SCAN={SCAN_BROKERS} EXEC={EXEC_BROKERS}')
    print('='*90)

    sigs = scan()
    print(f'\nScan -> {len(sigs)} signals')
    if not sigs:
        print('standing down')
        return
    planned_all=[]
    seen=set()
    for s in sigs:
        existing=[]
        for b in EXEC_BROKERS:
            if s['symbol'] in [p.symbol for p in get_positions(b)]:
                existing.append(b)
        if existing:
            print(f"skip {s['symbol']} {s['side']} already open on {existing}")
            continue
        # Global dedupe across this run
        dedupe_key=(s['symbol'], s['side'])
        if dedupe_key in seen:
            print(f"skip duplicate {s['symbol']} {s['side']}")
            continue
        seen.add(dedupe_key)
        plan = plan_fill(s)
        planned_all.extend(plan)
        for item in plan:
            print(f"{item.get('action')} {s['symbol']} {s['side']} via {item.get('broker')} qty={item.get('qty')} result={item.get('result','')}")
    print('\nSUMMARY')
    for item in planned_all:
        print(item)
    _write_copy_trade_queue(sigs, planned_all)

def get_positions(broker_name):
    b = BROKER[broker_name]
    try:
        if b['type'] == 'mt5':
            m = mt5_connect(b['profile'])
            out = list(m.positions_get() or [])
            m.shutdown()
            return out
        return []
    except Exception:
        return []

# ---------------------------------------------------------------------------
# COPY TRADE QUEUE
# ---------------------------------------------------------------------------
import json as _json

COPY_QUEUE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ous_copy_queue.json')

def _load_copy_queue():
    try:
        with open(COPY_QUEUE_PATH) as f:
            return _json.load(f)
    except Exception:
        return []

def _save_copy_queue(q):
    tmp = COPY_QUEUE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        _json.dump(q, f, indent=1, default=str)
    os.replace(tmp, COPY_QUEUE_PATH)

def _write_copy_trade_queue(sigs, planned_all):
    """Persist signals + execution plans so --replay-copy can fan out to other brokers."""
    q = _load_copy_queue()
    existing_keys = {(x.get('symbol'), x.get('side'), x.get('origin_ticket')) for x in q}
    for s in sigs:
        key = (s['symbol'], s['side'], s.get('ticket'))
        if key in existing_keys:
            continue
        plans = [p for p in planned_all if p.get('symbol') == s['symbol'] and p.get('side') == s['side']]
        if not plans:
            continue
        q.append({
            'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status': 'pending',
            'symbol': s['symbol'],
            'side': s['side'],
            'qty': s.get('qty'),
            'sl': s.get('sl'),
            'tp': s.get('tp'),
            'last': s.get('last'),
            'copy_broker': plans[0].get('broker'),
            'origin_ticket': s.get('ticket'),
            'plans': plans,
        })
    _save_copy_queue(q)
    print(f'[COPY] queue written: {len(q)} items -> {COPY_QUEUE_PATH}')


def replay_copy_queue(limit=None):
    q=_load_copy_queue()
    pending=[x for x in q if x.get('status')=='pending']
    if not pending:
        print('[COPY] no pending copies')
        return
    if limit: pending=pending[:int(limit)]
    print(f'[COPY] processing {len(pending)} copies')
    for item in pending:
        b=item.get('copy_broker'); symbol=item.get('symbol'); side=item.get('side')
        qty=item.get('qty'); sl=item.get('sl'); tp=item.get('tp'); last=item.get('last')
        try:
            if b in ('FTMO','CAPITAL'):
                ok,result=_mt5_fill_strict(BROKER[b]['profile'],symbol,side,qty,sl,tp,last)
            elif b=='ALPACA':
                ok,result=alpaca_fill_strict(symbol,side,qty,sl,tp,last)
            elif b=='IBKR':
                ok,result=ibkr_fill(symbol,side,qty,sl,tp,last)
            else:
                ok=False; result={'status':'FAIL','reason':'unknown broker'}
            status=result.get('status') if isinstance(result,dict) else ('OK' if ok else 'FAIL')
            print(f"[COPY] {symbol} {side} -> {b}: {status} reason={result.get('reason') if isinstance(result,dict) else ''}")
            item['status']=status
            if isinstance(result,dict):
                item['copy_retcode']=result.get('retcode')
                item['copy_ticket']=result.get('ticket') or item.get('origin_ticket')
        except Exception as e:
            item['status']=f'ERROR:{e}'
            print(f'[COPY] {symbol} {side} -> {b}: ERROR={e}')
    _save_copy_queue(q)
    print('[COPY] queue saved.')

def _run_copy_queue_from_args():
    import sys
    if '--replay-copy' in sys.argv:
        lim=None
        for i,a in enumerate(sys.argv):
            if a=='--replay-limit' and i+1<len(sys.argv):
                lim=int(sys.argv[i+1])
        replay_copy_queue(limit=lim)
    elif '--clear-copy' in sys.argv:
        _save_copy_queue([])
        print('[COPY] cleared')
    else:
        main()

if __name__=='__main__':
    _run_copy_queue_from_args()

