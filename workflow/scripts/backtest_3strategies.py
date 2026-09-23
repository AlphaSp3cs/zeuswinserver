"""Backtest: RSI 2-Day Mean Reversion, 80% Win Rate Combo, QScalper CCI/SMA
Fixed pandas alignment + yfinance multi-column issues.
"""
import yfinance as yf
import pandas as pd
import numpy as np

# ─── INDICATORS ───
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta).clip(lower=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def macd_line(series, fast=12, slow=26, signal=9):
    ema_f = series.ewm(span=fast).mean()
    ema_s = series.ewm(span=slow).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=signal).mean()
    return macd, sig

def cci(high, low, close, period=20):
    tp = (high + low + close) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.fabs(x - x.mean()).mean(), raw=True)
    return (tp - sma) / (0.015 * mad)

def bbands(series, period=20, std=2):
    mid = series.rolling(period).mean()
    sigma = series.rolling(period).std()
    return mid - std * sigma, mid, mid + std * sigma

# ─── STRATEGIES ───
def strat_rsi2(df):
    df = df.copy()
    df['rsi2'] = rsi(df['Close'], 2)
    df['signal'] = 0
    df.loc[df['rsi2'] < 15, 'signal'] = 1
    df.loc[df['rsi2'] > 85, 'signal'] = -1
    return df

def strat_combo(df):
    df = df.copy()
    df['rsi14'] = rsi(df['Close'], 14)
    macd, sig = macd_line(df['Close'])
    df['macd'] = macd
    df['macd_sig'] = sig
    lo, mid, hi = bbands(df['Close'])
    df['bb_lo'] = lo
    df['bb_hi'] = hi
    df['ema50'] = df['Close'].ewm(span=50).mean()
    df['signal'] = 0
    buy = (df['rsi14'] < 30) & (df['Close'] < df['bb_lo']) & (df['macd'] > df['macd_sig']) & (df['Close'] > df['ema50'])
    sell = (df['rsi14'] > 70) & (df['Close'] > df['bb_hi']) & (df['macd'] < df['macd_sig']) & (df['Close'] < df['ema50'])
    df.loc[buy, 'signal'] = 1
    df.loc[sell, 'signal'] = -1
    return df

def strat_qscalper(df):
    df = df.copy()
    df['cci'] = cci(df['High'], df['Low'], df['Close'])
    df['sma50'] = df['Close'].ewm(span=50).mean()
    df['signal'] = 0
    df.loc[(df['cci'] < -100) & (df['Close'] > df['sma50']), 'signal'] = 1
    df.loc[(df['cci'] > 100) & (df['Close'] < df['sma50']), 'signal'] = -1
    return df

# ─── BACKTEST ENGINE ───
def backtest(df, strategy_fn):
    df = strategy_fn(df)
    df = df.dropna(subset=['signal', 'atr'])
    
    trades = []
    pos = None
    entry_idx = None
    entry_price = 0
    
    for i in range(len(df)):
        row = df.iloc[i]
        sig = row['signal']
        
        if pos is None and sig != 0:
            pos = int(sig)
            entry_idx = i
            entry_price = float(row['Close'])
            atr_val = float(row['atr'])
            if atr_val <= 0:
                pos = None
                continue
        
        elif pos is not None and i > entry_idx:
            current = float(row['Close'])
            high_h = float(df['High'].iloc[entry_idx:i+1].max())
            low_l = float(df['Low'].iloc[entry_idx:i+1].min())
            atr_val = float(row['atr'])
            if atr_val <= 0:
                continue
            
            sl = entry_price - pos * 1.5 * atr_val if pos > 0 else entry_price + pos * 1.5 * atr_val
            tp = entry_price + pos * 3.0 * atr_val if pos > 0 else entry_price - pos * 3.0 * atr_val
            
            hit_sl = (pos > 0 and low_l <= sl) or (pos < 0 and high_h >= sl)
            hit_tp = (pos > 0 and high_h >= tp) or (pos < 0 and low_l <= tp)
            
            if hit_sl or hit_tp:
                exit_price = sl if hit_sl else tp
                ret = (exit_price - entry_price) / entry_price * pos
                trades.append({'won': ret > 0, 'ret': ret})
                pos = None
                entry_idx = None
    
    if len(trades) < 5:
        return {'wr': 0, 'pf': 0, 'trades': len(trades), 'total_ret': 0, 'max_dd': 0,
                'avg_win': 0, 'avg_loss': 0}
    
    wins = [t for t in trades if t['won']]
    losses = [t for t in trades if not t['won']]
    gw = sum(t['ret'] for t in wins)
    gl = sum(abs(t['ret']) for t in losses)
    pf = gw / gl if gl > 0 else 999
    
    equity = pd.Series([t['ret'] for t in trades]).cumsum()
    peak = equity.expanding().max()
    dd = (equity - peak).min()
    
    return {
        'wr': len(wins) / len(trades) * 100,
        'pf': pf,
        'trades': len(trades),
        'total_ret': equity.iloc[-1] * 100,
        'max_dd': dd * 100,
        'avg_win': np.mean([t['ret'] for t in wins]) * 100 if wins else 0,
        'avg_loss': np.mean([t['ret'] for t in losses]) * 100 if losses else 0,
    }

# ─── MAIN ───
print("=" * 70)
print("BACKTEST: 3 NEW STRATEGIES vs EXISTING STACK")
print("=" * 70)

assets = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'EURUSD=X', 'GBPUSD=X', 'USDJPY=X']
strategies = [('RSI2 MR', strat_rsi2), ('Combo 80%', strat_combo), ('QScalper', strat_qscalper)]

print("\n📥 Fetching data...")
data = {}
for sym in assets:
    try:
        raw = yf.download(sym, period='2y', interval='1d', progress=False)
        if raw.empty:
            continue
        # Flatten multi-level columns from yfinance
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.dropna(subset=['Close', 'High', 'Low'])
        raw['atr'] = atr(raw['High'], raw['Low'], raw['Close'])
        data[sym] = raw
        print(f"  {sym}: {len(raw)} bars ✓")
    except Exception as e:
        print(f"  {sym}: error {e}")

print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)

all_results = {}
for sym in data:
    for name, fn in strategies:
        try:
            r = backtest(data[sym], fn)
            key = f"{sym} | {name}"
            all_results[key] = r
            badge = "✅" if r['wr'] >= 70 and r['pf'] >= 1.5 else "⚠️" if r['wr'] >= 55 else "❌"
            print(f"  {badge} {key}: WR {r['wr']:.1f}% PF {r['pf']:.2f} N={r['trades']} Ret {r['total_ret']:.1f}% DD {r['max_dd']:.1f}%")
        except Exception as e:
            print(f"  ❌ {sym} | {name}: {str(e)[:60]}")

# Ranking
print("\n" + "=" * 70)
print("RANKING (by WR × PF)")
print("=" * 70)

valid = {k: v for k, v in all_results.items() if v['trades'] >= 5 and v['wr'] > 0}
ranked = sorted(valid.items(), key=lambda x: x[1]['wr'] * x[1]['pf'], reverse=True)

for i, (key, r) in enumerate(ranked[:15], 1):
    print(f"  {i}. {key} — WR {r['wr']:.1f}% PF {r['pf']:.2f} N={r['trades']}")

# Best per asset
print("\n" + "=" * 70)
print("BEST STRATEGY PER ASSET")
print("=" * 70)
for sym in data:
    asset_results = [(k, v) for k, v in valid.items() if k.startswith(sym)]
    if asset_results:
        best = max(asset_results, key=lambda x: x[1]['wr'] * x[1]['pf'])
        print(f"  {sym}: {best[0]} — WR {best[1]['wr']:.1f}% PF {best[1]['pf']:.2f}")

# Compare to existing stack
print("\n" + "=" * 70)
print("EXISTING STACK vs NEW STRATEGIES")
print("=" * 70)
print("  ATR_EXPANSION:  WR 51.2%  PF 1.9   622 trades")
print("  BB Breakout:    WR 57-59% PF 6.2  BTC/ETH overlay")
print("  RSI Divergence: WR 75.4%  PF N/A  CHAMPION")
print("  Momentum+ATR:   XRP/DOT/LTC overlay")
print()
print("  NEW - RSI2 MR:    Mean reversion overlay for RSI extremes")
print("  NEW - Combo 80%:  Multi-indicator (BB+MACD+RSI+EMA+ADX)")
print("  NEW - QScalper:   CCI/SMA trend scalping")
print()
print("✅ Backtest complete")
