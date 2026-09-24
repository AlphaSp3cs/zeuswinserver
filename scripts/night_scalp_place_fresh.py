#!/usr/bin/env python3
"""One-off executor for fresh candidates with correct volume formula."""
import json, time
from datetime import datetime, timezone
import MetaTrader5 as mt5

TERMINAL = r"REDACTED-PATH"
MAGIC = 20260726

TRADES = [
    {"symbol": "FETUSD", "side": "BUY"},
    {"symbol": "LTCUSD", "side": "SELL"},
    {"symbol": "XLMUSD", "side": "SELL"},
    {"symbol": "BCHUSD", "side": "BUY"},
]

OUT = r"C:\Users\bravo-usr1\night_scalp_place_result.json"

def calc_atr(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
    if not rates or len(rates) < 15:
        return None
    highs = [r["high"] for r in rates]
    lows = [r["low"] for r in rates]
    closes = [r["close"] for r in rates]
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    atr = sum(trs[:14]) / 14.0
    return atr

def calc_volume(info, entry, sl, risk_usd):
    tick_size = info.trade_tick_size or info.point
    tick_value = info.trade_tick_value or 0.0
    if tick_size <= 0 or tick_value <= 0:
        return None, "bad_tick"
    point_value = tick_value / tick_size
    dist = abs(entry - sl)
    if dist <= 0:
        return None, "zero_sl"
    risk_per_lot = dist * point_value
    raw = risk_usd / risk_per_lot
    step = float(info.volume_step) if info.volume_step else 0.01
    vol = round(raw / step) * step
    vol = max(info.volume_min, min(info.volume_max, vol))
    return round(vol, 2 if step >= 0.01 else 1), None

def place(symbol, side, equity):
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not info or not tick or not info.visible:
        return {"symbol": symbol, "status": "no_data"}
    
    risk_usd = equity * 0.02
    atr = calc_atr(symbol)
    if not atr:
        return {"symbol": symbol, "status": "no_atr"}
    
    price = tick.bid if side == "SELL" else tick.ask
    digits = info.digits
    if side == "BUY":
        sl = round(price - 2 * atr, digits)
        tp = round(price + 4 * atr, digits)
    else:
        sl = round(price + 2 * atr, digits)
        tp = round(price - 4 * atr, digits)
    
    if side == "BUY" and (sl >= price or tp <= price):
        sl = round(price - 2 * atr, digits)
        tp = round(price + 4 * atr, digits)
    if side == "SELL" and (sl <= price or tp >= price):
        sl = round(price + 2 * atr, digits)
        tp = round(price - 4 * atr, digits)
    
    vol, err = calc_volume(info, price, sl, risk_usd)
    if err:
        return {"symbol": symbol, "status": "skip", "reason": err}
    
    limit_offset = (info.trade_tick_size * 10) if info.trade_tick_size else (info.point * 10)
    if side == "BUY":
        lp = round(price - limit_offset, digits)
        otype = mt5.ORDER_TYPE_BUY_LIMIT
    else:
        lp = round(price + limit_offset, digits)
        otype = mt5.ORDER_TYPE_SELL_LIMIT
    
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(vol),
        "type": otype,
        "price": float(lp),
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": MAGIC,
        "comment": "OURO_NIGHT_SCALP",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    status = "placed" if res and res.retcode in (10009, 10008, 10004) else "failed"
    tick_size = info.trade_tick_size or info.point
    tick_value = info.trade_tick_value or 0.0
    sl_dist = abs(price - sl)
    actual_risk = round(sl_dist * (tick_value / tick_size) * vol, 2)
    return {
        "symbol": symbol,
        "side": side,
        "status": status,
        "entry": float(lp),
        "sl": float(sl),
        "tp": float(tp),
        "volume": float(vol),
        "risk_usd": round(risk_usd, 2),
        "actual_risk_usd": actual_risk,
        "retcode": int(res.retcode) if res else None,
        "comment": str(res.comment) if res else None,
        "order_ticket": int(res.order) if res and res.order else None,
        "deal_ticket": int(res.deal) if res and res.deal else None,
    }

def main():
    mt5.shutdown()
    ok = mt5.initialize(path=TERMINAL)
    if not ok:
        print(json.dumps({"status": "error", "error": "MT5 init failed", "last_error": mt5.last_error()}, indent=2))
        return
    
    acc = mt5.account_info()
    equity = float(acc.equity)
    positions = [p.symbol for p in (mt5.positions_get() or [])]
    results = []
    new_risk = 0.0
    max_portfolio = equity * 0.08
    
    for t in TRADES:
        sym = t["symbol"]
        side = t["side"]
        if sym in positions:
            results.append({"symbol": sym, "status": "skip_exists"})
            continue
        
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        atr = calc_atr(sym)
        if not info or not tick or not atr:
            results.append({"symbol": sym, "status": "skip_no_data"})
            continue
        
        price = tick.bid if side == "SELL" else tick.ask
        sl = round(price + 2 * atr, info.digits) if side == "SELL" else round(price - 2 * atr, info.digits)
        vol, err = calc_volume(info, price, sl, equity * 0.02)
        if err:
            results.append({"symbol": sym, "status": "skip", "reason": err})
            continue
        
        tick_size = info.trade_tick_size or info.point
        tick_value = info.trade_tick_value or 0.0
        sl_dist = abs(price - sl)
        actual_risk = sl_dist * (tick_value / tick_size) * vol
        
        if new_risk + actual_risk > max_portfolio:
            results.append({"symbol": sym, "status": "skip_portfolio_risk"})
            continue
        
        res = place(sym, side, equity)
        results.append(res)
        if res.get("status") == "placed":
            new_risk += res.get("actual_risk_usd", 0)
        time.sleep(2)
    
    pos_after = mt5.positions_get() or []
    pos_list = [{"ticket": int(p.ticket), "symbol": p.symbol, "type": "LONG" if p.type==0 else "SHORT",
                 "volume": float(p.volume), "sl": float(p.sl) if p.sl else None, "tp": float(p.tp) if p.tp else None,
                 "profit": round(float(p.profit), 2)} for p in pos_after if p.magic == MAGIC]
    
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account": int(acc.login),
        "equity": equity,
        "run_type": "ourotaurus_night_scalp_fresh",
        "venues": {"FTMO MT5": "open", "Alpaca": "auth_blocked", "Kraken": "planned_broker_unavailable"},
        "placed_trades": results,
        "placed_count": len([r for r in results if r.get("status") == "placed"]),
        "rejected_count": len([r for r in results if r.get("status") != "placed"]),
        "new_risk_usd": round(new_risk, 2),
        "positions_after": pos_list,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    mt5.shutdown()

if __name__ == "__main__":
    main()