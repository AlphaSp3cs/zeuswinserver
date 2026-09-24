#!/usr/bin/env python3
import os, sys, json, math
import MetaTrader5 as mt5

CAPITAL_PATH = r"C:\Program Files\Capital.com MetaTrader 5"
LOGIN = int(os.environ.get('CAPITAL_MT5_LOGIN', '0'))
SERVER = os.environ.get('CAPITAL_MT5_SERVER', 'CapitalCom-Demo')
PASSWORD = os.environ.get('CAPITAL_MT5_PASSWORD', '')
# Portable data directory under Roaming so we use the existing account/session.
DATA_DIR = os.path.join(os.environ["APPDATA"], "MetaQuotes", "Terminal", "46520203FA1E86B0DCE9D1386F461BB8")

def init_capital():
    ok = mt5.initialize(
        path=os.path.join(CAPITAL_PATH, "terminal64.exe"),
        login=LOGIN,
        server=SERVER,
        password=PASSWORD,
        portable=True,
        data_path=DATA_DIR,
    )
    info = mt5.account_info()
    terminal_info = mt5.terminal_info()
    return {
        "initialize": bool(ok),
        "login": info.login if info else None,
        "server": info.server if info else None,
        "company": info.company if info else None,
        "equity": float(info.equity) if info else None,
        "balance": float(info.balance) if info else None,
        "margin": float(info.margin) if info else None,
        "free_margin": float(info.margin_free) if info else None,
        "margin_level": float(info.margin_level) if info else None,
        "terminal_build": str(terminal_info.build) if terminal_info else None,
        "terminal_path": str(terminal_info.path) if terminal_info else None,
    }

def close_position(ticket, symbol, volume, pos_type, price, deviation=10):
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": int(ticket),
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5.ORDER_TYPE_SELL if int(pos_type) == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "price": float(price),
        "deviation": int(deviation),
        "type_time": mt5.ORDER_TIME_GTC,
    }
    res = mt5.order_send(req)
    if res is None:
        return {"ticket": int(ticket), "closed": False, "retcode": None, "comment": "order_send returned None"}
    return {
        "ticket": int(ticket),
        "closed": bool(res.retcode == mt5.TRADE_RETCODE_DONE or res.retcode == mt5.TRADE_RETCODE_DONE_PARTIAL),
        "retcode": int(res.retcode),
        "comment": str(res.comment),
        "order": int(res.order) if hasattr(res, "order") else None,
        "request_id": int(res.request_id) if hasattr(res, "request_id") else None,
        "result": str(res.retcode),
    }

def repair_sltp(pos, atr=None):
    symbol = pos.symbol
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    entry = pos.price_open
    sl = pos.sl
    tp = pos.tp
    # If both sl and tp are None, invalid.
    if sl is None and tp is None:
        return {"action": "close_invalid", "reason": "no_sl_no_tp"}
    si = mt5.symbol_info(symbol)
    if si is None:
        return None
    min_stop = si.stops_level * si.point
    if min_stop <= 0:
        min_stop = si.point * 10
    # use 1.0 ATR or min_stop * 3 if no atr
    dist = max(atr if atr and atr > 0 else min_stop * 3, min_stop)
    if pos.type == mt5.POSITION_TYPE_BUY:
        desired_sl = entry - dist
        desired_tp = entry + dist * 2
        if sl is None or sl >= entry or desired_sl >= entry:
            new_sl = desired_sl
            new_tp = desired_tp
            return {"action": "set_sltp", "new_sl": new_sl, "new_tp": new_tp}
        if tp is None or tp <= entry:
            return {"action": "set_tp_only", "new_tp": desired_tp}
    else:
        desired_sl = entry + dist
        desired_tp = entry - dist * 2
        if sl is None or sl <= entry or desired_sl <= entry:
            new_sl = desired_sl
            new_tp = desired_tp
            return {"action": "set_sltp", "new_sl": new_sl, "new_tp": desired_tp}
        if tp is None or tp >= entry:
            return {"action": "set_sl_only", "new_sl": desired_sl}
    return None

def set_sltp(ticket, symbol, volume, pos_type, sl, tp):
    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": int(ticket),
        "symbol": symbol,
        "volume": float(volume),
        "type": int(pos_type),
        "sl": float(sl) if sl is not None else 0.0,
        "tp": float(tp) if tp is not None else 0.0,
        "type_time": mt5.ORDER_TIME_GTC,
    }
    res = mt5.order_send(req)
    if res is None:
        return {"ticket": int(ticket), "ok": False, "retcode": None, "comment": "order_send returned None"}
    return {
        "ticket": int(ticket),
        "ok": bool(res.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL, mt5.TRADE_RETCODE_NO_CHANGES)),
        "retcode": int(res.retcode),
        "comment": str(res.comment),
    }

def fetch_atr(symbol, timeframe=mt5.TIMEFRAME_H1, bars=100):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) < 20:
        return None
    try:
        highs = [float(r[2]) for r in rates]
        lows = [float(r[3]) for r in rates]
        closes = [float(r[4]) for r in rates]
    except Exception:
        return None
    trs = []
    for i in range(1, len(rates)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    if not trs:
        return None
    # ATR14
    window = 14
    if len(trs) < window:
        return sum(trs)/len(trs)
    return sum(trs[-window:]) / window

def main():
    out = {"init": None, "positions": [], "actions": [], "universe_sample": [], "errors": []}
    try:
        out["init"] = init_capital()
    except Exception as e:
        out["errors"].append({"stage": "init", "error": str(e)})
        print(json.dumps(out, indent=2))
        mt5.shutdown()
        return

    if not out["init"]["initialize"] or out["init"]["login"] != LOGIN:
        out["errors"].append({"stage": "login", "error": "login mismatch or init failed", "init": out["init"]})
        print(json.dumps(out, indent=2))
        mt5.shutdown()
        return

    try:
        positions = mt5.positions_get()
    except Exception as e:
        out["errors"].append({"stage": "positions_get", "error": str(e)})
        print(json.dumps(out, indent=2))
        mt5.shutdown()
        return

    out["positions"] = []
    for p in positions or []:
        pos = {
            "ticket": int(p.ticket),
            "symbol": str(p.symbol),
            "type": "buy" if p.type == mt5.POSITION_TYPE_BUY else "sell",
            "volume": float(p.volume),
            "entry": float(p.price_open),
            "sl": float(p.sl) if p.sl is not None else None,
            "tp": float(p.tp) if p.tp is not None else None,
            "profit": float(p.profit),
            "swap": float(p.swap),
            "comment": str(p.comment) if hasattr(p, "comment") else "",
        }
        out["positions"].append(pos)

    if not out["positions"]:
        out["message"] = "no_open_positions"
        print(json.dumps(out, indent=2))
        mt5.shutdown()
        return

    # Validity + repair/close pass
    out["actions"] = []
    for pos in out["positions"]:
        ticket = pos["ticket"]
        symbol = pos["symbol"]
        volume = pos["volume"]
        ptype = pos["type"]
        sl = pos["sl"]
        tp = pos["tp"]
        # Try repair attempt via order_send TRADE_ACTION_SLTP; if 10025, valid.
        atr = fetch_atr(symbol)
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(ticket),
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5.POSITION_TYPE_BUY if ptype == "buy" else mt5.POSITION_TYPE_SELL,
            "sl": float(sl) if sl is not None else 0.0,
            "tp": float(tp) if tp is not None else 0.0,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        try:
            res = mt5.order_send(req)
        except Exception as e:
            res = None
            out["actions"].append({"ticket": ticket, "symbol": symbol, "action": "probe_failed", "retcode": None, "comment": str(e)})
            continue
        retcode = int(res.retcode) if res and hasattr(res, "retcode") else None
        comment = str(res.comment) if res and hasattr(res, "comment") else ""
        if retcode == mt5.TRADE_RETCODE_DONE or retcode == mt5.TRADE_RETCODE_NO_CHANGES:
            out["actions"].append({"ticket": ticket, "symbol": symbol, "valid": True, "retcode": retcode, "comment": comment})
        else:
            # Invalid stops or other. Try one repair.
            repair = repair_sltp(type("P", (), {"symbol": symbol, "price_open": pos["entry"], "type": mt5.POSITION_TYPE_BUY if ptype=="buy" else mt5.POSITION_TYPE_SELL, "sl": sl, "tp": tp})(), atr=atr)
            if repair and repair.get("action") == "close_invalid":
                tick = mt5.symbol_info_tick(symbol)
                close_price = tick.bid if ptype == "buy" else tick.ask
                cres = close_position(ticket, symbol, volume, mt5.POSITION_TYPE_BUY if ptype=="buy" else mt5.POSITION_TYPE_SELL, close_price)
                out["actions"].append({"ticket": ticket, "symbol": symbol, "valid": False, "retcode": retcode, "comment": comment, "close_result": cres})
            elif repair:
                new_sl = repair.get("new_sl")
                new_tp = repair.get("new_tp")
                if repair.get("action") == "set_tp_only":
                    new_sl = sl
                elif repair.get("action") == "set_sl_only":
                    new_tp = tp
                rreq = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": int(ticket),
                    "symbol": symbol,
                    "volume": float(volume),
                    "type": mt5.POSITION_TYPE_BUY if ptype=="buy" else mt5.POSITION_TYPE_SELL,
                    "sl": float(new_sl) if new_sl is not None else 0.0,
                    "tp": float(new_tp) if new_tp is not None else 0.0,
                    "type_time": mt5.ORDER_TIME_GTC,
                }
                try:
                    rres = mt5.order_send(rreq)
                except Exception as e:
                    rres = None
                rret = int(rres.retcode) if rres and hasattr(rres, "retcode") else None
                rcomment = str(rres.comment) if rres and hasattr(rres, "comment") else ""
                if rret in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_NO_CHANGES):
                    out["actions"].append({"ticket": ticket, "symbol": symbol, "valid": False, "retcode": retcode, "comment": comment, "repair": repair, "repair_retcode": rret, "repair_comment": rcomment, "repaired": True})
                else:
                    tick = mt5.symbol_info_tick(symbol)
                    close_price = tick.bid if ptype == "buy" else tick.ask
                    cres = close_position(ticket, symbol, volume, mt5.POSITION_TYPE_BUY if ptype=="buy" else mt5.POSITION_TYPE_SELL, close_price)
                    out["actions"].append({"ticket": ticket, "symbol": symbol, "valid": False, "retcode": retcode, "comment": comment, "repair": repair, "repair_retcode": rret, "repair_comment": rcomment, "close_result": cres})
            else:
                out["actions"].append({"ticket": ticket, "symbol": symbol, "valid": False, "retcode": retcode, "comment": comment, "action": "unknown_invalid"})

    # Universe sample: first 100 tradable symbols from Market Watch / all symbols
    try:
        all_syms = mt5.symbols_get()
    except Exception as e:
        all_syms = []
        out["errors"].append({"stage": "symbols_get", "error": str(e)})
    sample = []
    for s in (all_syms or []):
        try:
            if getattr(s, "select", False):
                tick = mt5.symbol_info_tick(s.name)
                if tick and tick.last:
                    sample.append({
                        "symbol": s.name,
                        "bid": float(tick.bid),
                        "ask": float(tick.ask),
                        "last": float(tick.last),
                    })
                    if len(sample) >= 120:
                        break
        except Exception:
            continue
    out["universe_sample"] = sample

    print(json.dumps(out, indent=2))
    mt5.shutdown()

if __name__ == "__main__":
    main()
