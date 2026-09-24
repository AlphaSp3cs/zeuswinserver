"""
Execute specific BUY setups on FTMO terminal with hard SL+TP, 1% risk.
"""
import sys, os
sys.path.insert(0, os.path.expanduser('~'))
from mt5_connect import connect as mt5_connect
import MetaTrader5 as mt5

# Exact setups from relaxed scan
TRADES = [
    {'symbol':'XAGUSD','side':'BUY','sl':52.055,'tp':66.416},
    {'symbol':'DOTUSD','side':'BUY','sl':0.759,'tp':0.963},
    {'symbol':'XPTUSD','side':'BUY','sl':1475.27,'tp':1812.26},
]

def lot_size(symbol, entry, sl, risk_usd):
    info = mt5.symbol_info(symbol)
    if not info:
        raise RuntimeError(f"{symbol}: no symbol_info")
    print(f"  {symbol} digits={info.digits} point={info.point} trade_tick_value={info.trade_tick_value} trade_tick_size={info.trade_tick_size}")
    # SL distance in points
    sl_dist_pts = abs(entry - sl) / info.point
    # risk per point per lot = tick_value / tick_size
    risk_per_pt = info.trade_tick_value / info.trade_tick_size if info.trade_tick_size else 0
    if risk_per_pt <= 0 or sl_dist_pts <= 0:
        raise RuntimeError(f"{symbol}: bad sizing params")
    vol = risk_usd / (sl_dist_pts * risk_per_pt)
    # clamp to min/max lot, round to 2 decimals
    vol = max(info.volume_min, min(info.volume_max, vol))
    vol = round(vol, 2 if info.volume_step >= 0.01 else 1)
    print(f"  -> risk_pts={sl_dist_pts:.1f} risk_per_pt={risk_per_pt:.4f} raw_vol={risk_usd/(sl_dist_pts*risk_per_pt):.4f} final_vol={vol}")
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
    print(f"FTMO account {info.login}: balance={info.balance} equity={equity} risk={risk:.2f}")
    print("=== EXECUTING 3 BUY setups ===")
    results=[]
    for t in TRADES:
        symbol=t['symbol']; side=t['side']; sl=t['sl']; tp=t['tp']
        print(f"\n[{symbol}] {side} SL={sl} TP={tp}")
        try:
            vol = lot_size(symbol, mt5.symbol_info_tick(symbol).ask if side=='BUY' else mt5.symbol_info_tick(symbol).bid, sl, risk)
            res = place(symbol, side, sl, tp, vol)
            results.append({'symbol':symbol,'retcode':res.retcode,'deal':res.deal,'order':res.order,'volume':vol,'comment':res.comment})
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({'symbol':symbol,'error':str(e)})
    print("\n=== SUMMARY ===")
    for r in results:
        if 'deal' in r:
            print(f"  {r['symbol']}: ticket={r['order']} deal={r['deal']} vol={r['volume']}")
        else:
            print(f"  {r['symbol']}: ERROR={r['error']}")
    # verify positions
    print("\n=== LIVE POSITIONS ===")
    positions = m.positions_get()
    if positions is None:
        print("  no positions")
    else:
        for p in positions:
            if p.magic == 20260720:
                print(f"  {p.symbol} {p.type} vol={p.volume} price={p.price_open} sl={p.sl} tp={p.tp} profit={p.profit}")
    m.shutdown()

if __name__ == '__main__':
    main()