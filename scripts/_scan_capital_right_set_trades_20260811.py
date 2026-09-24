"""
Live re-scan on Capital.com MT5 (RIGHT terminal) + sentiment fold + staged trade placement.
- Reads live prices/RSI for tradable crypto symbols.
- Folds all prior scanned data (macro sentiment: NEUTRAL regime, 9L/2S across 22 sectors)
  as the sentiment overlay for all other sectors.
- Recomputes stage-limit entries and TPs from LIVE capital.com prices (scanner's own
  stage prices are on a different price scale and cannot be reused).
- Places PENDING (cancelable) BUY_LIMIT / SELL_LIMIT orders -- NOT market orders.
Set DRY_RUN=False to actually place orders.
"""
import MetaTrader5 as mt5
import json, datetime, sys

CRED = {
    "path": r"C:\Program Files\Capital.com MetaTrader 5\terminal64.exe",
    "login": int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685')),
    "password": os.environ.get('CAPITAL_MT5_PASSWORD', ''),
    "server": os.environ.get('CAPITAL_MT5_SERVER', 'Capital.ComBah-Demo'),
}
DRY_RUN = False

# Scanner signals from ALL_SECTOR_TICKETS_2026-08-11.md (side, symbol, class)
SCANNER = [
    ("LONG",  "ZEC",  "CRYPTO"), ("LONG", "ETH", "CRYPTO"), ("LONG", "XRP", "CRYPTO"),
    ("LONG",  "BTC",  "EQUITY"), ("LONG", "SOL", "CRYPTO"), ("LONG", "AVAX", "CRYPTO"),
    ("LONG",  "AAVE", "CRYPTO"), ("LONG", "XMR", "CRYPTO"), ("LONG", "DOGE", "CRYPTO"),
    ("SHORT", "WLD",  "EQUITY"), ("SHORT", "NEAR", "CRYPTO"),
]
# Map scanner symbol -> capital.com MT5 symbol (None if not offered by broker).
BROKER_MAP = {
    "ZEC": None, "ETH": "ETHUSD", "XRP": "XRPUSD", "BTC": "BTCUSD", "SOL": "SOLUSD",
    "AVAX": "AVAXUSD", "AAVE": "AAVEUSD", "XMR": None, "DOGE": "DOGEUSD",
    "WLD": None, "NEAR": None,
}
# Strategy parameters derived from scanner tickets (verified: long TP = +25%, short TP = -20%,
# stage entry = -5% for longs / +5% for shorts).
LONG_TP_PCT, LONG_STAGE_PCT = 0.25, -0.05
SHORT_TP_PCT, SHORT_STAGE_PCT = -0.20, 0.05
SL_PCT_BELOW_ENTRY = 0.05  # SL = entry * (1 - 0.05) for longs

def rsi(series, period=14):
    if len(series) < period + 1:
        return None
    deltas = [series[i] - series[i-1] for i in range(1, len(series))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def main():
    if not mt5.initialize(**CRED):
        print("INIT FAILED:", mt5.last_error()); sys.exit(1)
    acc = mt5.account_info()
    print(f"CONNECTED login={acc.login} bal={acc.balance:.2f} eq={acc.equity:.2f} "
          f"server={acc.server} mode={acc.trade_mode}")

    # Open positions (already set) -- skip these symbols to avoid double exposure.
    open_pos = mt5.positions_get() or []
    open_syms = {p.symbol for p in open_pos}
    print(f"OPEN POSITIONS ({len(open_pos)}): {sorted(open_syms)}")

    # ---- LIVE SCAN on capital.com RIGHT ----
    live = {}
    for scanner_sym, brk in BROKER_MAP.items():
        if brk is None:
            live[scanner_sym] = {"broker_sym": None, "available": False, "reason": "not offered by capital.com MT5"}
            continue
        if not mt5.symbol_select(brk, True):
            live[scanner_sym] = {"broker_sym": brk, "available": False, "reason": "symbol_select failed"}
            continue
        tick = mt5.symbol_info_tick(brk)
        info = mt5.symbol_info(brk)
        rates = mt5.copy_rates_from_pos(brk, mt5.TIMEFRAME_M15, 0, 100)
        r = rsi([x["close"] for x in rates]) if (rates is not None and len(rates) > 0) else None
        bid = tick.bid if tick else None
        live[scanner_sym] = {
            "broker_sym": brk, "available": True, "bid": bid,
            "ask": tick.ask if tick else None,
            "rsi14_m15": round(r, 2) if r is not None else None,
            "digits": info.digits if info else None,
            "min_vol": info.volume_min if info else None,
        }

    # ---- SENTIMENT FOLD ----
    # Macro sentiment (all prior scans up to this point):
    MACRO = {"regime": "NEUTRAL", "longs": 9, "shorts": 2, "sectors": 22,
             "bias": "buy-the-dip (9L vs 2S, neutral regime)"}
    # Live crypto micro-sentiment: average RSI of available cryptos
    rsilist = [v["rsi14_m15"] for v in live.values() if v.get("available") and v["rsi14_m15"] is not None]
    crypto_rsi_avg = round(sum(rsilist)/len(rsilist), 2) if rsilist else None
    print(f"\nMACRO SENTIMENT: {MACRO}")
    print(f"LIVE CRYPTO RSI AVG (capital.com RIGHT): {crypto_rsi_avg} -> "
          f"{'oversold/accumulate' if (crypto_rsi_avg or 99) < 45 else ('neutral' if (crypto_rsi_avg or 0) < 60 else 'elevated')}")

    # ---- BUILD ORDERS (staged, cancelable limit orders) ----
    orders = []
    for side, sym, cls in SCANNER:
        v = live.get(sym, {})
        if not v.get("available"):
            orders.append({"scanner_sym": sym, "action": "SKIP", "reason": v.get("reason", "n/a")})
            continue
        brk = v["broker_sym"]
        if brk in open_syms:
            orders.append({"scanner_sym": sym, "broker_sym": brk, "action": "SKIP",
                           "reason": "already open on capital.com RIGHT"})
            continue
        bid = v["bid"]
        if bid is None:
            orders.append({"scanner_sym": sym, "broker_sym": brk, "action": "SKIP", "reason": "no live bid"})
            continue
        if side == "LONG":
            entry = round(bid * (1 + LONG_STAGE_PCT), v["digits"])
            tp = round(bid * (1 + LONG_TP_PCT), v["digits"])
            sl = round(entry * (1 - SL_PCT_BELOW_ENTRY), v["digits"])
            order_type = mt5.ORDER_TYPE_BUY_LIMIT
        else:
            entry = round(bid * (1 + SHORT_STAGE_PCT), v["digits"])
            tp = round(bid * (1 + SHORT_TP_PCT), v["digits"])
            sl = round(entry * (1 + SL_PCT_BELOW_ENTRY), v["digits"])
            order_type = mt5.ORDER_TYPE_SELL_LIMIT
        orders.append({
            "scanner_sym": sym, "broker_sym": brk, "side": side,
            "live_bid": bid, "entry_limit": entry, "tp": tp, "sl": sl,
            "rsi14_m15": v["rsi14_m15"], "order_type": order_type,
            "action": "PLACE_PENDING",
        })

    # ---- EXECUTE (or dry run) ----
    results = []
    for o in orders:
        if o.get("action") != "PLACE_PENDING":
            print(f"  SKIP {o['scanner_sym']}: {o.get('reason')}")
            results.append(o); continue
        brk = o["broker_sym"]
        syminfo = mt5.symbol_info(brk)
        min_vol = syminfo.volume_min if syminfo else 0.01
        # conservative notional target ~ $80 per new trade
        vol = max(min_vol, round((80.0 / o["live_bid"]) / min_vol) * min_vol) if o["live_bid"] else min_vol
        vol = round(vol, 4)
        print(f"  {'[DRYRUN] ' if DRY_RUN else ''}PLACE {o['side']} LIMIT {brk} "
              f"vol={vol} entry={o['entry_limit']} sl={o['sl']} tp={o['tp']} rsi={o['rsi14_m15']}")
        if DRY_RUN:
            results.append({**o, "planned_vol": vol, "status": "DRYRUN"})
            continue
        req = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": brk, "volume": vol, "type": o["order_type"],
            "price": o["entry_limit"], "sl": o["sl"], "tp": o["tp"],
            "deviation": 20, "magic": 20260811, "comment": "Zeus-capital-right-staged",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_RETURN,
        }
        r = mt5.order_send(req)
        results.append({**o, "planned_vol": vol, "retcode": r.retcode, "comment": r.comment, "order": r.order})
        print(f"     -> retcode={r.retcode} order={r.order} {r.comment}")

    # ---- BREAKEVEN MANAGEMENT on open positions (standing law: move SL to BE at >=2% profit) ----
    be_actions = []
    for p in open_pos:
        entry = p.price_open; cur = p.price_current
        if p.type == mt5.POSITION_TYPE_BUY:
            pnl = (cur - entry)/entry*100
        else:
            pnl = (entry - cur)/entry*100
        if pnl >= 2.0 and p.sl != entry and p.type == mt5.POSITION_TYPE_BUY:
            print(f"  BE-MGMT {p.symbol} ticket={p.ticket} pnl={pnl:.2f}% -> move SL to entry {entry}")
            if not DRY_RUN:
                r = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket,
                                    "sl": entry, "tp": p.tp})
                be_actions.append({"ticket": p.ticket, "symbol": p.symbol, "retcode": r.retcode})
            else:
                be_actions.append({"ticket": p.ticket, "symbol": p.symbol, "pnl": round(pnl,2), "planned": "move SL->entry"})
        else:
            be_actions.append({"ticket": p.ticket, "symbol": p.symbol, "pnl": round(pnl,2), "action": "no change"})

    mt5.shutdown()
    out = {
        "timestamp": datetime.datetime.utcnow().isoformat()+"Z",
        "broker": "mt5_capital_right", "login": 1028685, "server": "Capital.ComBah-Demo",
        "dry_run": DRY_RUN, "macro_sentiment": MACRO,
        "live_crypto_rsi_avg": crypto_rsi_avg, "live": live, "orders": results,
        "breakeven_management": be_actions,
    }
    with open("_scan_capital_right_20260811.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nWROTE _scan_capital_right_20260811.json")
    return out

if __name__ == "__main__":
    main()
