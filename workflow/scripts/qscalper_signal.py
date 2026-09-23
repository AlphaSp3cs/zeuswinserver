"""QScalper CCI/SMA Signal Module — OuroTaurus integration.
BUY:  CCI < -100 AND price > SMA50 (oversold bounce in uptrend)
SELL: CCI > 100 AND price < SMA50 (overbought rally in downtrend)
SL 1.5 ATR / TP 3 ATR (3:1 RR)

Checks H4 then D1 fallback. Integrates with conviction_feed.py.
"""
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

def calc_cci(high, low, close, period=20):
    if isinstance(high, np.ndarray):
        high = pd.Series(high)
        low = pd.Series(low)
        close = pd.Series(close)
    tp = (high + low + close) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.fabs(x - x.mean()).mean(), raw=True)
    return (tp - sma) / (0.015 * mad)

def score_qscalper(sym, tf=mt5.TIMEFRAME_H4):
    """Score QScalper setup. Returns dict or None."""
    rates = mt5.copy_rates_from_pos(sym, tf, 0, 100)
    if rates is None or len(rates) < 50:
        return None
    
    df = pd.DataFrame(rates)
    df['cci'] = calc_cci(df['high'].values, df['low'].values, df['close'].values)
    df['sma50'] = df['close'].ewm(span=50).mean()
    
    # ATR from rates
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    last = df.iloc[-1]
    cci_val = float(last['cci'])
    sma50 = float(last['sma50'])
    price = float(last['close'])
    atr_val = float(last['atr'])
    
    if atr_val <= 0:
        return None
    
    # Direction logic
    if cci_val < -100 and price > sma50:
        direction = 'BUY'
        edge = (abs(cci_val) - 100) / 50 + (price - sma50) / sma50 * 100
        score = min(10, max(0, edge))
        sl = price - 1.5 * atr_val
        tp = price + 3.0 * atr_val
    elif cci_val > 100 and price < sma50:
        direction = 'SELL'
        edge = (cci_val - 100) / 50 + (sma50 - price) / sma50 * 100
        score = min(10, max(0, edge))
        sl = price + 1.5 * atr_val
        tp = price - 3.0 * atr_val
    else:
        return None
    
    # Spread check
    tick = mt5.symbol_info_tick(sym)
    spread = (tick.ask - tick.bid) / tick.bid * 100 if tick and tick.ask > 0 else 999
    if spread > 0.5:
        return None
    
    return {
        'symbol': sym,
        'strategy': 'QScalper',
        'direction': direction,
        'score': round(score, 1),
        'price': round(price, 5),
        'sl': round(sl, 5),
        'tp': round(tp, 5),
        'cci': round(cci_val, 1),
        'sma50': round(sma50, 5),
        'atr': round(atr_val, 5),
        'spread': round(spread, 3),
        'tf': 'H4' if tf == mt5.TIMEFRAME_H4 else 'D1',
    }

def scan_qscalper(assets):
    """Scan all assets. Returns list of signals."""
    signals = []
    for sym in assets:
        r = score_qscalper(sym, mt5.TIMEFRAME_H4)
        if r is None:
            r = score_qscalper(sym, mt5.TIMEFRAME_D1)
        if r and r['score'] >= 4:
            signals.append(r)
    return signals

if __name__ == '__main__':
    mt5.initialize(r'C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe')
    assets = ['BTCUSD', 'ETHUSD', 'XRPUSD', 'EURUSD', 'GBPUSD', 'USDJPY',
              'SOLUSD', 'ADAUSD', 'DOTUSD', 'LTCUSD', 'AUDUSD', 'NZDUSD']
    sigs = scan_qscalper(assets)
    if sigs:
        for s in sorted(sigs, key=lambda x: x['score'], reverse=True):
            print(f"  {s['symbol']}: {s['direction']} score={s['score']} CCI={s['cci']} "
                  f"price={s['price']} SL={s['sl']} TP={s['tp']} TF={s['tf']}")
    else:
        print("  No QScalper signals active (strong trend — no pullbacks)")
    mt5.shutdown()