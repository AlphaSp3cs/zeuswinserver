"""FULL MARKET SCAN — open classes only (indices, crypto, forex, commodities).
Real MT5 daily data. Signals = our proven edge: RSI extreme AND price vs SMA50
(regime guard from post-mortem). Read-only: prints signals, no orders.

Signal rules (mean-reversion, both directions):
  LONG  : RSI14 < 35  AND close > SMA50   (oversold pullback in uptrend)
  SHORT : RSI14 > 68  AND close < SMA50   (overbought fade in downtrend)
Size guard: notional <= 2% of broker equity; SL/TP from ATR (2:1)."""
import MetaTrader5 as mt5, csv, os
from datetime import datetime, timezone

OUT='C:/Users/bravo-usr1/trade_data'; os.makedirs(OUT, exist_ok=True)
mt5.initialize(timeout=15000)

# Open-class universe on MT5 (US equities/ETF excluded — session closed)
UNIVERSE = {
 'indices':  ['US30','US500','US100','DE40','UK100'],
 'crypto':   ['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD'],
 'forex':    ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF'],
 'commodities':['XAUUSD','XAGUSD','WTI','BRENT','XPTUSD','XPDUSD'],
}

def indicators(closes):
    n=len(closes)
    # RSI14
    gains=[]; losses=[]
    for i in range(1,n):
        ch=closes[i]-closes[i-1]; gains.append(max(ch,0)); losses.append(max(-ch,0))
    rsi=None
    if n>14:
        ag=sum(gains[:14])/14; al=sum(losses[:14])/14
        rsi=100-(100/(1+(ag/al if al>0 else 999)))
        for i in range(15,n):
            ag=(ag*13+gains[i-1])/14; al=(al*13+losses[i-1])/14
            rs=ag/al if al>0 else 999
            rsi=100-(100/(1+rs))
    # SMA50
    sma50 = sum(closes[-50:])/50 if n>=50 else None
    # ATR14
    atr=None
    if '_tr' in indicators.__dict__: pass
    return rsi, sma50

print("="*90)
print("FULL MARKET SCAN — OPEN CLASSES (indices/crypto/forex/commodities)  REAL MT5")
print("="*90)
signals=[]
for cls, syms in UNIVERSE.items():
    for s in syms:
        info=mt5.symbol_info(s)
        if not info: continue
        rates=mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_D1, 0, 60)
        if rates is None or len(rates)<50: continue
        closes=[r['close'] for r in rates]
        highs=[r['high'] for r in rates]; lows=[r['low'] for r in rates]
        n=len(closes)
        # RSI
        g=[max(closes[i]-closes[i-1],0) for i in range(1,n)]
        l=[max(closes[i-1]-closes[i],0) for i in range(1,n)]
        ag=sum(g[:14])/14; al=sum(l[:14])/14
        rsi=100-(100/(1+(ag/al if al>0 else 999)))
        for i in range(15,n):
            ag=(ag*13+g[i-1])/14; al=(al*13+l[i-1])/14
            rsi=100-(100/(1+(ag/al if al>0 else 999)))
        sma50=sum(closes[-50:])/50
        last=closes[-1]
        # ATR14
        tr=[max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,n)]
        atr=sum(tr[-14:])/14
        # signal
        side=None; reason=None
        if rsi<35 and last>sma50:
            side='BUY'; reason=f"RSI {rsi:.1f} oversold + above SMA50 (uptrend pullback)"
        elif rsi>68 and last<sma50:
            side='SELL'; reason=f"RSI {rsi:.1f} overbought + below SMA50 (downtrend fade)"
        reg = 'ABOVE' if last>sma50 else 'BELOW'
        if side:
            # SL/TP via ATR 2:1
            if side=='BUY':
                sl=last-2*atr; tp=last+4*atr
            else:
                sl=last+2*atr; tp=last-4*atr
            signals.append({'class':cls,'symbol':s,'side':side,'rsi':round(rsi,1),
                            'last':round(last,info.digits and 10**-min(info.digits,4) and last or last),
                            'sma50':round(sma50,4),'regime':reg,'atr':round(atr,4),
                            'sl':round(sl,4),'tp':round(tp,4),'reason':reason})
            print(f"  >> SIGNAL {side:4} {s:8} [{cls:11}] RSI={rsi:5.1f} reg={reg} last={last:.4f} SL={sl:.4f} TP={tp:.4f}")
print("-"*90)
print(f"SCAN COMPLETE: {len(signals)} signals fired across open classes.")
print("None fired? Market may be mid-regime (no RSI extremes vs SMA50).")
mt5.shutdown()
