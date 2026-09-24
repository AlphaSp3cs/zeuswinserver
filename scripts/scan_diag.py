"""Diagnostic: print RSI14, SMA50, regime for every open-class symbol so we
can see WHY 0 signals fired and what's near a trigger. Read-only."""
import MetaTrader5 as mt5
mt5.initialize(timeout=15000)
UNIVERSE = {
 'indices':['US30','US500','US100','DE40','UK100'],
 'crypto':['BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD'],
 'forex':['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF'],
 'commodities':['XAUUSD','XAGUSD','WTI','BRENT','XPTUSD','XPDUSD'],
}
rows=[]
for cls,syms in UNIVERSE.items():
    for s in syms:
        info=mt5.symbol_info(s)
        if not info: continue
        r=mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_D1,0,60)
        if r is None or len(r)<50: continue
        c=[x['close'] for x in r]; n=len(c)
        g=[max(c[i]-c[i-1],0) for i in range(1,n)]; l=[max(c[i-1]-c[i],0) for i in range(1,n)]
        ag=sum(g[:14])/14; al=sum(l[:14])/14; rsi=100-(100/(1+(ag/al if al>0 else 999)))
        for i in range(15,n):
            ag=(ag*13+g[i-1])/14; al=(al*13+l[i-1])/14; rsi=100-(100/(1+(ag/al if al>0 else 999)))
        sma50=sum(c[-50:])/50; last=c[-1]
        reg='ABOVE' if last>sma50 else 'BELOW'
        near=''
        if rsi<35 and last>sma50: near='BUY-SIGNAL'
        elif rsi>68 and last<sma50: near='SELL-SIGNAL'
        elif rsi<35: near='oversold-but-BELOW-SMA50(blocked)'
        elif rsi>68: near='overbought-but-ABOVE-SMA50(blocked)'
        rows.append((cls,s,round(rsi,1),round(last,4),round(sma50,4),reg,near))
mt5.shutdown()
print(f"{'CLASS':11}{'SYM':9}{'RSI':>6}{'LAST':>12}{'SMA50':>12}  REGIME  NOTE")
print("-"*80)
for cls,s,rsi,last,sma50,reg,near in rows:
    print(f"{cls:11}{s:9}{rsi:>6}{last:>12}{sma50:>12}  {reg:6}  {near}")
print("-"*80)
buys=[r for r in rows if r[6]=='BUY-SIGNAL']; sells=[r for r in rows if r[6]=='SELL-SIGNAL']
obs=[r for r in rows if 'oversold' in (r[6] or '')]; oba=[r for r in rows if 'overbought' in (r[6] or '')]
print(f"Clean signals: {len(buys)} buy / {len(sells)} sell")
print(f"Blocked-by-regime: {len(obs)} oversold-below-SMA50, {len(oba)} overbought-above-SMA50")
