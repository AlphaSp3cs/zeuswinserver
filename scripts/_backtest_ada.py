import os, sys, json
from datetime import datetime, timezone
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

FTMO_PATH = r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"
mt5.shutdown()
mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
tick = mt5.symbol_info_tick("ADAUSD")
rates = mt5.copy_rates_from_pos("ADAUSD", mt5.TIMEFRAME_H1, 0, 720)
mt5.shutdown()
if tick is None or rates is None or len(rates) < 60:
    print(json.dumps({"error": "insufficient_data", "tick": bool(tick), "bars": 0 if rates is None else len(rates)}))
    sys.exit(0)
df = pd.DataFrame(rates)
for col in ['close','high','low']:
    df[col] = pd.to_numeric(df[col], errors='coerce')
price = float(tick.bid)
ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
atr14 = float((df['high'] - df['low']).rolling(14).mean().iloc[-1])
bullish = bool(price > ema20 > ema50)
bearish = bool(price < ema20 < ema50)
trend = "BULLISH" if bullish else "BEARISH" if bearish else "RANGE"
# backtest long first touch TP/SL from historical bars
closes = df['close'].values
highs = df['high'].values
lows = df['low'].values
wins = losses = 0
for i in range(50, len(closes)-10):
    entry = closes[i]
    sl = entry - 1.5*float((df['high'] - df['low']).rolling(14).mean().iloc[i])
    tp = entry + 3.0*float((df['high'] - df['low']).rolling(14).mean().iloc[i])
    future_high = max(highs[i+1:i+11])
    future_low = min(lows[i+1:i+11])
    if future_high >= tp:
        wins += 1
    elif future_low <= sl:
        losses += 1
total = wins + losses
back = {"bars": int(total), "win_rate": round(wins/total, 3) if total else None, "wins": int(wins), "losses": int(losses)}
decision = "CLOSE" if (back.get('win_rate') is not None and back['win_rate'] < 0.40) or trend == "BEARISH" else "HOLD"
print(json.dumps({
    "symbol": "ADAUSD",
    "price": round(price, 6),
    "ema20": round(ema20, 6),
    "ema50": round(ema50, 6),
    "atr14": round(atr14, 6),
    "trend": trend,
    "backtest_30d": back,
    "close_decision": decision
}, indent=2))
