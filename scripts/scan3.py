from alpaca_trade_api import REST
import pandas as pd, numpy as np, json, time
api=REST('PKKFBUIB2ME4QEL4DC552CASYM','B7UzBja7QK3sZGB1H6pWyviNPCyJed6TBfMSxfZ3Wivb','https://paper-api.alpaca.markets', api_version='v2')
symbols=['BTC/USD','ETH/USD','SOL/USD','RENDER/USD','GRT/USD','FIL/USD','LINK/USD','DOGE/USD']
results={}
for sym in symbols:
    try:
        bars=api.get_crypto_bars(sym,'5Min',limit=50).df
        if bars is None or len(bars)<30:
            results[sym]={'error':'insufficient data ('+str(len(bars))+')'}
            continue
        close=bars['c']; high=bars['h']; low=bars['l']; vol=bars['v']
        # RSI 14
        delta=close.diff(); gain=delta.where(delta>0,0).rolling(14).mean(); loss=-delta.where(delta<0,0).rolling(14).mean()
        rs=gain/loss.replace(0,1e-9); rsi=100-(100/(1+rs))
        curr_rsi=float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
        # MACD
        ema12=close.ewm(span=12,adjust=False).mean(); ema26=close.ewm(span=26,adjust=False).mean()
        macd=ema12-ema26; signal=macd.ewm(span=9,adjust=False).mean(); hist=macd-signal
        bull_macd=bool(hist.iloc[-1]>hist.iloc[-2])
        # SMA20 vs EMA20
        sma20=close.rolling(20).mean(); ema20=close.ewm(span=20,adjust=False).mean()
        bull_trend=bool(close.iloc[-1]>sma20.iloc[-1] and ema20.iloc[-1]>sma20.iloc[-1])
        # Bollinger Band
        bb_sma=close.rolling(20).mean(); bb_std=close.rolling(20).std()
        upper=bb_sma+2*bb_std; lower=bb_sma-2*bb_std
        bull_bb=bool(close.iloc[-1]<lower.iloc[-1])
        # Volume ratio
        avg_vol=vol.rolling(20).mean()
        vol_ratio=float(vol.iloc[-1]/avg_vol.iloc[-1]) if avg_vol.iloc[-1]!=0 else 0.0
        bull_vol=bool(vol_ratio>1.5)
        score=sum([curr_rsi>55, bull_macd, bull_trend, bull_bb, bull_vol])
        results[sym]={'score':score,'price':float(close.iloc[-1]), 'rsi':round(float(curr_rsi),1), 'macd':bull_macd, 'trend':bull_trend, 'bb':bull_bb, 'vol_ratio':round(vol_ratio,2)}
    except Exception as e:
        results[sym]={'error':str(e)}
    time.sleep(0.2)
print(json.dumps(results, indent=2))
