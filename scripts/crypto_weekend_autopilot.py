#!/usr/bin/env python3
"""
Crypto Weekend Autopilot — scan/set/close crypto trades Fri 16:00 ET -> Sun 17:00 ET.
Windows Task Scheduler should call this every N minutes during crypto weekend window.
"""
import json, os, sys, time, math, datetime, warnings
from pathlib import Path

warnings.filterwarnings("ignore")

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except Exception:
    HAS_WINOTIFY = False
    import os as _os_dg
    if _os_dg.environ.get('OURO_DISABLE_TOAST','').strip().lower() in ('1','true','yes'):
        HAS_WINOTIFY = False  # bravo: toasts OFF, Telegram-only

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import yfinance as yf
warnings.filterwarnings("ignore")

# ── Config ──────────────────────────────────────────────────────────────────
BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
STATE_FILE = BASE_FIRM / 'workflow' / 'crypto_weekend_state.json'
LOG_FILE = BASE_FIRM / 'workflow' / 'crypto_weekend_log.jsonl'
OUT_DIR = BASE_FIRM / 'workflow'

CYCLE_SEC = 900          # 15 min between cycles
MAX_OPEN = 4             # max concurrent open positions
MAX_HOLD_SEC = 14400     # 4 hours max hold per scalp
RISK_PCT = 0.01          # 1% per trade
DEVIATION = 20
MAGIC = 20260813

# Crypto weekend window in ET: Fri 16:00 -> Sun 17:00
CUTOFF_ET_HOUR_SUNDAY = 17
START_ET_HOUR_FRIDAY = 16
START_ET_MIN_FRIDAY = 0

sys.path.insert(0, str(BASE_FIRM / 'scripts'))
from mt5_connect import connect as mt5_connect, KNOWN_BROKERS

BROKER_WATERFALL = ['ftmo', 'capital', 'kraken']  # Add Kraken for crypto weekend

# ── Crypto Universe ─────────────────────────────────────────────────────────
CRYPTO_UNIVERSE = [
    'BTC-USD','ETH-USD','SOL-USD','XRP-USD','AVAX-USD','LINK-USD','AAVE-USD','UNI-USD',
    'DOGE-USD','BNB-USD','XMR-USD','NEAR-USD','MATIC-USD','ADA-USD','DOT-USD','LTC-USD',
    'ATOM-USD','FTM-USD','ALGO-USD','SAND-USD','MANA-USD','ENJ-USD','BAT-USD','ZRX-USD',
    'ICX-USD','VET-USD','XTZ-USD','EGLD-USD','KSM-USD','DASH-USD','ZEC-USD','WAVES-USD'
]

MT5_CRYPTO = ['BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'ADAUSD', 'DOGEUSD', 'BNBUSD']

# ── Helpers ──────────────────────────────────────────────────────────────────
def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

def et_now():
    return now_utc().astimezone(datetime.timezone(datetime.timedelta(hours=-4)))

def toast(title, msg, urgency='INFO'):
    if not HAS_WINOTIFY:
        return
    try:
        n = Notification(app_id="Zeus CryptoWeekend", title=title, msg=msg)
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
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'cycles': 0, 'open': [], 'last_run': None, 'broker_state': {}}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')

def yf_close(sym, period="1mo", interval="1h"):
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(period=period, interval=interval, auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 25:
            return None
        return {
            'closes': [float(x) for x in hist['Close'].tolist()],
            'highs': [float(x) for x in hist['High'].tolist()],
            'lows': [float(x) for x in hist['Low'].tolist()],
            'volumes': [float(x) for x in hist['Volume'].tolist()],
        }
    except Exception:
        return None

def rsi14(closes):
    if len(closes) < 15: return 50.0
    gains=[]; losses=[]
    for i in range(1,15):
        d=closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(-min(d,0))
    ag=sum(gains)/14; al=sum(losses)/14
    if al==0: return 100.0 if ag>0 else 50.0
    rs=ag/al
    return 100-100/(1+rs)

def atr14(highs, lows, closes):
    if len(closes)<15: return None
    tr=[]
    for i in range(1,len(closes)):
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    if len(tr)<14: return None
    return sum(tr[-14:])/14

def conviction_score(rsi, macd_line, macd_signal, price, bb_lower, bb_upper):
    score=0; components={}
    if rsi < 30: rp=30
    elif 30 <= rsi < 40: rp=20
    elif 60 <= rsi <= 70: rp=10
    else: rp=0
    components['rsi_p']=rp; score+=rp

    bullish_cross = macd_line > macd_signal and macd_line > 0
    if bullish_cross: mp=30
    elif macd_line > macd_signal: mp=20
    elif macd_line < macd_signal: mp=10
    else: mp=0
    components['macd_p']=mp; score+=mp

    if price < bb_lower: bp=25
    elif price > bb_upper: bp=0
    else: bp=0
    components['bb_p']=bp; score+=bp

    components['total']=score
    return max(0, min(100, score)), components

def ema(values, span):
    out=[]; m=2/(span+1); prev=sum(values[:span])/span; out.append(prev)
    for v in values[span:]:
        prev=(v-prev)*m+prev; out.append(prev)
    return out

def macd_bias(closes):
    if len(closes)<35: return 'neutral'
    e12=ema(closes,12); e26=ema(closes,26)
    m=[x-y for x,y in zip(e12,e26)]
    s=ema(m,9)
    return 'bullish' if m[-1]>s[-1] else 'bearish' if m[-1]<s[-1] else 'neutral'

def bollinger(closes, n=20, k=2):
    if len(closes)<n: return None, None, None
    m=sum(closes[-n:])/n
    var=sum((x-m)**2 for x in closes[-n:])/n
    std=math.sqrt(var)
    return m-k*std, m, m+k*std

def scan_crypto_symbol(sym):
    d = yf_close(sym, period='5d', interval='1h')
    if not d or len(d['closes']) < 25:
        return None
    closes = d['closes']; highs = d['highs']; lows = d['lows']
    rsi = rsi14(closes)
    macd_b = macd_bias(closes)
    bb_lower, bb_middle, bb_upper = bollinger(closes)
    atr = atr14(highs, lows, closes)
    price = closes[-1]
    score, comps = conviction_score(rsi, 0 if macd_b=='neutral' else (1 if macd_b=='bullish' else -1),
                                   0, price, bb_lower or price*0.95, bb_upper or price*1.05)
    side = 'BUY' if score >= 55 and rsi < 45 else ('SELL' if score <= 35 and rsi > 55 else None)
    if side and atr:
        sl = price - 2*atr if side == 'BUY' else price + 2*atr
        tp = price + 4*atr if side == 'BUY' else price - 4*atr
    else:
        sl = tp = None
    return {
        'symbol': sym, 'price': price, 'rsi': rsi, 'macd': macd_b,
        'conviction': score, 'side': side, 'atr': atr, 'sl': sl, 'tp': tp
    }

def broker_executable(profile):
    try:
        m = mt5_connect(profile)
        if not m:
            return False, 'no_connection'
        info = m.account_info()
        m.shutdown()
        if not info:
            return False, 'no_account_info'
        return bool(info.trade_allowed), f"trade_allowed={info.trade_allowed}"
    except Exception as e:
        return False, f'exception={e}'

def send_ticket(profile, symbol, side, qty, entry, sl, tp):
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
            'comment': 'CRYPTO_WEEKEND',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,
        }
        res = m.order_send(req)
        m.shutdown()
        rc = getattr(res, 'retcode', None)
        comment = getattr(res, 'comment', '')
        ticket = getattr(res, 'order', None) or getattr(res, 'deal', None)
        if rc in (10009, 10008, 10004):
            return {'retcode': rc, 'ticket': ticket, 'price': float(price)}, None
        return None, f'retcode={rc} {comment}'
    except Exception as e:
        try:
            m.shutdown()
        except Exception:
            pass
        return None, f'exception={e}'

def close_position_weekend(profile, symbol, ticket, volume, side):
    m = mt5_connect(profile)
    if not m:
        return False, 'no_mt5_connection'
    try:
        tick = m.symbol_info_tick(symbol)
        price = tick.bid if side == 'BUY' else tick.ask
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': float(volume),
            'type': mt5.ORDER_TYPE_SELL if side == 'BUY' else mt5.ORDER_TYPE_BUY,
            'position': int(ticket),
            'price': float(price),
            'deviation': DEVIATION,
            'magic': MAGIC,
            'comment': 'CRYPTO_WEEKEND_CLOSE',
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
            ok, out = close_position_weekend(profile, symbol, ticket, p.get('volume', 0.01), p.get('side', 'BUY'))
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
    ts = now.strftime('%Y%m%dT%H%MZ')
    log_json({'event': 'CYCLE_START', 'cycle': cycle, 'now_utc': now.isoformat(), 'now_et': et.isoformat()})

    # 1. Window guard: Fri 16:00 ET -> Sun 17:00 ET
    weekday = et.weekday()  # Mon=0, Fri=4, Sun=6
    in_window = False
    if weekday == 4:  # Friday
        in_window = (et.hour > START_ET_HOUR_FRIDAY or (et.hour == START_ET_HOUR_FRIDAY and et.minute >= START_ET_MIN_FRIDAY))
    elif weekday == 5:  # Saturday all day
        in_window = True
    elif weekday == 6:  # Sunday
        in_window = et.hour < CUTOFF_ET_HOUR_SUNDAY or (et.hour == CUTOFF_ET_HOUR_SUNDAY and et.minute < 0)
    if not in_window:
        msg = f"Outside crypto weekend window. Now {et.strftime('%H:%M ET')} {et.strftime('%A')}. No action."
        print(msg)
        log_json({'event': 'OUTSIDE_WINDOW', 'msg': msg})
        toast('CryptoWeekend IDLE', msg, 'INFO')
        save_state({'cycles': cycle, 'open': [], 'last_run': now.isoformat(), 'stopped': True})
        return

    # 2. Broker probe
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
        toast('CryptoWeekend BLOCKED', msg, 'HIGH')
        save_state(state)
        return

    # 3. Close expired
    open_positions = state.get('open', [])
    open_positions, expired = close_all_expired(open_positions)
    if expired:
        toast('CryptoWeekend CLOSE', f"Closed {len(expired)} expired scalp(s).", 'HIGH')

    # 4. Scan crypto universe
    setups = []
    for sym in CRYPTO_UNIVERSE:
        s = scan_crypto_symbol(sym)
        if not s or not s['side']:
            continue
        setups.append(s)

    # 5. Cap new tickets by MAX_OPEN
    slots = max(0, MAX_OPEN - len(open_positions))
    new_tickets = []
    for setup in sorted(setups, key=lambda x: x['conviction'], reverse=True)[:slots]:
        sym = setup['symbol']
        if any(p.get('symbol') == sym for p in open_positions):
            continue
        for profile in executable_brokers:
            m = None
            try:
                m = mt5_connect(profile)
                if not m:
                    continue
                # For MT5, normalize symbol name
                mt5_sym = sym.replace('-USD','USD')
                info = m.symbol_info(mt5_sym)
                if not info or not getattr(info, 'visible', False):
                    m.shutdown()
                    continue
                tick = m.symbol_info_tick(mt5_sym)
                if not tick:
                    m.shutdown()
                    continue
                entry = tick.ask if setup['side'] == 'BUY' else tick.bid
                risk_usd = 700 * RISK_PCT  # placeholder equity; adjust when state tracks equity
                sl_dist = abs(entry - setup['sl'])
                tick_size = info.trade_tick_size or info.point or 0.0001
                tick_value = float(info.trade_tick_value or 0.0)
                if tick_value <= 0:
                    tick_value = 1.0
                sl_pts = sl_dist / tick_size
                if sl_pts <= 0:
                    m.shutdown()
                    continue
                raw = risk_usd / (sl_pts * tick_value)
                step = float(info.volume_step) if info.volume_step else 0.01
                qty = round(raw / step) * step
                qty = max(info.volume_min, min(info.volume_max, qty))
                qty = round(qty, 2 if step >= 0.01 else 1)
                res, err = send_ticket(profile, mt5_sym, setup['side'], qty, entry, setup['sl'], setup['tp'])
                if res:
                    ticket = {
                        'ticket': res.get('ticket'),
                        'symbol': sym,
                        'side': setup['side'],
                        'volume': qty,
                        'entry': float(entry),
                        'sl': float(setup['sl']),
                        'tp': float(setup['tp']),
                        'profile': profile,
                        'opened_at': now.isoformat(),
                        'conviction': setup['conviction'],
                        'rsi': setup['rsi'],
                        'macd': setup['macd'],
                    }
                    new_tickets.append(ticket)
                    open_positions.append(ticket)
                    log_json({'event': 'TICKET_PLACED', **ticket, 'retcode': res.get('retcode')})
                else:
                    log_json({'event': 'TICKET_FAIL', 'symbol': sym, 'profile': profile, 'err': err})
                m.shutdown()
                break
            except Exception as e:
                try:
                    if m:
                        m.shutdown()
                except Exception:
                    pass
                log_json({'event': 'TICKET_EXCEPTION', 'symbol': sym, 'profile': profile, 'err': str(e)})

    # 6. Refresh open PnL
    refreshed = []
    for p in open_positions:
        profile = p.get('profile')
        ticket = p.get('ticket')
        sym = p.get('symbol')
        m = None
        try:
            m = mt5_connect(profile)
            if not m:
                refreshed.append(p)
                continue
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
                if m:
                    m.shutdown()
            except Exception:
                pass
            refreshed.append(p)

    state['open'] = refreshed
    state['last_run'] = now.isoformat()
    save_state(state)

    placed = len(new_tickets)
    total_open = len(refreshed)
    summary = f"CryptoWeekend cycle {cycle}: placed={placed}, open={total_open}, brokers={executable_brokers}"
    print(summary)
    log_json({'event': 'CYCLE_END', 'cycle': cycle, 'placed': placed, 'open': total_open, 'brokers': executable_brokers})
    toast('CryptoWeekend CYCLE', summary, 'HIGH' if placed > 0 else 'INFO')

    # Save cycle artifact
    artifact = OUT_DIR / f'crypto_weekend_cycle_{ts}.json'
    artifact.write_text(json.dumps({
        'cycle': cycle,
        'setups': setups,
        'open': refreshed,
        'placed': new_tickets,
        'broker_state': broker_ok
    }, indent=2), encoding='utf-8')

def main():
    print(f"CryptoWeekend autopilot started at {now_utc().isoformat()}")
    et = et_now()
    weekday = et.weekday()
    in_window = False
    if weekday == 4:
        in_window = (et.hour > START_ET_HOUR_FRIDAY or (et.hour == START_ET_HOUR_FRIDAY and et.minute >= START_ET_MIN_FRIDAY))
    elif weekday == 5:
        in_window = True
    elif weekday == 6:
        in_window = et.hour < CUTOFF_ET_HOUR_SUNDAY or (et.hour == CUTOFF_ET_HOUR_SUNDAY and et.minute < 0)
    if not in_window:
        msg = f"Outside crypto weekend window. Now {et.strftime('%H:%M ET')} {et.strftime('%A')}. No action."
        print(msg)
        log_json({'event': 'OUTSIDE_WINDOW', 'msg': msg})
        toast('CryptoWeekend IDLE', msg, 'INFO')
        return
    run_cycle()
    print("Cycle complete. Task Scheduler will re-run at next interval.")

if __name__ == '__main__':
    main()
