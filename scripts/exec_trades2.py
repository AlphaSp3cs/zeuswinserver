"""
Execute missing setups from relaxed scan on FTMO.
No duplicates with existing tickets.
"""
import sys, os
sys.path.insert(0, os.path.expanduser('~'))
from mt5_connect import connect as mt5_connect
import MetaTrader5 as mt5

TRADES = [
    {'symbol':'ETHUSD','side':'SELL','sl':2039.38,'tp':1653.05},
    {'symbol':'USDJPY','side':'SELL','sl':164.013,'tp':159.469},
    {'symbol':'USDCHF','side':'SELL','sl':0.82119,'tp':0.78882},
    {'symbol':'BTCUSD','side':'SELL','sl':68349.71,'tp':59203.80},
    {'symbol':'XAUUSD','side':'BUY','sl':3867.55,'tp':4373.57},
    {'symbol':'EURUSD','side':'BUY','sl':1.13144,'tp':1.16136},
    {'symbol':'GBPUSD','side':'BUY','sl':1.31283,'tp':1.35893},
]

def lot_size(symbol, entry, sl, risk_usd):
    info = mt5.symbol_info(symbol)
    if not info:
        raise RuntimeError(f"{symbol}: no symbol_info")
    sl_dist_pts = abs(entry - sl) / info.point
    risk_per_pt = info.trade_tick_value / info.trade_tick_size if info.trade_tick_size else 0
    if risk_per_pt <= 0 or sl_dist_pts <= 0:
        raise RuntimeError(f"{symbol}: bad sizing params")
    vol = risk_usd / (sl_dist_pts * risk_per_pt)
    vol = max(info.volume_min, min(info.volume_max, vol))
    vol = round(vol, 2 if info.volume_step >= 0.01 else 1)
    print(f"  {symbol}: risk_pts={sl_dist_pts:.1f} risk_per_pt={risk_per_pt:.4f} raw_vol={risk_usd/(sl_dist_pts*risk_per_pt):.4f} final_vol={vol}")
    return vol

def place(symbol, side, sl, tp, vol):
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        raise RuntimeError(f"{symbol}: no tick")
    price = tick.ask if side=='BUY' else tick.bid
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": vol,
        "type": mt5.ORDER_TYPE_BUY if side=='BUY' else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 20260720,
        "comment": "OUS_FTMO_RSI_45",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    print(f"  Sending {side} {symbol} vol={vol} price={price} SL={sl} TP={tp}")
    res = mt5.order_send(req)
    print(f"  -> retcode={res.retcode} comment={res.comment} ticket={res.order} deal={res.deal}")
    return res

def main():
    m = mt5_connect('ftmo')
    info = m.account_info()
    equity = info.equity
    risk = equity * 0.01
    print(f"FTMO {info.login}: equity={equity} risk={risk:.2f}")
    print("=== EXECUTING 7 MISSING SETUPS ===")
    results=[]
    for t in TRADES:
        symbol=t['symbol']; side=t['side']; sl=t['sl']; tp=t['tp']
        print(f"\n[{symbol}] {side} SL={sl} TP={tp}")
        try:
            tick = m.symbol_info_tick(symbol)
            price = tick.ask if side=='BUY' else tick.bid
            vol = lot_size(symbol, price, sl, risk)
            res = place(symbol, side, sl, tp, vol)
            results.append({'symbol':symbol,'retcode':res.retcode,'deal':res.deal,'order':res.order,'volume':vol,'profit':0})
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({'symbol':symbol,'error':str(e)})
    print("\n=== SUMMARY ===")
    ok=0; fail=0
    for r in results:
        if 'deal' in r and r['deal']:
            print(f"  {r['symbol']}: ticket={r['order']} vol={r['volume']}")
            ok+=1
        else:
            print(f"  {r['symbol']}: ERROR={r.get('error',r.get('comment'))}")
            fail+=1
    print(f"\nok={ok} fail={fail}")
    m.shutdown()

if __name__ == '__main__':
    main()