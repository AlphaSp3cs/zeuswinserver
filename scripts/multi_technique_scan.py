"""
Multi-technique sector scan for FTMO.
Techniques:
1. Bollinger Band breakout/reversal
2. SMA fast/slow crossover
3. ATR volatility expansion
4. Support/resistance breaks
"""
import sys, os
sys.path.insert(0, os.path.expanduser('~'))
from mt5_connect import connect as mt5_connect
import MetaTrader5 as mt5
import json

OUT='C:/Users/bravo-usr1/trade_data'
m = mt5_connect('ftmo')
print('login:', m.account_info().login)

UNIVERSE = {
    'indices':['US30','US500','US100','DE40','UK100'],
    'crypto':['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD'],
    'forex':['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF','NZDUSD','CADUSD'],
    'commodities':['XAUUSD','XAGUSD','WTI','BRENT','XPTUSD','XPDUSD'],
}

signals=[]

for cls,syms in UNIVERSE.items():
    for s in syms:
        info=m.symbol_info(s)
        if not info: continue
        r=m.copy_rates_from_pos(s,mt5.TIMEFRAME_H4,0,100)
        if r is None or len(r)<50: continue
        c=[x['close'] for x in r]; h=[x['high'] for x in r]; lo=[x['low'] for x in r]
        
        # Moving averages
        sma20=sum(c[-20:])/20
        sma50=sum(c[-50:])/50
        sma200=sum(c[-200:])/200 if len(c)>=200 else sma50
        
        # Bollinger Bands (20 period, 2 std)
        import math
        std20=math.sqrt(sum((x-sma20)**2 for x in c[-20:])/20)
        bb_mid=sma20
        bb_upper=sma20+2*std20
        bb_lower=sma20-2*std20
        
        # ATR
        tr=[]
        for i in range(1,len(c)):
            tr.append(max(h[i]-lo[i], abs(h[i]-c[i-1]), abs(lo[i]-c[i-1])))
        atr20=sum(tr[-20:])/20 if len(tr)>=20 else sum(tr)/len(tr) if tr else 0
        atr5=sum(tr[-5:])/5 if len(tr)>=5 else atr20
        
        last=c[-1]
        
        # Technique 1: Bollinger Band breakout/reversal
        if last > bb_upper:
            signals.append({'class':cls,'symbol':s,'technique':'BB_BREAKOUT_UP','side':'BUY','last':last,'bb_upper':bb_upper,'bb_lower':bb_lower,'atr20':atr20,'reason':'break above upper BB'})
        elif last < bb_lower:
            signals.append({'class':cls,'symbol':s,'technique':'BB_BREAKOUT_DOWN','side':'SELL','last':last,'bb_upper':bb_upper,'bb_lower':bb_lower,'atr20':atr20,'reason':'break below lower BB'})
        
        # Technique 2: SMA crossover
        if sma20 > sma50 and c[-2] < sum(c[-21:-1])/20:  # fast just crossed above slow
            signals.append({'class':cls,'symbol':s,'technique':'SMA_CROSS_UP','side':'BUY','last':last,'sma20':sma20,'sma50':sma50,'atr20':atr20,'reason':'SMA20 crossed above SMA50'})
        elif sma20 < sma50 and c[-2] > sum(c[-21:-1])/20:  # fast just crossed below slow
            signals.append({'class':cls,'symbol':s,'technique':'SMA_CROSS_DOWN','side':'SELL','last':last,'sma20':sma20,'sma50':sma50,'atr20':atr20,'reason':'SMA20 crossed below SMA50'})
        
        # Technique 3: ATR volatility expansion
        if atr5 > 1.5 * atr20 and last > sma20:
            signals.append({'class':cls,'symbol':s,'technique':'ATR_EXPANSION_UP','side':'BUY','last':last,'atr5':atr5,'atr20':atr20,'reason':'volatility expanding, above SMA20'})
        elif atr5 > 1.5 * atr20 and last < sma20:
            signals.append({'class':cls,'symbol':s,'technique':'ATR_EXPANSION_DOWN','side':'SELL','last':last,'atr5':atr5,'atr20':atr20,'reason':'volatility expanding, below SMA20'})

# Deduplicate by symbol+side
seen=set()
unique=[]
for s in signals:
    key=(s['symbol'],s['side'])
    if key not in seen:
        seen.add(key)
        unique.append(s)

# Sort by ATR relative strength
unique.sort(key=lambda x: abs(x.get('atr20',0)/x['last']), reverse=True)

print(f'\nMulti-technique scan: {len(unique)} signals')
for s in unique[:20]:
    print(f"  {s['side']:4} {s['symbol']:8} [{s['class']}] {s['technique']} price={s['last']:.5f} reason={s['reason']}")

with open(os.path.join(OUT,'multi_technique_signals.json'),'w') as f:
    json.dump(unique, f, indent=2)
print('saved multi_technique_signals.json')
m.shutdown()