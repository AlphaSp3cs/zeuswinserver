#!/usr/bin/env python3
"""Night scalp executor — reads latest FTMO scan and places crypto scalps with hard SL+TP."""
import sys, os, json, time, glob
from datetime import datetime, timezone
import MetaTrader5 as mt5
import numpy as np

TERMINAL = r"REDACTED-PATH"
ACCOUNT = REDACTED
SCAN_GLOB = os.path.expanduser(r"~\ftmo_scan_logs\ftmo_scan_*.json")
OUT = os.path.expanduser(r"~\night_scalp_executor_result.json")
MAGIC = 20260726
RISK_PCT = 0.02
DEVIATION = 20


def latest_scan():
    files = sorted(glob.glob(SCAN_GLOB), reverse=True)
    if not files:
        return None
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def calc_atr(symbol, period=14):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, max(period + 1, 100))
    if rates is None or len(rates) < period + 1:
        return None
    highs = np.array([r["high"] for r in rates])
    lows = np.array([r["low"] for r in rates])
    closes = np.array([r["close"] for r in rates])
    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - closes[:-1])
    tr3 = np.abs(lows[1:] - closes[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    return float(np.mean(tr[-period:]))


def calc_volume(info, entry, sl, risk_usd):
    point = info.point or 0.0001
    tick_size = info.trade_tick_size or point
    tick_value = float(info.trade_tick_value or 0.0)
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
    step = float(info.volume_step) if info.volume_step else 0.01
    vol = round(raw / step) * step
    vol = max(info.volume_min, min(info.volume_max, vol))
    return round(vol, 2 if step >= 0.01 else 1), None


def main():
    scan = latest_scan()
    if not scan:
        print(json.dumps({"status": "error", "error": "no scan file found"}, indent=2))
        return

    mt5.shutdown()
    ok = mt5.initialize(path=TERMINAL)
    if not ok:
        print(json.dumps({"status": "error", "error": "MT5 init failed", "last_error": mt5.last_error()}, indent=2))
        return

    acc = mt5.account_info()
    login = getattr(acc, "login", None)
    if int(login or 0) != ACCOUNT:
        print(json.dumps({"status": "error", "error": f"WRONG LOGIN: {login}", "expected": ACCOUNT}, indent=2))
        mt5.shutdown()
        return

    equity = float(acc.equity)
    risk_usd = equity * RISK_PCT
    positions = [p.symbol for p in (mt5.positions_get() or [])]
    results = []
    candidates = scan.get("candidate_trades", [])
    for c in candidates:
        sym = c.get("symbol")
        signal = c.get("signal")
        if not sym or not signal or sym in positions:
            continue
        info = mt5.symbol_info(sym)
        if not info or not info.visible:
            results.append({"symbol": sym, "status": "skip", "reason": "symbol not visible"})
            continue
        tick = mt5.symbol_info_tick(sym)
        if not tick or (not tick.ask and not tick.bid):
            results.append({"symbol": sym, "status": "skip", "reason": "no tick data"})
            continue

        side = "BUY" if signal == "BUY" else "SELL"
        sl = c.get("sl_short" if side == "SELL" else "sl_long")
        tp = c.get("tp_short" if side == "SELL" else "tp_long")
        atr = calc_atr(sym)
        if atr is None:
            results.append({"symbol": sym, "status": "skip", "reason": "no ATR data"})
            continue
        price = tick.ask if side == "BUY" else tick.bid
        if sl is None or tp is None or sl <= 0 or tp <= 0:
            sl = round(price - 2 * atr, info.digits) if side == "BUY" else round(price + 2 * atr, info.digits)
            tp = round(price + 4 * atr, info.digits) if side == "BUY" else round(price - 4 * atr, info.digits)
        if side == "BUY" and (sl >= price or tp <= price):
            sl = round(price - 2 * atr, info.digits)
            tp = round(price + 4 * atr, info.digits)
        if side == "SELL" and (sl <= price or tp >= price):
            sl = round(price + 2 * atr, info.digits)
            tp = round(price - 4 * atr, info.digits)

        vol, err = calc_volume(info, price, sl, risk_usd)
        if err:
            results.append({"symbol": sym, "status": "skip", "reason": f"sizing error: {err}"})
            continue

        # Market order due to venue limit-order restriction for crypto
        otype = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": float(vol),
            "type": otype,
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "deviation": DEVIATION,
            "magic": MAGIC,
            "comment": "OURO_SCALP_MKT",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        status = "placed" if res and res.retcode in (10009, 10008, 10004) else "failed"
        results.append({
            "symbol": sym,
            "side": side,
            "status": status,
            "entry": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "volume": float(vol),
            "risk_usd": float(risk_usd),
            "retcode": int(res.retcode) if res else None,
            "comment": str(res.comment) if res else None,
            "order_ticket": int(res.order) if res and res.order else None,
            "deal_ticket": int(res.deal) if res and res.deal else None,
        })
        time.sleep(1)

    mt5.shutdown()
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account": int(login) if login else None,
        "equity": equity,
        "risk_per_trade_usd": risk_usd,
        "scan_file": scan.get("timestamp"),
        "placed": results,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()