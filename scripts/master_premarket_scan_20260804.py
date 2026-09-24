#!/usr/bin/env python3
"""
Master premarket scanner: ETFs, stocks, bonds, futures, rates, FX, commodities, indices.
Outputs ranked setups with VWAP, RSI, ATR, backtest, tradegate, news correlation.
"""
import json, time, os
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5
import requests

TERMINAL = r'REDACTED-PATH'
LOGIN = int(os.environ.get('FTMO_MT5_LOGIN', '0'))
PW = os.environ.get('FTMO_MT5_PASSWORD', '')
SERVER = os.environ.get('FTMO_MT5_SERVER', '')
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
OUT = BASE / 'artifacts' / f'master_premarket_scan_20260804T{datetime.now(timezone.utc).strftime("%H%M")}Z.json'

# Universe: ETFs, stocks, indices, futures proxies on MT5
UNIVERSE = {
    'indices': ['US30Cash', 'US100Cash', 'US500Cash', 'UK100Cash', 'DE40Cash', 'JP225Cash', 'AUS200Cash'],
    'forex': ['EURUSD', 'GBPUSD', 'USDJPY', 'EURJPY', 'GBPJPY', 'AUDUSD', 'NZDUSD', 'USDCHF', 'EURGBP'],
    'commodities': ['XAUUSD', 'XAGUSD', 'USOIL', 'UKOIL', 'NGAS', 'WHEAT', 'CORN'],
    'crypto': ['BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'DOGEUSD', 'DOTUSD'],
    'bonds_rates_proxies': ['US10Y', 'US30Y', 'DE10Y', 'JP10Y'],  # if available
    'etfs_proxies': ['SPY500', 'NDQ100', 'DOW30'],  # CFD proxies if available
}

# VWAP + trend filter parameters
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
    # MT5 structured array: access fields as attributes
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

def backtest_simple(rates, side, sl_mult=1.0, tp_mult=2.0):
    """Simple ATR-based backtest."""
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

def tradegate(win_rate, expectancy, rsi, price, ema20, ema50, vwap):
    reasons = []
    if win_rate < 0.45:
        reasons.append('win_rate_low')
    if expectancy <= 0:
        reasons.append('expectancy_negative')
    if rsi is not None and 40 <= rsi <= 60:
        reasons.append('rsi_neutral')
    # VWAP + trend filter
    trend = 'NONE'
    if None not in (price, ema20, ema50, vwap):
        if price > ema20 > ema50 > vwap:
            trend = 'LONG'
        elif price < ema20 < ema50 < vwap:
            trend = 'SHORT'
        else:
            reasons.append('no_trend_alignment')
    else:
        reasons.append('missing_indicator')
    if reasons:
        return {'pass': False, 'reasons': reasons, 'trend': trend}
    return {'pass': True, 'reasons': [], 'trend': trend}

def main():
    payload = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'universe': {}, 'summary': {'total': 0, 'candidates': 0, 'high_grade': 0}}
    ok, err = init_ftmo()
    if not ok:
        payload['error'] = str(err)
        OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps(payload, indent=2))
        return

    acct = mt5.account_info()
    payload['account'] = {'login': int(acct.login), 'equity': float(acct.equity), 'balance': float(acct.balance)}

    for category, symbols in UNIVERSE.items():
        payload['universe'][category] = []
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

            # Determine side from trend filter
            side = None
            if None not in (current, ema20, ema50, vwap):
                if current > ema20 > ema50 > vwap:
                    side = 'LONG'
                elif current < ema20 < ema50 < vwap:
                    side = 'SHORT'

            # Backtest
            bt = {'win_rate': 0, 'expectancy': 0, 'trades': 0}
            if side:
                bt = backtest_simple(rates, side)

            # Tradegate
            gate = tradegate(bt['win_rate'], bt['expectancy'], rsi, current, ema20, ema50, vwap)
            payload['summary']['total'] += 1
            if side:
                payload['summary']['candidates'] += 1
            if gate['pass']:
                payload['summary']['high_grade'] += 1

            payload['universe'][category].append({
                'symbol': sym,
                'price': round(current, 5),
                'atr': round(atr, 5) if atr else None,
                'rsi': round(rsi, 2) if rsi else None,
                'vwap': round(vwap, 5) if vwap else None,
                'ema20': round(ema20, 5) if ema20 else None,
                'ema50': round(ema50, 5) if ema50 else None,
                'side': side,
                'backtest': bt,
                'tradegate': gate,
                'sl_long': round(current - 1.0 * atr, 5) if side == 'LONG' and atr else None,
                'tp_long': round(current + 2.0 * atr, 5) if side == 'LONG' and atr else None,
                'sl_short': round(current + 1.0 * atr, 5) if side == 'SHORT' and atr else None,
                'tp_short': round(current - 2.0 * atr, 5) if side == 'SHORT' and atr else None,
            })
            time.sleep(0.1)

    mt5.shutdown()
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print('WROTE', OUT)
    print(json.dumps(payload['summary'], indent=2))

if __name__ == '__main__':
    main()