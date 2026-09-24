#!/usr/bin/env python3
"""
OuroTaurus Edge Engine v1 — Advanced unified scan + predictive scoring.
This is the persistent brain: learns, adapts, and routes across all brokers.
"""
import json, os, sys, time, math, datetime, hashlib, traceback
from pathlib import Path
from collections import deque

import pandas as pd
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*generic.*unit for NumPy timedelta.*')
warnings.filterwarnings('ignore', message='.*The generic unit for NumPy timedelta.*')
warnings.filterwarnings('ignore', message='.*Please use a specific unit instead.*')
import requests
import numpy as np
import yfinance as yf
from ib_insync import IB, Contract, Order
from etoro_auth import EtoroAuth
import MetaTrader5 as mt5

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
EDGE_STATE = BASE_FIRM / 'workflow' / 'edge_engine_state.json'
EDGE_LOG = BASE_FIRM / 'workflow' / 'edge_engine_log.jsonl'
EDGE_LEARN = BASE_FIRM / 'workflow' / 'edge_learning.json'
sys.path.insert(0, str(BASE_FIRM / 'scripts'))
from mt5_connect import connect as mt5_connect, KNOWN_BROKERS

# ── Config ───────────────────────────────────────────────────────────────────
BROKER_WATERFALL = ['etoro', 'ibkr', 'capital', 'ftmo']
MAX_OPEN = 4
RISK_PCT = 0.01
MAX_HOLD_SEC = 7200
DEVIATION = 20
MAGIC = 20260817

ETORO_INSTRUMENT_MAP = {
    'EURUSD': 1, 'GBPUSD': 2, 'NZDUSD': 3, 'USDCAD': 4, 'USDJPY': 5,
    'AUDUSD': 7, 'GBPAUD': 50, 'NZDJPY': 55, 'GBPCHF': 51, 'EURCHF': 9,
    'USDTRY': 62, 'USDCHF': 6, 'EURJPY': 10, 'GBPJPY': 11, 'AUDJPY': 14,
    'CADJPY': 15, 'CHFJPY': 16, 'NZDCHF': 54, 'NZDCAD': 53,
    'USDSEK': 58, 'USDNOK': 57, 'USDMXN': 59, 'USDZAR': 61, 'USDPLN': 52,
    'XAUUSD': 18, 'XAGUSD': 19,
    'US500': 28, 'SPX500': 27, 'US100': 29, 'US30': 26, 'UK100': 32, 'DE40': 25,
    'AUS200': 24, 'JPN225': 23, 'FRA40': 31, 'ES35': 34, 'ITA40': 36,
    'SPAIN35': 37, 'EU50': 38, 'HK50': 33, 'CHINA50': 35, 'INDIA50': 39,
    'BRAZIL60': 40, 'SOX': 30,
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

UNIVERSE = {
    'indices': ['US30','US500','US100','JP225','UK100','HK50','EU50','AU200','DE40','ES35','FR40','IT40','SG30'],
    'crypto': ['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD','DOGEUSD','FETUSD','RENDERUSD','GRTUSD','OCEANUSD','LDOUSD','ENSUSD'],
    'forex': [
        'EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF','NZDUSD','USDCAD',
        'EURJPY','EURGBP','GBPJPY','AUDJPY','AUDNZD','AUDCAD','CADJPY','CHFJPY','NZDJPY',
        'EURCHF','EURCAD','EURAUD','GBPCHF','GBPAUD','GBPCAD','GBPNZD','NZDCHF','NZDCAD',
        'USDTRY','USDZAR','USDMXN','USDCNH','USDSGD','USDHKD','USDTHB','USDSEK','USDNOK','USDDKK','USDPLN'
    ],
    'commodities': ['XAUUSD','XAGUSD','WTIOIL','BRENT','NGAS','COPPER'],
}

YFINANCE_MAP = {
    # Indices -> Yahoo tickers
    'US30': '^DJI', 'US500': '^GSPC', 'US100': '^IXIC', 'JP225': '^N225',
    'UK100': '^FTSE', 'HK50': '^HSI', 'EU50': '^STOXX50E', 'AU200': '^AXJO',
    'DE40': '^GDAXI', 'ES35': '^IBEX', 'FR40': '^FCHI', 'IT40': 'FTSEMIB.MI',
    'SG30': '^STI',
    # Crypto -> Yahoo tickers
    'BTCUSD': 'BTC-USD', 'ETHUSD': 'ETH-USD', 'SOLUSD': 'SOL-USD',
    'AVAXUSD': 'AVAX-USD', 'ADAUSD': 'ADA-USD', 'XRPUSD': 'XRP-USD',
    'DOTUSD': 'DOT-USD', 'LINKUSD': 'LINK-USD', 'DOGEUSD': 'DOGE-USD',
    'FETUSD': 'FET-USD', 'RENDERUSD': 'RENDER-USD', 'GRTUSD': 'GRT-USD',
    'OCEANUSD': 'OCEAN-USD', 'LDOUSD': 'LDO-USD', 'ENSUSD': 'ENS-USD',
    # Forex -> Yahoo tickers
    'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'USDJPY=X',
    'AUDUSD': 'AUDUSD=X', 'USDCHF': 'USDCHF=X', 'NZDUSD': 'NZDUSD=X',
    'USDCAD': 'USDCAD=X', 'EURJPY': 'EURJPY=X', 'EURGBP': 'EURGBP=X',
    'GBPJPY': 'GBPJPY=X', 'AUDJPY': 'AUDJPY=X', 'AUDNZD': 'AUDNZD=X',
    'AUDCAD': 'AUDCAD=X', 'CADJPY': 'CADJPY=X', 'CHFJPY': 'CHFJPY=X',
    'NZDJPY': 'NZDJPY=X', 'EURCHF': 'EURCHF=X', 'EURCAD': 'EURCAD=X',
    'EURAUD': 'EURAUD=X', 'GBPCHF': 'GBPCHF=X', 'GBPAUD': 'GBPAUD=X',
    'GBPCAD': 'GBPCAD=X', 'GBPNZD': 'GBPNZD=X', 'NZDCHF': 'NZDCHF=X',
    'NZDCAD': 'NZDCAD=X', 'USDTRY': 'USDTRY=X', 'USDZAR': 'USDZAR=X',
    'USDMXN': 'USDMXN=X', 'USDCNH': 'USDCNY=X', 'USDSGD': 'USDSGD=X',
    'USDHKD': 'USDHKD=X', 'USDTHB': 'USDTHB=X', 'USDSEK': 'USDSEK=X',
    'USDNOK': 'USDNOK=X', 'USDDKK': 'USDDKK=X', 'USDPLN': 'USDPLN=X',
    # Commodities -> Yahoo tickers
    'XAUUSD': 'GC=F', 'XAGUSD': 'SI=F', 'WTIOIL': 'CL=F', 'BRENT': 'BZ=F',
    'NGAS': 'NG=F', 'COPPER': 'HG=F',
}

# Symbols known to fail on IBKR paper gateway; skip to reduce noise.
SKIP_IBKR_SYMBOLS = {
    'DE40', 'XAUUSD', 'XAGUSD', 'WTIOIL', 'BRENT', 'NGAS', 'COPPER',
    'XRPUSD',
}

BULLISH_KW = ['surge','rally','breakout','adoption','approval','bullish','upgrade','inflow','ETF','beat','raise','growth']
BEARISH_KW = ['crash','ban','hack','bearish','downgrade','outflow','regulation','sell-off','collapse','miss','cut','recession']

_IBKR_CLIENT_ID_BASE = 4002

# ── Helpers ──────────────────────────────────────────────────────────────────
def now_utc(): return datetime.datetime.now(datetime.timezone.utc)
def now_et(): return now_utc().astimezone(datetime.timezone(datetime.timedelta(hours=-4)))

def log_json(obj):
    with EDGE_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': now_utc().isoformat(), **obj}, default=str) + '\n')

def toast(msg, submsg='', lvl='INFO'):
    import os as _os_dg
    if _os_dg.environ.get('OURO_DISABLE_TOAST','').strip().lower() in ('1','true','yes'):
        return  # bravo: toasts OFF
    try:
        from winotify import Notification
        Notification(app_id='EdgeEngine', title=msg, msg=submsg, duration='short').show()
    except Exception:
        pass

def load_learning():
    if EDGE_LEARN.exists():
        try:
            return json.loads(EDGE_LEARN.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'weights': {'trend': 1.0, 'rsi': 1.0, 'atr': 1.0, 'news': 1.0, 'corr': 1.0}, 'history': []}

def save_learning(learn):
    EDGE_LEARN.write_text(json.dumps(learn, indent=2), encoding='utf-8')

def update_learning(outcome):
    """Outcome = {'symbol':..., 'side':..., 'pnl':..., 'hold_sec':..., 'setup':...}"""
    learn = load_learning()
    learn['history'].append(outcome)
    if len(learn['history']) > 200:
        learn['history'] = learn['history'][-200:]
    # Adjust weights based on recent performance
    recent = learn['history'][-20:]
    if len(recent) >= 5:
        avg_pnl = sum(r.get('pnl', 0) for r in recent) / len(recent)
        # Simple adaptive: if losing, increase trend weight
        if avg_pnl < 0:
            learn['weights']['trend'] = min(2.5, learn['weights'].get('trend', 1.0) * 1.05)
            learn['weights']['rsi'] = max(0.5, learn['weights'].get('rsi', 1.0) * 0.95)
        else:
            learn['weights']['trend'] = max(0.8, learn['weights'].get('trend', 1.0) * 0.98)
    save_learning(learn)
    return learn

def load_state():
    if EDGE_STATE.exists():
        try:
            return json.loads(EDGE_STATE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'open': [], 'last_run': None, 'cycles': 0, 'broker_state': {}}

def save_state(state):
    EDGE_STATE.write_text(json.dumps(state, indent=2, default=str), encoding='utf-8')

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
        trade_allowed = bool(info.trade_allowed)
        equity = float(getattr(info, 'equity', 0))
        return trade_allowed and equity > 0, f"equity={equity:.2f} trade={trade_allowed}"
    except Exception as e:
        return False, f'MT5 error: {e}'

# ── eToro ────────────────────────────────────────────────────────────────────
def normalize_etoro_symbol(raw):
    sym = str(raw).upper()
    if '-' in sym and sym.endswith('USD'):
        sym = sym.replace('-USD', '')
    elif sym.endswith('USD') and len(sym) > 6:
        sym = sym[:-3]
    if sym.startswith('^'): sym = sym[1:]
    if sym.endswith('=F'): sym = sym[:-2]
    if sym.endswith('=X'): sym = sym[:-2]
    return sym

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
        'action': 'open', 'transaction': tx, 'instrumentID': instr_id,
        'orderType': 'mkt', 'leverage': 1, 'amount': float(qty),
        'orderCurrency': 'usd', 'stopLossRate': float(sl), 'takeProfitRate': float(tp),
    }
    url = f'https://public-api.etoro.com/api/v2/trading/execution/{mode}/orders'
    headers = {
        'x-request-id': str(__import__('uuid').uuid4()),
        'x-api-key': api_key, 'x-user-key': user_key,
        'Content-Type': 'application/json', 'Accept': 'application/json',
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return {'retcode': r.status_code, 'ticket': data.get('orderId'), 'deal': data.get('referenceId'), 'price': float(entry)}, None
        return None, f'HTTP {r.status_code}: {r.text[:200]}'
    except Exception as e:
        return None, f'etoro exception: {e}'

# ── IBKR ─────────────────────────────────────────────────────────────────────
def send_ticket_ibkr(symbol, side, qty, entry, sl, tp):
    ib = IB()
    try:
        ib.connect('127.0.0.1', 4002, clientId=2002, timeout=10)
        if not ib.isConnected():
            return None, 'IBKR not connected on 4002'
        sym = symbol.upper()
        if sym in ('XAGUSD', 'XAUUSD'):
            c = Contract(symbol=sym.replace('USD', ''), secType='CFD', exchange='SMART', currency='USD')
        elif sym in ('USDNOK','GBPNZD','USDSGD','USDCAD','USDSEK','USDMXN','USDZAR','USDPLN','USDTRY','NZDUSD','AUDUSD','GBPUSD','EURUSD','USDJPY','NZDJPY','GBPAUD','GBPCHF','EURCHF','EURJPY','GBPJPY','AUDJPY','CADJPY','CHFJPY','NZDCHF','NZDCAD'):
            base = sym[:3]
            quote = sym[3:]
            c = Contract(symbol=base, secType='CASH', exchange='IDEALPRO', currency=quote)
        elif sym in ('US500','SPX500','US30','US100','UK100','DE40','AUS200','JPN225','FRA40','ES35','ITA40','SPAIN35','EU50','HK50','CHINA50','INDIA50','BRAZIL60','SOX'):
            c = Contract(symbol=sym, secType='CFD', exchange='SMART', currency='USD')
        elif len(sym) == 6:
            base = sym[:3]
            quote = sym[3:6]
            c = Contract(symbol=base, secType='CASH', exchange='IDEALPRO', currency=quote)
        else:
            return None, f'Unsupported IBKR symbol mapping: {symbol}'
        qualified = ib.qualifyContracts(c)
        if not qualified:
            return None, 'IBKR contract qualification failed'
        c = qualified[0]
        if sym in ('XAGUSD', 'XAUUSD'):
            qty = 1
        order = Order(action=side.upper(), orderType='LMT', totalQuantity=qty, lmtPrice=entry, tif='GTC')
        trade = ib.placeOrder(c, order)
        time.sleep(0.5)
        status = trade.orderStatus.status
        if status in ('Submitted', 'Filled', 'PendingSubmit'):
            return {'retcode': 200, 'ticket': trade.orderStatus.orderId, 'deal': None, 'price': float(entry)}, None
        return None, f'IBKR status={status}'
    except Exception as e:
        return None, f'IBKR error: {e}'
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

# ── MT5 ──────────────────────────────────────────────────────────────────────
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
            'action': mt5.TRADE_ACTION_DEAL, 'symbol': symbol, 'volume': float(qty),
            'type': mt5.ORDER_TYPE_BUY if side == 'BUY' else mt5.ORDER_TYPE_SELL,
            'price': float(price), 'sl': float(sl), 'tp': float(tp),
            'deviation': DEVIATION, 'magic': MAGIC, 'comment': 'EDGE_ENGINE',
            'type_time': mt5.ORDER_TIME_GTC, 'type_filling': mt5.ORDER_FILLING_FOK,
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

# ── ADVANCED SCANNING ────────────────────────────────────────────────────────
def fetch_mtf_data(symbol):
    """Fetch 1H/4H/1D/1W data for multi-timeframe analysis."""
    try:
        yf_sym = YFINANCE_MAP.get(symbol, symbol)
        data = {}
        for tf, period, interval in [('1h', '60d', '1h'), ('4h', '120d', '4h'), ('1d', '2y', '1d'), ('1wk', '5y', '1wk')]:
            try:
                df = yf.download(yf_sym, period=period, interval=interval, progress=False)
                if df is not None and not df.empty and len(df) > 20:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = [col[0] if col[1] == yf_sym else col[1] for col in df.columns]
                    data[tf] = df
            except Exception:
                continue
        return data
    except Exception:
        return {}

def advanced_score(symbol, side, mtf_data, learn_weights):
    """Advanced scoring with multi-timeframe confluence, volume, volatility."""
    if not mtf_data:
        return 0, {}
    
    score_details = {}
    total_score = 0
    
    # Use 4H and 1D as primary
    primary_tf = '4h' if '4h' in mtf_data else '1d'
    primary_df = mtf_data.get(primary_tf)
    
    if primary_df is None or len(primary_df) < 20:
        return 0, {}
    
    closes = primary_df['Close'].values
    highs = primary_df['High'].values
    lows = primary_df['Low'].values
    volumes = primary_df.get('Volume', pd.Series(index=primary_df.index, data=np.ones(len(closes)))).values
    
    # RSI
    delta = np.diff(closes)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.mean(gain[-14:]) if len(gain) >= 14 else 1
    avg_loss = np.mean(loss[-14:]) if len(loss) >= 14 else 1
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    
    # Trend alignment across TFs
    trend_score = 0
    tf_count = 0
    for tf, df in mtf_data.items():
        if len(df) < 20:
            continue
        tf_count += 1
        c = df['Close'].values
        sma20 = np.mean(c[-20:])
        sma50 = np.mean(c[-50:]) if len(c) >= 50 else sma20
        if side == 'BUY' and c[-1] > sma20 > sma50:
            trend_score += 1
        elif side == 'SELL' and c[-1] < sma20 < sma50:
            trend_score += 1
        else:
            trend_score -= 0.5
    
    trend_score = (trend_score / max(tf_count, 1)) * learn_weights.get('trend', 1.0)
    
    # RSI score (moderate RSI is better)
    if side == 'BUY' and 40 <= rsi <= 60:
        rsi_score = 1.5 * learn_weights.get('rsi', 1.0)
    elif side == 'SELL' and 40 <= rsi <= 60:
        rsi_score = 1.5 * learn_weights.get('rsi', 1.0)
    elif side == 'BUY' and rsi < 30:
        rsi_score = 0.8 * learn_weights.get('rsi', 1.0)
    elif side == 'SELL' and rsi > 70:
        rsi_score = 0.8 * learn_weights.get('rsi', 1.0)
    else:
        rsi_score = -1.0 * learn_weights.get('rsi', 1.0)  # Penalize extremes
    
    # ATR quality
    atr = np.mean(np.abs(highs[-14:] - lows[-14:])) if len(highs) >= 14 else 0
    atr_pct = (atr / closes[-1]) * 100 if closes[-1] > 0 else 0
    atr_score = min(1.5, atr_pct * 10) * learn_weights.get('atr', 1.0)
    
    # Volume confirmation
    vol_score = 0
    if len(volumes) >= 20:
        avg_vol = np.mean(volumes[-20:])
        if side == 'BUY' and volumes[-1] > avg_vol * 1.2:
            vol_score = 0.5
        elif side == 'SELL' and volumes[-1] > avg_vol * 1.2:
            vol_score = 0.5
    
    total_score = trend_score + rsi_score + atr_score + vol_score
    
    score_details = {
        'rsi': round(float(rsi), 2),
        'trend_score': round(float(trend_score), 2),
        'rsi_score': round(float(rsi_score), 2),
        'atr_score': round(float(atr_score), 2),
        'vol_score': round(float(vol_score), 2),
        'total': round(float(total_score), 2),
        'side': side,
        'conviction': min(10, max(1, int(total_score * 2.5))),
    }
    
    return total_score, score_details

# ── NEWS / SENTIMENT ─────────────────────────────────────────────────────────
def news_sentiment(symbol):
    """Fast news sentiment scan."""
    try:
        yf_sym = YFINANCE_MAP.get(symbol, symbol)
        name = yf.Ticker(yf_sym).info.get('shortName', symbol)
        query = f"{name} stock news today"
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}&tbm=nws"
        try:
            r = requests.get(url, headers=headers, timeout=5)
            text = r.text.lower()
            bullish = sum(1 for kw in BULLISH_KW if kw in text)
            bearish = sum(1 for kw in BEARISH_KW if kw in text)
            if bullish > bearish:
                return 'BULLISH', bullish - bearish
            elif bearish > bullish:
                return 'BEARISH', bearish - bullish
            return 'NEUTRAL', 0
        except Exception:
            return 'NEUTRAL', 0
    except Exception:
        return 'NEUTRAL', 0

# ── ARBITRAGE DETECTION ──────────────────────────────────────────────────────
def detect_arbitrage(symbol):
    """Detect price inefficiencies across brokers for same asset."""
    prices = {}
    
    # eToro price (if available)
    if symbol in ETORO_INSTRUMENT_MAP:
        try:
            auth = EtoroAuth()
            auth.load_secure_file(BASE_FIRM / '.broker_creds_secure.json')
            auth.load_env()
            auth.validate()
            h = {'x-request-id': str(__import__('uuid').uuid4()), 'x-api-key': auth.api_key, 'x-user-key': auth.user_key}
            r = requests.get(f'https://public-api.etoro.com/api/v1/trading/info/demo/portfolio', headers=h, timeout=5)
            if r.status_code == 200:
                for p in r.json().get('clientPortfolio', {}).get('positions', []):
                    if p.get('instrumentID') == ETORO_INSTRUMENT_MAP.get(symbol):
                        prices['etoro'] = p.get('openRate')
                        break
        except Exception:
            pass
    
    # IBKR price
    try:
        ib = IB()
        try:
            ib.connect('127.0.0.1', 4002, clientId=4002, timeout=8)
        except Exception as exc:
            if 'already in use' in str(exc):
                raise RuntimeError('ibkr_client_in_use')
            raise
        sym = symbol.upper()
        if sym in SKIP_IBKR_SYMBOLS:
            pass
        elif sym in ('USDNOK','GBPNZD','USDSGD','USDCAD','USDSEK','USDMXN','USDZAR','USDPLN','USDTRY','NZDUSD','AUDUSD','GBPUSD','EURUSD','USDJPY','NZDJPY','GBPAUD','GBPCHF','EURCHF','EURJPY','GBPJPY','AUDJPY','CADJPY','CHFJPY','NZDCHF','NZDCAD'):
            c = Contract(symbol=sym[:3], secType='CASH', exchange='IDEALPRO', currency=sym[3:])
        elif sym in ('US500','SPX500','US30','US100','UK100','DE40','AUS200','JPN225','FRA40','ES35','ITA40','SPAIN35','EU50','HK50','CHINA50','INDIA50','BRAZIL60','SOX'):
            c = Contract(symbol=sym, secType='CFD', exchange='SMART', currency='USD')
        elif len(sym) == 6:
            c = Contract(symbol=sym[:3], secType='CASH', exchange='IDEALPRO', currency=sym[3:])
        else:
            c = None
        if c:
            q = ib.qualifyContracts(c)
            if q:
                tick = ib.reqMktData(q[0], '', False, False)
                ib.sleep(0.5)
                if tick.bid and tick.ask:
                    prices['ibkr'] = (tick.bid + tick.ask) / 2
        ib.disconnect()
    except RuntimeError as exc:
        if str(exc) != 'ibkr_client_in_use':
            pass
        # else: suppress known IBKR client-collision noise
    except Exception:
        pass
    
    # yfinance price
    try:
        yf_sym = YFINANCE_MAP.get(symbol, symbol)
        ticker = yf.Ticker(yf_sym)
        hist = ticker.history(period='1d', interval='1m', auto_adjust=True, progress=False)
        if not hist.empty:
            prices['yfinance'] = hist['Close'].iloc[-1]
    except Exception:
        pass
    
    if len(prices) >= 2:
        vals = list(prices.values())
        spread = max(vals) - min(vals)
        avg = np.mean(vals)
        if avg > 0 and spread / avg > 0.001:  # >0.1% spread = arbitrage opportunity
            return True, spread / avg, prices
    return False, 0, prices

# ── CORE SCAN LOOP ───────────────────────────────────────────────────────────
def scan_universe(learn_weights):
    """Scan all universes with advanced scoring."""
    setups = []
    
    for sector, symbols in UNIVERSE.items():
        for sym in symbols:
            try:
                mtf = fetch_mtf_data(sym)
                if not mtf:
                    continue
                
                # Determine side from primary timeframe
                primary_tf = '4h' if '4h' in mtf else '1d'
                df = mtf.get(primary_tf)
                if df is None or len(df) < 20:
                    continue
                
                closes = df['Close'].values
                sma20 = np.mean(closes[-20:])
                sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma20
                
                side = 'BUY' if closes[-1] > sma20 > sma50 else 'SELL' if closes[-1] < sma20 < sma50 else None
                if not side:
                    continue
                
                # Score
                score, details = advanced_score(sym, side, mtf, learn_weights)
                if score < 2.0:
                    continue
                
                # News sentiment
                sentiment, sent_score = news_sentiment(sym)
                
                # Arbitrage check
                arb, arb_spread, arb_prices = detect_arbitrage(sym)
                
                # ATR for SL/TP
                highs = df['High'].values
                lows = df['Low'].values
                atr = np.mean(np.abs(highs[-14:] - lows[-14:])) if len(highs) >= 14 else 0
                
                entry = float(closes[-1])
                atr = float(atr)
                digits = 5 if side == 'BUY' and 'USD' in sym and len(sym) == 6 else 2 if sym in ('XAUUSD','XAGUSD') else 3 if 'JPY' in sym else 5
                sl = round(entry - 1.2*atr, digits) if side == 'BUY' else round(entry + 1.2*atr, digits)
                tp = round(entry + 2.4*atr, digits) if side == 'BUY' else round(entry - 2.4*atr, digits)
                
                setup = {
                    'symbol': sym,
                    'sector': sector,
                    'side': side,
                    'entry': entry,
                    'sl': sl,
                    'tp': tp,
                    'atr': atr,
                    'rsi': details.get('rsi', 50),
                    'conviction': details.get('conviction', 5),
                    'score': score,
                    'trend_score': details.get('trend_score', 0),
                    'rsi_score': details.get('rsi_score', 0),
                    'atr_score': details.get('atr_score', 0),
                    'vol_score': details.get('vol_score', 0),
                    'news_sentiment': sentiment,
                    'news_score': sent_score,
                    'arbitrage': arb,
                    'arb_spread': arb_spread,
                    'arb_prices': arb_prices,
                    'broker_routing': ['etoro', 'ibkr', 'capital', 'ftmo'],
                    'data_source': 'edge_engine_v1',
                }
                setups.append(setup)
                log_json({'event': 'SETUP_FOUND', 'symbol': sym, 'side': side, 'conviction': setup['conviction'], 'score': score})
            except Exception as e:
                continue
    
    # Sort by conviction
    setups.sort(key=lambda x: x.get('conviction', 0), reverse=True)
    return setups

# ── POSITION SIZING ──────────────────────────────────────────────────────────
def size_position(symbol, side, entry, sl, tp, profile, equity):
    """Dynamic position sizing based on volatility and conviction."""
    risk_dist = abs(entry - sl)
    if risk_dist <= 0:
        return 0
    
    risk_amount = equity * RISK_PCT
    
    # Adjust by volatility
    atr_mult = 1.0
    try:
        yf_sym = YFINANCE_MAP.get(symbol, symbol)
        ticker = yf.Ticker(yf_sym)
        hist = ticker.history(period='20d', interval='1d', auto_adjust=True, progress=False)
        if not hist.empty and len(hist) >= 14:
            atr = np.mean(np.abs(hist['High'].values[-14:] - hist['Low'].values[-14:]))
            atr_pct = atr / hist['Close'].values[-1]
            if atr_pct > 0.05:  # High vol
                atr_mult = 0.7
            elif atr_pct < 0.015:  # Low vol
                atr_mult = 1.3
    except Exception:
        pass
    
    risk_amount *= atr_mult
    
    if symbol in ('XAUUSD', 'XAGUSD'):
        risk_per_unit = risk_dist * 100
        qty = risk_amount / risk_per_unit
        return max(0.01, min(1.0, qty))
    elif len(symbol) == 6 and 'USD' in symbol:
        risk_per_unit = risk_dist * 100000
        qty = risk_amount / risk_per_unit
        return max(0.01, min(50.0, qty))
    else:
        return 1000.0  # Default for indices/CFDs

# ── EXECUTION ────────────────────────────────────────────────────────────────
def send_ticket(profile, symbol, side, qty, entry, sl, tp):
    if profile == 'etoro':
        return send_ticket_etoro(symbol, side, qty, entry, sl, tp)
    if profile == 'ibkr':
        return send_ticket_ibkr(symbol, side, qty, entry, sl, tp)
    return send_ticket_mt5(profile, symbol, side, qty, entry, sl, tp)

def refresh_positions(open_positions):
    """Refresh PnL on all open positions."""
    refreshed = []
    
    for p in open_positions:
        profile = p.get('profile')
        ticket = p.get('ticket')
        sym = p.get('symbol', '').upper()
        
        try:
            if profile == 'etoro':
                auth = EtoroAuth()
                auth.load_secure_file(BASE_FIRM / '.broker_creds_secure.json')
                auth.load_env()
                auth.validate()
                h = {'x-request-id': str(__import__('uuid').uuid4()), 'x-api-key': auth.api_key, 'x-user-key': auth.user_key}
                r = requests.get(f'https://public-api.etoro.com/api/v1/trading/info/{auth.mode}/portfolio', headers=h, timeout=10)
                if r.status_code == 200:
                    for pos in r.json().get('clientPortfolio', {}).get('positions', []):
                        if str(pos.get('positionID')) == str(ticket):
                            p['profit'] = float(pos.get('profit', 0.0))
                            p['current_price'] = float(pos.get('openRate', p.get('entry', 0)))
                            break
            elif profile == 'ibkr':
                ib = IB()
                ib.connect('127.0.0.1', 4002, clientId=2002, timeout=5)
                if ib.isConnected():
                    trades = ib.trades()
                    for trade in trades:
                        if trade.orderStatus.orderId == ticket:
                            p['profit'] = float(trade.orderStatus.avgFillPrice or 0)
                            break
                    ib.disconnect()
            else:
                m = mt5_connect(profile)
                if m:
                    for pos in (m.positions_get() or []):
                        if pos.ticket == ticket:
                            p['profit'] = float(pos.profit)
                            p['current_price'] = float(pos.price_current)
                            break
                    m.shutdown()
        except Exception:
            pass
        
        refreshed.append(p)
    
    return refreshed

# ── MAIN CYCLE ───────────────────────────────────────────────────────────────
def run_cycle():
    state = load_state()
    cycle = state.get('cycles', 0) + 1
    state['cycles'] = cycle
    now = now_utc()
    log_json({'event': 'CYCLE_START', 'cycle': cycle, 'now_utc': now.isoformat()})
    
    # 1. Broker probe
    broker_ok = {}
    for profile in BROKER_WATERFALL:
        ok, reason = broker_executable(profile)
        broker_ok[profile] = {'ok': ok, 'reason': reason}
        state['broker_state'][profile] = {'ok': ok, 'reason': reason, 'checked_at': now.isoformat()}
    
    executable_brokers = [p for p, s in broker_ok.items() if s['ok']]
    if not executable_brokers:
        print('No executable brokers this cycle.')
        log_json({'event': 'NO_BROKER', 'brokers': broker_ok})
        toast('EdgeEngine BLOCKED', 'No executable brokers', 'HIGH')
        save_state(state)
        return
    
    # 2. Load learning weights
    learn = load_learning()
    weights = learn.get('weights', {})
    
    # 3. Scan universe with advanced scoring
    setups = scan_universe(weights)
    log_json({'event': 'SCAN_COMPLETE', 'setups_found': len(setups)})
    toast('EdgeEngine SCAN', f'Found {len(setups)} advanced setups', 'INFO')
    
    if not setups:
        print('No setups found.')
        save_state(state)
        return
    
    # 4. Refresh existing positions
    open_positions = state.get('open', [])
    open_positions = refresh_positions(open_positions)
    
    # 5. Close positions that hit SL/TP or thesis break
    closed = []
    still_open = []
    for p in open_positions:
        profit = p.get('profit', 0)
        entry = p.get('entry', 0)
        current = p.get('current_price', entry)
        sl = p.get('sl', 0)
        tp = p.get('tp', 0)
        side = p.get('side', 'BUY')
        
        should_close = False
        reason = ''
        
        if profit >= 2500:  # FTMO challenge target
            should_close = True
            reason = 'TARGET_HIT'
        elif profit <= -500:  # Risk management
            should_close = True
            reason = 'STOP_LOSS'
        elif side == 'BUY' and current <= sl:
            should_close = True
            reason = 'SL_HIT'
        elif side == 'SELL' and current >= sl:
            should_close = True
            reason = 'SL_HIT'
        elif side == 'BUY' and current >= tp:
            should_close = True
            reason = 'TP_HIT'
        elif side == 'SELL' and current <= tp:
            should_close = True
            reason = 'TP_HIT'
        
        if should_close:
            closed.append({'ticket': p.get('ticket'), 'symbol': p.get('symbol'), 'reason': reason, 'profit': profit})
            log_json({'event': 'POSITION_CLOSED', **p, 'close_reason': reason})
        else:
            still_open.append(p)
    
    open_positions = still_open
    
    # 6. Cap by MAX_OPEN
    slots = max(0, MAX_OPEN - len(open_positions))
    new_tickets = []
    
    for setup in setups[:slots]:
        sym = setup.get('symbol', '').upper()
        side = setup.get('side', 'BUY').upper()
        
        # Dedup
        if any(p.get('symbol', '').upper() == sym for p in open_positions):
            continue
        
        entry = float(setup.get('entry', 0))
        sl = float(setup.get('sl', 0))
        tp = float(setup.get('tp', 0))
        if entry <= 0 or sl <= 0 or tp <= 0:
            continue
        
        # Size
        equity = 200000.0  # FTMO challenge account
        qty = size_position(sym, side, entry, sl, tp, 'ftmo', equity)
        if qty <= 0:
            continue
        
        # Try brokers in waterfall
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
                    'conviction': setup.get('conviction', 5),
                    'score': setup.get('score', 0),
                    'news_sentiment': setup.get('news_sentiment', 'NEUTRAL'),
                    'arbitrage': setup.get('arbitrage', False),
                }
                new_tickets.append(ticket)
                open_positions.append(ticket)
                log_json({'event': 'TICKET_PLACED', **ticket, 'retcode': res.get('retcode')})
                break
            else:
                log_json({'event': 'TICKET_FAIL', 'symbol': sym, 'profile': profile, 'err': str(err)[:200]})
    
    # 7. Learn from closed positions
    for c in closed:
        outcome = {
            'symbol': c.get('symbol'),
            'reason': c.get('reason'),
            'pnl': c.get('profit', 0),
            'hold_sec': 0,
        }
        update_learning(outcome)
    
    # 8. Save state
    state['open'] = open_positions
    state['last_run'] = now.isoformat()
    save_state(state)
    
    # 9. Report
    placed = len(new_tickets)
    total_open = len(open_positions)
    summary = f"Cycle {cycle}: placed={placed}, open={total_open}, closed={len(closed)}, brokers={executable_brokers}"
    print(summary)
    log_json({'event': 'CYCLE_END', 'cycle': cycle, 'placed': placed, 'open': total_open, 'closed': len(closed), 'brokers': executable_brokers})
    toast('EdgeEngine CYCLE', summary, 'HIGH' if placed > 0 else 'INFO')

def main():
    print(f"Edge Engine v1 started at {now_utc().isoformat()}")
    try:
        while True:
            run_cycle()
            time.sleep(300)  # 5 min cycles
    except KeyboardInterrupt:
        print("Edge Engine stopped.")

if __name__ == '__main__':
    main()
