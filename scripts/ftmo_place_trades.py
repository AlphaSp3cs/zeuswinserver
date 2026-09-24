"""Place FTMO MT5 high-conviction buy trades with hard SL+TP and 1% risk sizing, tolerant to zero live ticks."""
import sys, os, time, math
sys.path.insert(0, os.path.expanduser('~'))
from mt5_connect import connect as mt5_connect
import MetaTrader5 as mt5
from datetime import datetime, timezone

SYMBOLS = [
    {"symbol": "XLMUSD", "side": "BUY", "note": "oversold"},
    {"symbol": "ETHUSD", "side": "BUY", "note": "steady"},
    {"symbol": "SOLUSD", "side": "BUY", "note": "steady"},
    {"symbol": "BTCUSD", "side": "BUY", "note": "pullback"},
]
RISK_PCT = 0.01
SL_ATR = 2.0
TP_ATR = 4.0
DEVIATION = 20
MAGIC = 20260723
LIMIT_DISCOUNT = 0.001  # 0.1%

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_h1(symbol, bars=600):
    for tf in (mt5.TIMEFRAME_H1,):
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
    if rates is None or len(rates) < 60:
        return None
    return rates

def atr14(rates):
    closes = [float(r['close']) for r in rates]
    highs = [float(r['high']) for r in rates]
    lows = [float(r['low']) for r in rates]
    trs = []
    for i in range(1, len(rates)):
        h = highs[i]; l = lows[i]; pc = closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < 14:
        return None
    a = sum(trs[:14]) / 14.0
    for i in range(14, len(trs)):
        a = (a * 13 + trs[i]) / 14.0
    return a

def close_price(rates):
    if rates is None or len(rates) == 0:
        return None
    # usually numpy array; sometimes list
    return float(rates[-1]['close'])

def calc_volume(symbol, info, entry, sl, risk_usd):
    point = info.point or 0.0001
    tick_size = info.trade_tick_size or point
    tick_value = info.trade_tick_value
    if tick_size <= 0 or tick_value <= 0:
        return None, f"bad_tick size={tick_size} value={tick_value}"
    sl_dist = abs(entry - sl)
    if sl_dist <= 0:
        return None, "zero_sl"
    risk_per_pt = tick_value / tick_size
    sl_dist_pts = sl_dist / point
    if sl_dist_pts <= 0:
        return None, "zero_points"
    raw = risk_usd / (sl_dist_pts * risk_per_pt)
    vol = float(raw)
    step = float(info.volume_step) if info.volume_step else 0.01
    vol = round(vol / step) * step
    vol = max(info.volume_min, min(info.volume_max, vol))
    return round(vol, 2 if step >= 0.01 else 1), None

def send_order(m, symbol, side, entry, sl, tp, volume, info, backtest_ok=True):
    if not backtest_ok:
        raise ValueError(f"backtest_required but missing for {symbol}")
    digits = info.digits
    sl = round(sl, digits)
    tp = round(tp, digits)
    tick = m.symbol_info_tick(symbol)
    use_market = False
    price = round(entry, digits)
    otype = m.ORDER_TYPE_BUY if side == 'BUY' else m.ORDER_TYPE_SELL
    if tick and tick.ask and tick.bid:
        if side == 'BUY':
            limit_price = round(tick.ask * (1 - LIMIT_DISCOUNT), digits)
            if 0 < limit_price < tick.ask:
                price = limit_price
                use_otype = m.ORDER_TYPE_BUY_LIMIT
            else:
                price = tick.ask
                use_otype = m.ORDER_TYPE_BUY
                use_market = True if LIMIT_DISCOUNT<=0 else False
        else:
            limit_price = round(tick.bid * (1 + LIMIT_DISCOUNT), digits)
            if limit_price > tick.bid and limit_price > 0:
                price = limit_price
                use_otype = m.ORDER_TYPE_SELL_LIMIT
            else:
                price = tick.bid
                use_otype = m.ORDER_TYPE_SELL
                use_market = True if LIMIT_DISCOUNT<=0 else False
    else:
        use_otype = m.ORDER_TYPE_BUY if side == 'BUY' else m.ORDER_TYPE_SELL
        use_market = True
    req = {
        "action": m.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": otype if use_market else use_otype,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": "ZEUS_HIGHCONV",
        "type_time": m.ORDER_TIME_GTC,
    }
    res = m.order_send(req)
    if res.retcode not in (10009, 10008, 10004):
        req2 = dict(req)
        req2["type"] = m.ORDER_TYPE_BUY if side=='BUY' else m.ORDER_TYPE_SELL
        req2["price"] = tick.ask if side=='BUY' else tick.bid if tick else price
        if not (tick and tick.ask and tick.bid):
            req2["price"] = price
        print(f"  retry_market {symbol} price={req2['price']} type={req2['type']}")
        res = m.order_send(req2)
    return res, price, sl, tp, volume

m = mt5_connect('ftmo')
acc = m.account_info()
equity = float(acc.equity)
risk_usd = equity * RISK_PCT
print(f"FTMO account={acc.login} server={acc.server} equity={equity:.2f} risk_per_trade={risk_usd:.2f} time={now_iso()}")

results = []
for t in SYMBOLS:
    symbol = t['symbol']; side = t['side']
    info = m.symbol_info(symbol)
    if not info:
        print(f"SKIP {symbol}: no symbol_info")
        results.append({"symbol": symbol, "status": "skip", "reason": "symbol_info missing"})
        continue
    tick = m.symbol_info_tick(symbol)
    rates = get_h1(symbol)
    a = atr14(rates) if rates is not None else None
    last = close_price(rates)
    if last is None or a is None or a <= 0:
        print(f"SKIP {symbol}: bad market data last={last} atr={a}")
        results.append({"symbol": symbol, "status": "skip", "reason": "bad market data"})
        continue
    if tick and tick.ask and tick.bid:
        ref_price = tick.ask if side=='BUY' else tick.bid
    else:
        # No live tick: fallback to last close
        ref_price = last
    # set entry near ref, conservative for buy: slight adjust below last
    if side == 'BUY':
        entry = ref_price
        sl = round(entry - SL_ATR * a, info.digits)
        tp = round(entry + TP_ATR * a, info.digits)
    else:
        entry = ref_price
        sl = round(entry + SL_ATR * a, info.digits)
        tp = round(entry - TP_ATR * a, info.digits)
    if sl <= 0 or tp <= 0:
        print(f"SKIP {symbol}: nonpositive SL/TP")
        results.append({"symbol": symbol, "status": "skip", "reason": "non-positive SL/TP"})
        continue
    vol, err = calc_volume(symbol, info, entry, sl, risk_usd)
    if err:
        print(f"SKIP {symbol}: sizing error {err}")
        results.append({"symbol": symbol, "status": "skip", "reason": err})
        continue
    print(f"\nTRY {symbol} {side} entry={round(entry, info.digits)} atr={a} sl={sl} tp={tp} vol={vol}")
    try:
        res, used_price, used_sl, used_tp, used_vol = send_order(m, symbol, side, entry, sl, tp, vol, info)
        print(f"  retcode={res.retcode} comment={res.comment} order={res.order} deal={res.deal}")
        if res.retcode in (10009, 10008):
            results.append({
                "symbol": symbol, "side": side, "status": "placed",
                "price": float(used_price), "sl": float(used_sl), "tp": float(used_tp),
                "volume": float(used_vol), "order_ticket": res.order, "deal_ticket": res.deal,
                "comment": res.comment, "atr": a
            })
        else:
            results.append({
                "symbol": symbol, "side": side, "status": "failed", "retcode": res.retcode,
                "comment": res.comment, "entry": float(entry), "sl": float(sl), "tp": float(tp),
                "volume": float(vol)
            })
    except Exception as e:
        print(f"  EXCEPTION {symbol}: {e}")
        results.append({"symbol": symbol, "status": "error", "error": str(e)})

print("\n=== LIVE POSITIONS WITH MAGIC ", MAGIC, " ===")
for p in m.positions_get() or []:
    if p.magic == MAGIC:
        print(f"ticket={p.ticket} {p.symbol} {'LONG' if p.type==0 else 'SHORT'} vol={p.volume} open={p.price_open} sl={p.sl} tp={p.tp} profit={p.profit}")

with open(r'C:\Users\bravo-usr1\ftmo_place_result.json','w') as f:
    json.dump({"timestamp": now_iso(), "account": int(acc.login), "equity": equity, "results": results}, f, indent=2)
print("\nsaved ftmo_place_result.json")
m.shutdown()