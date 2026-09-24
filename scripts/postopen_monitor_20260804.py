#!/usr/bin/env python3
"""
Post-open monitor: scans all sectors and alerts ONLY when a setup passes tradegate.
Designed to run at 09:45, 11:00, 13:00 ET.
Output: JSON alert if high-grade setups found, else quiet.
"""
import json, time, os
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

TERMINAL = r'REDACTED-PATH'
LOGIN = int(os.environ.get('FTMO_MT5_LOGIN', '0'))
PW = os.environ.get('FTMO_MT5_PASSWORD', '')
SERVER = os.environ.get('FTMO_MT5_SERVER', '')
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
OUT = BASE / 'artifacts' / f'postopen_alert_20260804T{datetime.now(timezone.utc).strftime("%H%M")}Z.json'

UNIVERSE = {
    'indices': ['US30Cash','US100Cash','US500Cash','UK100Cash','DE40Cash','JP225Cash','AUS200Cash','SPX500','NAS100','DJ30'],
    'forex': ['EURUSD','GBPUSD','USDJPY','EURJPY','GBPJPY','AUDUSD','NZDUSD','USDCHF','EURGBP','USDCNH','USDMXN'],
    'commodities': ['XAUUSD','XAGUSD','USOIL','UKOIL','NGAS','WHEAT','CORN','COCOA','SUGAR'],
    'crypto': ['BTCUSD','ETHUSD','SOLUSD','XRPUSD','DOGEUSD','DOTUSD','ADAUSD','LINKUSD'],
    'bonds_rates': ['US10Y','US30Y','DE10Y','JP10Y','UK10Y'],
    'etfs_proxies': ['SPY500','NDQ100','DOW30','RSI30','VOL'],
}

VWAP_PERIOD = 20
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
BACKTEST_BARS = 90

def init_ftmo():
    mt5.shutdown()
    time.sleep(1)
    ok = mt5.initialize(TERMINAL, login=LOGIN, password=PW, server=SERVER)
    if not ok:
        return False, mt5.last_error()
    acct = mt5.account_info()
    if not acct or acct.login != LOGIN:
        mt5.shutdown()
        return False, 'account_mismatch'
    return True, acct

def get_rates(symbol, timeframe=mt5.TIMEFRAME_H1, bars=BACKTEST_BARS):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) < 50:
        return None
    return rates

def calc_vwap(rates):
    tp_vol = 0.0
    vol = 0.0
    for r in rates[-VWAP_PERIOD:]:
        tp = (r['high'] + r['low'] + r['close']) / 3
        v = r['real_volume'] if 'real_volume' in r.dtype.names else 1
        tp_vol += tp * v
        vol += v
    return tp_vol / vol if vol > 0 else None

def calc_ema(values, span):
    out = []
    mult = 2 / (span + 1)
    prev = sum(values[:span]) / span
    out.append(prev)
    for v in values[span:]:
        prev = (v - prev) * mult + prev
        out.append(prev)
    return out

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))

def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period

def detect_open_reversal(rates):
    if len(rates) < 3:
        return False
    prev_close = rates[-2]['close']
    curr_open = rates[-1]['open']
    curr_close = rates[-1]['close']
    gap = curr_open - prev_close
    if abs(gap) == 0:
        return False
    if gap < 0 and curr_close > curr_open:
        return True
    if gap > 0 and curr_close < curr_open:
        return True
    return False

def detect_bull_breakout(rates):
    if len(rates) < 20:
        return False
    recent_high = max(r['high'] for r in rates[-20:-1])
    curr_close = rates[-1]['close']
    curr_vol = rates[-1]['real_volume'] if 'real_volume' in rates[-1].dtype.names else 1
    prev_vol = rates[-2]['real_volume'] if 'real_volume' in rates[-2].dtype.names else 1
    return curr_close > recent_high and curr_vol > prev_vol

def detect_1pm_formation(rates):
    if len(rates) < 8:
        return False
    mid_idx = len(rates) // 2
    mid_bar = rates[mid_idx]
    prev_bar = rates[mid_idx - 1]
    body = abs(mid_bar['close'] - mid_bar['open'])
    total_range = mid_bar['high'] - mid_bar['low']
    if total_range == 0:
        return False
    return body / total_range > 0.7 and mid_bar['close'] != mid_bar['open']

def backtest_simple(rates, side, sl_mult=1.0, tp_mult=2.0):
    if len(rates) < 30:
        return {'win_rate': 0, 'expectancy': 0, 'trades': 0}
    closes = [r['close'] for r in rates]
    highs = [r['high'] for r in rates]
    lows = [r['low'] for r in rates]
    atr = calc_atr(highs, lows, closes)
    if not atr or atr == 0:
        return {'win_rate': 0, 'expectancy': 0, 'trades': 0}
    wins = 0
    losses = 0
    total_r = 0
    for i in range(20, len(rates)-1):
        entry = closes[i]
        sl = entry - sl_mult * atr if side == 'LONG' else entry + sl_mult * atr
        tp = entry + tp_mult * atr if side == 'LONG' else entry - tp_mult * atr
        for j in range(i+1, len(rates)):
            if side == 'LONG':
                if lows[j] <= sl:
                    losses += 1
                    total_r -= 1
                    break
                if highs[j] >= tp:
                    wins += 1
                    total_r += 2
                    break
            else:
                if highs[j] >= sl:
                    losses += 1
                    total_r -= 1
                    break
                if lows[j] <= tp:
                    wins += 1
                    total_r += 2
                    break
    trades = wins + losses
    win_rate = wins / trades if trades > 0 else 0
    expectancy = total_r / trades if trades > 0 else 0
    return {'win_rate': round(win_rate, 2), 'expectancy': round(expectancy, 2), 'trades': trades}

def tradegate(win_rate, expectancy, rsi, formations):
    reasons = []
    if win_rate < 0.45:
        reasons.append('win_rate_low')
    if expectancy <= 0:
        reasons.append('expectancy_negative')
    if rsi is not None and 40 <= rsi <= 60:
        reasons.append('rsi_neutral')
    if not formations:
        reasons.append('no_formation')
    if reasons:
        return {'pass': False, 'reasons': reasons}
    return {'pass': True, 'reasons': []}

def main():
    payload = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'alerts': [], 'summary': {'scanned': 0, 'alerts': 0}}
    ok, err = init_ftmo()
    if not ok:
        payload['error'] = str(err)
        OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps(payload, indent=2))
        return

    acct = mt5.account_info()
    payload['account'] = {'login': int(acct.login), 'equity': float(acct.equity)}

    for category, symbols in UNIVERSE.items():
        for sym in symbols:
            info = mt5.symbol_info(sym)
            if not info or not info.visible:
                continue
            rates = get_rates(sym)
            if rates is None:
                continue
            closes = [r['close'] for r in rates]
            highs = [r['high'] for r in rates]
            lows = [r['low'] for r in rates]
            current = closes[-1]
            atr = calc_atr(highs, lows, closes)
            rsi = calc_rsi(closes)
            vwap = calc_vwap(rates)
            ema20_vals = calc_ema(closes, EMA_FAST)
            ema50_vals = calc_ema(closes, EMA_SLOW)
            ema20 = ema20_vals[-1] if ema20_vals else None
            ema50 = ema50_vals[-1] if ema50_vals else None

            formations = []
            if detect_open_reversal(rates):
                formations.append('open_reversal')
            if detect_bull_breakout(rates):
                formations.append('bull_breakout')
            if detect_1pm_formation(rates):
                formations.append('1pm_formation')

            side = None
            if None not in (current, ema20, ema50, vwap):
                if current > ema20 > ema50 > vwap:
                    side = 'LONG'
                elif current < ema20 < ema50 < vwap:
                    side = 'SHORT'

            if not side:
                if 'bull_breakout' in formations or 'open_reversal' in formations:
                    side = 'LONG'
                elif '1pm_formation' in formations:
                    side = 'LONG' if current > rates[-1]['open'] else 'SHORT'

            bt = {'win_rate': 0, 'expectancy': 0, 'trades': 0}
            if side:
                bt = backtest_simple(rates, side)

            gate = tradegate(bt['win_rate'], bt['expectancy'], rsi, formations)
            payload['summary']['scanned'] += 1

            if gate['pass']:
                alert = {
                    'symbol': sym,
                    'category': category,
                    'side': side,
                    'price': round(current, 5),
                    'atr': round(atr, 5) if atr else None,
                    'rsi': round(rsi, 2) if rsi else None,
                    'formations': formations,
                    'backtest': bt,
                    'sl': round(current - 1.0 * atr, 5) if side == 'LONG' and atr else round(current + 1.0 * atr, 5) if side == 'SHORT' and atr else None,
                    'tp': round(current + 2.0 * atr, 5) if side == 'LONG' and atr else round(current - 2.0 * atr, 5) if side == 'SHORT' and atr else None,
                }
                payload['alerts'].append(alert)
                payload['summary']['alerts'] += 1

            time.sleep(0.1)

    mt5.shutdown()
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    if payload['summary']['alerts'] > 0:
        print('ALERT:', json.dumps(payload, indent=2))
    else:
        print('NO_ALERT: scanned', payload['summary']['scanned'], 'symbols, 0 high-grade setups')

if __name__ == '__main__':
    main()