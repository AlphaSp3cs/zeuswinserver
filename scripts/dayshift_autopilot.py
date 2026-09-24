#!/usr/bin/env python3
"""
Dayshift Autopilot — full auto dayshift mode for eToro demo and IBKR paper,
with FTMO LEFT and Capital RIGHT as secondary execution venues if trades allow
and capital is available.

Runs during dayshift window: 08:30 -> 16:00 ET Mon-Fri.
Windows Task Scheduler should call this every N minutes during dayshift.
"""
import json, os, sys, time, math, datetime
from pathlib import Path

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except Exception:
    HAS_WINOTIFY = False
    import os as _os_dg
    if _os_dg.environ.get('OURO_DISABLE_TOAST','').strip().lower() in ('1','true','yes'):
        HAS_WINOTIFY = False  # bravo: toasts OFF, Telegram-only

import requests
import numpy as np
import yfinance as yf
from ib_insync import IB, Contract, Order
from etoro_auth import EtoroAuth

import MetaTrader5 as mt5

# ── Config ──────────────────────────────────────────────────────────────────
BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
BASE_DESKTOP = Path(r'C:\Users\bravo-usr1\Desktop')
STATE_FILE = BASE_FIRM / 'workflow' / 'dayshift_state.json'
LOG_FILE = BASE_FIRM / 'workflow' / 'dayshift_log.jsonl'
OUT_DIR = BASE_FIRM / 'workflow'

CYCLE_SEC = 900          # 15 min between cycles
MAX_OPEN = 4             # max concurrent open positions
MAX_HOLD_SEC = 28800     # 8 hours max hold per daytrade
RISK_PCT = 0.01          # 1% per trade
DEVIATION = 20
MAGIC = 20260812

# Dayshift window in ET: 08:30 -> 16:00 Mon-Fri
# Script enforces hard cutoff regardless of who/what called it.
CUTOFF_ET_HOUR = 16
CUTOFF_ET_MIN = 0
START_ET_HOUR = 8
START_ET_MIN = 30

sys.path.insert(0, str(BASE_FIRM / 'scripts'))
from mt5_connect import connect as mt5_connect, KNOWN_BROKERS

# Dayshift broker priority: eToro demo first, then IBKR paper, then FTMO LEFT, then Capital RIGHT
BROKER_WATERFALL = ['etoro', 'ibkr', 'ftmo', 'capital']

# Dayshift asset class: equities, indices, forex, crypto, metals
DAYSHIFT_UNIVERSE = {
    'indices': ['US30','US500','US100','JP225','UK100','HK50','EU50','AU200','DE40','ES35','FR40','IT40','SG30'],
    'crypto': [
        'BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD','XMRUSD','ZECUSD','UNIUSD',
        'BCHUSD','EOSUSD','FILUSD','NEARUSD','ATOMUSD','ALGOUSD','VETUSD','THETAUSD','FTMUSD','SANDUSD','MANAUSD',
        'AXSUSD','IMXUSD','ARBUSD','OPUSD','MATICUSD','INJUSD','SUIUSD','SEIUSD','TIAUSD','APTUSD','MOVEUSD',
        'BLURUSD','PEPEUSD','WIFUSD','DOGEUSD','SHIBUSD','FLOKIUSD','FETUSD','RENDERUSD','GRTUSD','OCEANUSD',
        'AGIXUSD','LDOUSD','RPLUSD','SSVUSD','ENSUSD','BLZUSD','KAVAUSD','CRVUSD','SNXUSD','1INCHUSD',
        'USDTUSD','USDCUSD','DAIUSD'
    ],
    'forex': [
        'EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF','NZDUSD','USDCAD',
        'EURJPY','EURGBP','GBPJPY','AUDJPY','AUDNZD','AUDCAD','CADJPY','CHFJPY','NZDJPY',
        'EURCHF','EURCAD','EURAUD','GBPCHF','GBPAUD','GBPCAD','GBPNZD','NZDCHF','NZDCAD',
        'USDTRY','USDZAR','USDMXN','USDCNH','USDSGD','USDHKD','USDTHB','USDSEK','USDNOK','USDDKK','USDPLN'
    ],
    'commodities': [
        'XAUUSD','XAGUSD','XPTUSD','XPDUSD',
        'WTIOIL','BRENT','NGAS',
        'COPPER','LITHIUM','URANIUM'
    ],
}

# News keywords
BULLISH_KW = ['surge','rally','breakout','adoption','approval','bullish','upgrade','inflow','ETF']
BEARISH_KW = ['crash','ban','hack','bearish','downgrade','outflow','regulation','sell-off','collapse']

# ── Helpers ──────────────────────────────────────────────────────────────────
def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

def et_now():
    return now_utc().astimezone(datetime.timezone(datetime.timedelta(hours=-4)))

def toast(title, msg, urgency='INFO'):
    if not HAS_WINOTIFY:
        return
    try:
        n = Notification(app_id="Zeus Dayshift", title=title, msg=msg)
        if urgency == 'HIGH':
            n.set_audio(audio.Default, loop=False)
        n.show()
    except Exception:
        pass

def log_json(obj):
    obj['ts'] = now_utc().isoformat()
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')

def load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault('cycles', 0)
    data.setdefault('open', [])
    data.setdefault('last_run', None)
    data.setdefault('broker_state', {})
    return data

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')

def news_sentiment(symbol, asset_class):
    try:
        query = f"{symbol} {asset_class} market news today"
        url = f"https://lite.duckduckgo.com/lite/?q={requests.utils.quote(query)}"
        r = requests.get(url, timeout=10, headers={'User-Agent':'Mozilla/5.0'})
        text = r.text.lower()
        score = 0
        for kw in BULLISH_KW:
            if kw in text:
                score += 1
        for kw in BEARISH_KW:
            if kw in text:
                score -= 1
        sentiment = 'NEUTRAL'
        if score >= 2:
            sentiment = 'BULLISH'
        elif score <= -2:
            sentiment = 'BEARISH'
        return sentiment, score, text[:200]
    except Exception:
        return 'NEUTRAL', 0, ''

def calc_atr(symbol, period=14):
    for profile in BROKER_WATERFALL:
        if profile in ('etoro', 'ibkr'):
            continue  # ATR from MT5 brokers only
        m = mt5_connect(profile)
        if not m:
            continue
        try:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, max(period + 1, 100))
            if rates is None or len(rates) < period + 1:
                m.shutdown()
                continue
            highs = np.array([r['high'] for r in rates])
            lows = np.array([r['low'] for r in rates])
            closes = np.array([r['close'] for r in rates])
            tr1 = highs[1:] - lows[1:]
            tr2 = np.abs(highs[1:] - closes[:-1])
            tr3 = np.abs(lows[1:] - closes[:-1])
            tr = np.maximum(tr1, np.maximum(tr2, tr3))
            val = float(np.mean(tr[-period:]))
            m.shutdown()
            return val
        except Exception:
            try:
                m.shutdown()
            except Exception:
                pass
    return None

def rsi_from_rates(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gs, ls = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gs.append(max(d, 0.0))
        ls.append(max(-d, 0.0))
    ag = sum(gs[:period]) / period
    al = sum(ls[:period]) / period
    for i in range(period, len(gs)):
        ag = (ag * (period - 1) + gs[i]) / period
        al = (al * (period - 1) + ls[i]) / period
    if al <= 0:
        return 100.0 if ag > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + ag / al)

def scan_symbol(symbol, asset_class):
    for profile in BROKER_WATERFALL:
        if profile in ('etoro', 'ibkr'):
            continue
        m = mt5_connect(profile)
        if not m:
            continue
        try:
            info = m.symbol_info(symbol)
            if not info or not getattr(info, 'visible', False):
                m.shutdown()
                continue
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
            m.shutdown()
            if rates is None or len(rates) < 50:
                continue
            closes = np.array([r['close'] for r in rates])
            highs = np.array([r['high'] for r in rates])
            lows = np.array([r['low'] for r in rates])
            r = rsi_from_rates(closes, 14)
            sma20 = float(np.mean(closes[-20:]))
            sma50 = float(np.mean(closes[-50:]))
            atr = calc_atr(symbol) or (float(np.mean(highs[-14:] - lows[-14:])) * 0.8)
            last = float(closes[-1])
            tick = m.symbol_info_tick(symbol)
            bid = float(tick.bid) if tick else last
            ask = float(tick.ask) if tick else last
            return {
                'symbol': symbol, 'asset_class': asset_class,
                'price': last, 'bid': bid, 'ask': ask,
                'rsi': round(r, 1), 'sma20': round(sma20, 5),
                'sma50': round(sma50, 5), 'atr': round(atr, 5),
            }
        except Exception:
            try:
                m.shutdown()
            except Exception:
                pass
    return None

def broker_executable(profile):
    if profile == 'etoro':
        try:
            auth = EtoroAuth()
            auth.load_secure_file(BASE_FIRM / '.broker_creds_secure.json')
            auth.load_env()
            auth.validate()
            return True, f"eToro demo OK username={auth.state.get('me_response', {}).get('username', '?')}"
        except Exception as e:
            return False, f'eToro auth failed: {e}'
    if profile == 'ibkr':
        try:
            ib = IB()
            ib.connect('127.0.0.1', 4002, clientId=2002, timeout=10)
            if ib.isConnected():
                ib.disconnect()
                return True, 'IBKR paper connected'
            return False, 'IBKR not connected'
        except Exception as e:
            return False, f'IBKR error: {e}'
    # MT5 brokers
    try:
        m = mt5_connect(profile)
        if not m:
            return False, 'no_connection'
        info = m.account_info()
        m.shutdown()
        if not info:
            return False, 'no_account_info'
        # Check if trading is allowed and account has capital
        trade_allowed = bool(info.trade_allowed)
        equity = float(getattr(info, 'equity', 0) or 0)
        capital_ok = equity > 0
        return trade_allowed and capital_ok, f"trade_allowed={trade_allowed}, equity={equity:.2f}"
    except Exception as e:
        return False, f'exception={e}'

def size_by_risk(entry, sl, equity):
    if abs(entry - sl) <= 0:
        return None
    risk_usd = equity * RISK_PCT
    return risk_usd

def send_ticket(profile, symbol, side, qty, entry, sl, tp):
    if profile == 'etoro':
        return send_ticket_etoro(symbol, side, qty, entry, sl, tp)
    if profile == 'ibkr':
        return send_ticket_ibkr(symbol, side, qty, entry, sl, tp)
    return send_ticket_mt5(profile, symbol, side, qty, entry, sl, tp)

def send_ticket_mt5(profile, symbol, side, qty, entry, sl, tp):
    m = mt5_connect(profile)
    if not m:
        return None, 'no_mt5_connection'
    try:
        m.symbol_select(symbol, True)
        info = m.symbol_info(symbol)
        tick = m.symbol_info_tick(symbol)
        if not info or not tick:
            m.shutdown()
            return None, 'no_symbol_info'
        digits = info.digits or 5
        entry = round(entry, digits)
        sl = round(sl, digits)
        tp = round(tp, digits)
        qty = max(info.volume_min, min(info.volume_max, qty))
        qty = round(qty, 2 if info.volume_step and info.volume_step >= 0.01 else 1)
        price = tick.ask if side == 'BUY' else tick.bid
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': float(qty),
            'type': mt5.ORDER_TYPE_BUY if side == 'BUY' else mt5.ORDER_TYPE_SELL,
            'price': float(price),
            'sl': float(sl),
            'tp': float(tp),
            'deviation': DEVIATION,
            'magic': MAGIC,
            'comment': 'DAYSHIFT',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }
        res = m.order_send(req)
        m.shutdown()
        rc = getattr(res, 'retcode', None)
        comment = getattr(res, 'comment', '')
        ticket = getattr(res, 'order', None)
        deal = getattr(res, 'deal', None)
        if rc in (10009, 10008, 10004):
            return {'retcode': rc, 'ticket': ticket, 'deal': deal, 'price': float(price)}, None
        return None, f'retcode={rc} {comment}'
    except Exception as e:
        try:
            m.shutdown()
        except Exception:
            pass
        return None, f'exception={e}'

def send_ticket_etoro(symbol, side, qty, entry, sl, tp):
    try:
        auth = EtoroAuth()
        auth.load_secure_file(BASE_FIRM / '.broker_creds_secure.json')
        auth.load_env()
        auth.validate()
        api_key = auth.api_key
        user_key = auth.user_key
        mode = auth.mode
    except Exception as e:
        return None, f'etoro auth failed: {e}'

    instr_id = ETORO_INSTRUMENT_MAP.get(symbol.upper())
    if not instr_id:
        return None, f'unknown eToro instrument for {symbol}'

    tx = 'buy' if side.upper() == 'BUY' else 'sellshort'
    payload = {
        'action': 'open',
        'transaction': tx,
        'instrumentID': instr_id,
        'orderType': 'mkt',
        'leverage': 1,
        'amount': float(qty),
        'orderCurrency': 'usd',
        'stopLossRate': float(sl),
        'takeProfitRate': float(tp),
    }
    url = f'https://public-api.etoro.com/api/v2/trading/execution/{mode}/orders'
    headers = {
        'x-request-id': str(__import__('uuid').uuid4()),
        'x-api-key': api_key,
        'x-user-key': user_key,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return {
                'retcode': r.status_code,
                'ticket': data.get('orderId'),
                'deal': data.get('referenceId'),
                'price': float(entry),
            }, None
        return None, f'HTTP {r.status_code}: {r.text[:200]}'
    except Exception as e:
        return None, f'etoro exception: {e}'

def send_ticket_ibkr(symbol, side, qty, entry, sl, tp):
    ib = IB()
    try:
        ib.connect('127.0.0.1', 4002, clientId=2002, timeout=10)
        if not ib.isConnected():
            return None, 'IBKR not connected on 4002'

        if symbol.upper() in ('XAGUSD', 'XAUUSD'):
            c = Contract(symbol=symbol.upper().replace('USD', ''), secType='CFD', exchange='SMART', currency='USD')
        elif len(symbol) == 6:
            base = symbol[:3].upper()
            quote = symbol[3:6].upper()
            c = Contract(symbol=base, secType='CASH', exchange='IDEALPRO', currency=quote)
        else:
            return None, f'Unsupported IBKR symbol mapping: {symbol}'

        qualified = ib.qualifyContracts(c)
        if not qualified:
            return None, 'IBKR contract qualification failed'
        c = qualified[0]

        if symbol.upper() in ('XAGUSD', 'XAUUSD'):
            qty = 1

        order = Order(action=side.upper(), orderType='LMT', totalQuantity=qty, lmtPrice=entry, tif='GTC')
        trade = ib.placeOrder(c, order)
        time.sleep(0.5)
        status = trade.orderStatus.status
        if status in ('Submitted', 'Filled', 'PendingSubmit'):
            return {
                'retcode': 200,
                'ticket': trade.orderStatus.orderId,
                'deal': None,
                'price': float(entry),
            }, None
        return None, f'IBKR status={status}'
    except Exception as e:
        return None, f'IBKR error: {e}'
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

# ── eToro / IBKR / Symbol Helpers ───────────────────────────────────────────
ETORO_INSTRUMENT_MAP = {
    # Forex
    'EURUSD': 1, 'GBPUSD': 2, 'NZDUSD': 3, 'USDCAD': 4, 'USDJPY': 5,
    'AUDUSD': 7, 'GBPAUD': 50, 'NZDJPY': 55, 'GBPCHF': 51, 'EURCHF': 9,
    'USDTRY': 62, 'USDCHF': 6, 'EURJPY': 10, 'GBPJPY': 11, 'AUDJPY': 14,
    'CADJPY': 15, 'CHFJPY': 16, 'NZDCHF': 54, 'NZDCAD': 53,
    'USDSEK': 58, 'USDNOK': 57, 'USDMXN': 59, 'USDZAR': 61, 'USDPLN': 52,
    # Metals/Commodities
    'XAUUSD': 18, 'XAGUSD': 19,
    # Indices
    'US500': 28, 'SPX500': 27, 'US100': 29, 'US30': 26, 'UK100': 32, 'DE40': 25, 'AUS200': 24, 'JPN225': 23, 'FRA40': 31, 'ES35': 34, 'ITA40': 36, 'SPAIN35': 37, 'EU50': 38, 'HK50': 33, 'CHINA50': 35, 'INDIA50': 39, 'BRAZIL60': 40, 'SOX': 30,
    # Crypto - major
    'BTC': 100000, 'ETH': 100001, 'SOL': 100063, 'AVAX': 100085,
    'ADA': 100017, 'XRP': 100003, 'DOT': 100037, 'LINK': 100040,
    'UNI': 100041, 'BCH': 100002, 'FIL': 100045, 'NEAR': 100337,
    'ATOM': 100047, 'ALGO': 100046, 'VET': 100416, 'THETA': 100064,
    'SAND': 100084, 'MANA': 100048, 'AXS': 100082, 'IMX': 100016,
    'ARB': 100333, 'OP': 100335, 'INJ': 100330, 'SUI': 100340,
    'SEI': 100326, 'TIA': 100338, 'APT': 100315, 'MOVE': 100318,
    'BLUR': 100543, 'WIF': 100014, 'DOGE': 100043, 'FET': 100079,
    'RENDER': 100334, 'GRT': 100066, 'OCEAN': 100021, 'LDO': 100336,
    'RPL': 100341, 'ENS': 100089, 'BLZ': 100651, 'KAVA': 100541,
    'CRV': 100068, 'SNX': 100072, '1INCH': 100067, 'ZEC': 100028,
    'USDT': 100528, 'USDC': 100444, 'POL': 100056,
}

def normalize_etoro_symbol(raw):
    """Convert yfinance-style symbols to eToro instrument symbols."""
    sym = str(raw).upper()
    if '-' in sym and sym.endswith('USD'):
        sym = sym.replace('-USD', '')
    elif sym.endswith('USD') and len(sym) > 6:
        sym = sym[:-3]
    if sym.startswith('^'):
        sym = sym[1:]
    if sym.endswith('=F'):
        sym = sym[:-2]
    if sym.endswith('=X'):
        sym = sym[:-2]
    return sym

# ── Close / Management ───────────────────────────────────────────────────────
def close_position(profile, position):
    m = mt5_connect(profile)
    if not m:
        return False, 'no_mt5_connection'
    try:
        tick = m.symbol_info_tick(position.symbol)
        price = tick.bid if position.type == 0 else tick.ask
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': position.symbol,
            'volume': position.volume,
            'type': mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
            'position': position.ticket,
            'price': float(price),
            'deviation': DEVIATION,
            'magic': MAGIC,
            'comment': 'DAYSHIFT_CLOSE',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }
        res = m.order_send(req)
        m.shutdown()
        rc = getattr(res, 'retcode', None)
        if rc in (10009, 10008):
            return True, {'retcode': rc, 'ticket': getattr(res, 'order', None)}
        return False, f'retcode={rc} {getattr(res, "comment", "")}'
    except Exception as e:
        try:
            m.shutdown()
        except Exception:
            pass
        return False, f'exception={e}'

def close_all_expired(open_positions):
    now = now_utc()
    still_open = []
    closed = []
    for p in open_positions:
        opened = datetime.datetime.fromisoformat(p.get('opened_at', now.isoformat())).replace(tzinfo=datetime.timezone.utc)
        age = (now - opened).total_seconds()
        profile = p.get('profile')
        ticket = p.get('ticket')
        symbol = p.get('symbol')
        if age > MAX_HOLD_SEC:
            if profile in ('etoro', 'ibkr'):
                log_json({'event': 'MAX_HOLD_CLOSE_SKIP', 'ticket': ticket, 'symbol': symbol, 'profile': profile, 'reason': 'non-mt5 broker'})
                still_open.append(p)
            else:
                ok, out = close_position(profile, type('Pos', (), {'symbol': symbol, 'volume': p.get('volume', 0.01), 'type': 0 if p.get('side') == 'BUY' else 1, 'ticket': ticket})())
                closed.append({'ticket': ticket, 'symbol': symbol, 'reason': 'MAX_HOLD', 'ok': ok, 'out': out})
                log_json({'event': 'MAX_HOLD_CLOSE', 'ticket': ticket, 'symbol': symbol, 'ok': ok, 'out': out})
        else:
            still_open.append(p)
    return still_open, closed

# ── Main Cycle ───────────────────────────────────────────────────────────────
def run_cycle():
    state = load_state()
    cycle = state.get('cycles', 0) + 1
    state['cycles'] = cycle
    now = now_utc()
    et = et_now()
    log_json({'event': 'CYCLE_START', 'cycle': cycle, 'now_utc': now.isoformat(), 'now_et': et.isoformat()})

    # 1. Hard cutoff / outside dayshift window guard
    # Dayshift window: 08:30 ET -> 16:00 ET Mon-Fri
    weekday = et.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    in_window = (weekday < 5 and
                 (et.hour > START_ET_HOUR or (et.hour == START_ET_HOUR and et.minute >= START_ET_MIN)) and
                 et.hour < CUTOFF_ET_HOUR)
    if not in_window:
        msg = f"Outside dayshift window. Now {et.strftime('%H:%M ET')} weekday={weekday}. No action."
        print(msg)
        log_json({'event': 'OUTSIDE_WINDOW', 'msg': msg})
        toast('Dayshift IDLE', msg, 'INFO')
        save_state({'cycles': cycle, 'open': [], 'last_run': now.isoformat(), 'stopped': True})
        return

    # 2. Broker executable probe (with capital check for MT5 brokers)
    broker_ok = {}
    for profile in BROKER_WATERFALL:
        ok, reason = broker_executable(profile)
        broker_ok[profile] = {'ok': ok, 'reason': reason}
        state['broker_state'][profile] = {'ok': ok, 'reason': reason, 'checked_at': now.isoformat()}
    executable_brokers = [p for p, s in broker_ok.items() if s['ok']]
    if not executable_brokers:
        msg = 'No executable brokers this cycle.'
        print(msg)
        log_json({'event': 'NO_BROKER', 'brokers': broker_ok})
        toast('Dayshift BLOCKED', msg, 'HIGH')
        save_state(state)
        return

    # 3. Close expired daytrades
    open_positions = state.get('open', [])
    open_positions, expired = close_all_expired(open_positions)
    if expired:
        toast('Dayshift CLOSE', f"Closed {len(expired)} expired daytrade(s).", 'HIGH')

    # 4. Load setups from scan artifacts: scandata/setups.json + workflow/*scan*.json + new dayshift scans
    setups = []
    scan_sources = []
    scandata_setups = BASE_DESKTOP / 'scandata' / 'setups.json'
    if scandata_setups.exists():
        try:
            data = json.loads(scandata_setups.read_text(encoding='utf-8'))
            items = data if isinstance(data, list) else data.get('setups', data.get('viable_setups', []))
            if isinstance(items, list):
                setups.extend(items)
                scan_sources.append(f'scandata/setups.json:{len(items)}')
        except Exception:
            pass
    # New dayshift pre-market scan format (qualified_setups + watchlist)
    for scan_file in sorted(BASE_DESKTOP.glob('scandata/DAYSHIFT_*_PREMKT_*.json'))[-3:]:
        try:
            data = json.loads(scan_file.read_text(encoding='utf-8'))
            items = data.get('qualified_setups', []) + data.get('watchlist', [])
            if isinstance(items, list):
                setups.extend(items)
                scan_sources.append(f'{scan_file.name}:{len(items)}')
        except Exception:
            pass
    for scan_file in sorted(OUT_DIR.glob('nightshift_scan_*.json'))[-3:]:
        try:
            data = json.loads(scan_file.read_text(encoding='utf-8'))
            items = data.get('viable_setups', [])
            if isinstance(items, list):
                setups.extend(items)
                scan_sources.append(f'{scan_file.name}:{len(items)}')
        except Exception:
            pass
    for scan_file in sorted((BASE_FIRM / 'scans').glob('*.json'))[-3:]:
        try:
            data = json.loads(scan_file.read_text(encoding='utf-8'))
            items = data.get('viable_setups', data.get('setups', []))
            if isinstance(items, list):
                setups.extend(items)
                scan_sources.append(f'{scan_file.name}:{len(items)}')
        except Exception:
            pass

    # Deduplicate by symbol+side, keep highest conviction
    seen = {}
    for s in setups:
        key = f"{s.get('symbol','').upper()}_{s.get('side','').upper()}"
        if key not in seen or s.get('conviction', 0) > seen[key].get('conviction', 0):
            seen[key] = s
    setups = list(seen.values())

    # If no scan artifacts found, fall back to lightweight MT5 scan
    if not setups:
        log_json({'event': 'NO_SCAN_ARTIFACTS', 'msg': 'Falling back to live symbol scan'})
        toast('Dayshift SCAN', 'No scan artifacts found, using live scan', 'INFO')
        for cls, syms in DAYSHIFT_UNIVERSE.items():
            for sym in syms:
                s = scan_symbol(sym, cls)
                if not s:
                    continue
                rsi = s['rsi']
                last = s['price']
                atr = s['atr']
                if atr <= 0 or last <= 0:
                    continue
                if rsi < 35 and last > s['sma50']:
                    side = 'BUY'
                    sl = round(last - 2 * atr, s.get('digits', 5) if isinstance(s, dict) else 5)
                    tp = round(last + 4 * atr, s.get('digits', 5) if isinstance(s, dict) else 5)
                    conf = min(100, max(0, int((35 - rsi) * 2 + 30)))
                    ns, nsc, _ = news_sentiment(sym, cls)
                    conf = max(0, min(100, conf + (10 if ns == 'BULLISH' else -10 if ns == 'BEARISH' else 0)))
                    setups.append({
                        'symbol': sym, 'class': cls, 'side': side,
                        'entry': last, 'sl': sl, 'tp': tp, 'atr': atr,
                        'rsi': rsi, 'conviction': conf, 'news_sentiment': ns, 'news_score': nsc,
                    })
                elif rsi > 65 and last < s['sma50']:
                    side = 'SELL'
                    sl = round(last + 2 * atr, s.get('digits', 5) if isinstance(s, dict) else 5)
                    tp = round(last - 4 * atr, s.get('digits', 5) if isinstance(s, dict) else 5)
                    conf = min(100, max(0, int((rsi - 65) * 2 + 30)))
                    ns, nsc, _ = news_sentiment(sym, cls)
                    conf = max(0, min(100, conf + (10 if ns == 'BEARISH' else -10 if ns == 'BULLISH' else 0)))
                    setups.append({
                        'symbol': sym, 'class': cls, 'side': side,
                        'entry': last, 'sl': sl, 'tp': tp, 'atr': atr,
                        'rsi': rsi, 'conviction': conf, 'news_sentiment': ns, 'news_score': nsc,
                    })

    log_json({'event': 'SETUPS_LOADED', 'count': len(setups), 'sources': scan_sources})
    toast('Dayshift SCAN', f"Loaded {len(setups)} setups from {len(scan_sources)} sources", 'INFO')

    # 5. Cap new tickets by MAX_OPEN
    slots = max(0, MAX_OPEN - len(open_positions))
    new_tickets = []
    for setup in sorted(setups, key=lambda x: x.get('conviction', 0), reverse=True)[:slots]:
        sym = setup.get('symbol', '').upper()
        side = setup.get('side', 'BUY').upper()
        if any(p.get('symbol', '').upper() == sym for p in open_positions):
            continue

        entry = float(setup.get('entry', setup.get('last', 0)))
        sl = float(setup.get('sl', 0))
        tp = float(setup.get('tp', 0))
        atr = float(setup.get('atr', 0))
        if sl <= 0 or tp <= 0:
            side_local = setup.get('side', 'BUY').upper()
            if atr > 0 and entry > 0:
                sl = entry - 2 * atr if side_local == 'BUY' else entry + 2 * atr
                tp = entry + 4 * atr if side_local == 'BUY' else entry - 4 * atr
            else:
                continue
        if entry <= 0 or sl <= 0 or tp <= 0:
            continue

        qty = float(setup.get('amount', 1000))

        for profile in executable_brokers:
            sym_norm = normalize_etoro_symbol(sym) if profile == 'etoro' else sym
            if profile == 'etoro' and sym_norm not in ETORO_INSTRUMENT_MAP:
                continue
            res, err = send_ticket(profile, sym_norm if profile == 'etoro' else sym, side, qty, entry, sl, tp)
            if res:
                ticket = {
                    'ticket': res.get('ticket') or res.get('deal'),
                    'symbol': sym,
                    'side': side,
                    'volume': qty,
                    'entry': float(entry),
                    'sl': float(sl),
                    'tp': float(tp),
                    'profile': profile,
                    'opened_at': now.isoformat(),
                    'conviction': setup.get('conviction', 0),
                    'news_sentiment': setup.get('news_sentiment', 'NEUTRAL'),
                }
                new_tickets.append(ticket)
                open_positions.append(ticket)
                log_json({'event': 'TICKET_PLACED', **ticket, 'retcode': res.get('retcode')})
                break
            else:
                log_json({'event': 'TICKET_FAIL', 'symbol': sym, 'profile': profile, 'err': err})

    # 6. Refresh open PnL
    refreshed = []
    for p in open_positions:
        profile = p.get('profile')
        ticket = p.get('ticket')
        sym = p.get('symbol', '').upper()
        if profile == 'etoro':
            try:
                auth = EtoroAuth()
                auth.load_secure_file(BASE_FIRM / '.broker_creds_secure.json')
                auth.load_env()
                auth.validate()
                headers = {
                    'x-request-id': str(__import__('uuid').uuid4()),
                    'x-api-key': auth.api_key,
                    'x-user-key': auth.user_key,
                    'Accept': 'application/json',
                }
                r = requests.get(f'https://public-api.etoro.com/api/v1/trading/info/{auth.mode}/portfolio', headers=headers, timeout=15)
                if r.status_code == 200:
                    positions = r.json().get('clientPortfolio', {}).get('positions', [])
                    for pos in positions:
                        if str(pos.get('positionID')) == str(ticket):
                            p['profit'] = float(pos.get('profit', 0.0))
                            p['current_price'] = float(pos.get('openRate', p.get('entry', 0)))
                            break
                refreshed.append(p)
            except Exception:
                refreshed.append(p)
            continue
        if profile == 'ibkr':
            ib = IB()
            try:
                ib.connect('127.0.0.1', 4002, clientId=2002, timeout=10)
                if ib.isConnected():
                    for trade in ib.trades():
                        if trade.orderStatus.orderId == ticket:
                            p['profit'] = float(trade.orderStatus.avgFillPrice or 0)
                            refreshed.append(p)
                            ib.disconnect()
                            break
                    else:
                        refreshed.append(p)
                        ib.disconnect()
                else:
                    refreshed.append(p)
            except Exception:
                try:
                    ib.disconnect()
                except Exception:
                    pass
                refreshed.append(p)
            continue
        # MT5 refresh path
        m = mt5_connect(profile)
        if not m:
            refreshed.append(p)
            continue
        try:
            pos = None
            for pos in (m.positions_get() or []):
                if pos.ticket == ticket:
                    break
            m.shutdown()
            if pos:
                p['profit'] = float(pos.profit)
                p['current_price'] = float(pos.price_current)
            refreshed.append(p)
        except Exception:
            try:
                m.shutdown()
            except Exception:
                pass
            refreshed.append(p)

    state['open'] = refreshed
    state['last_run'] = now.isoformat()
    save_state(state)

    # 7. Report
    placed = len(new_tickets)
    total_open = len(refreshed)
    summary = f"Cycle {cycle}: placed={placed}, open={total_open}, brokers={executable_brokers}"
    print(summary)
    log_json({'event': 'CYCLE_END', 'cycle': cycle, 'placed': placed, 'open': total_open, 'brokers': executable_brokers})
    toast('Dayshift CYCLE', summary, 'HIGH' if placed > 0 else 'INFO')

    # Save cycle artifact
    ts = now.strftime('%Y%m%d%H%M')
    artifact = OUT_DIR / f'dayshift_cycle_{ts}.json'
    artifact.write_text(json.dumps({'cycle': cycle, 'open': refreshed, 'placed': new_tickets, 'broker_state': broker_ok}, indent=2), encoding='utf-8')

def main():
    print(f"Dayshift autopilot started at {now_utc().isoformat()}")
    et = et_now()
    weekday = et.weekday()
    in_window = (weekday < 5 and
                 (et.hour > START_ET_HOUR or (et.hour == START_ET_HOUR and et.minute >= START_ET_MIN)) and
                 et.hour < CUTOFF_ET_HOUR)
    if not in_window:
        msg = f"Outside dayshift window. Now {et.strftime('%H:%M ET')} weekday={weekday}. No action."
        print(msg)
        log_json({'event': 'OUTSIDE_WINDOW', 'msg': msg})
        toast('Dayshift IDLE', msg, 'INFO')
        return
    run_cycle()
    print("Cycle complete. Task Scheduler will re-run at next interval.")

if __name__ == '__main__':
    main()