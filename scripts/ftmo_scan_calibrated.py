"""FTMO Compliant Scan — calibrated with OuroBoros layer.

Uses calibration scoring for all candidates and open positions.
Outputs calibrated scores, bottomed-out flags, and trend alignment.
NO EXECUTION PERFORMED in this cron run.
"""
import sys, os, json, time
sys.path.insert(0, os.path.expanduser('~'))
from datetime import datetime, timezone
from pathlib import Path
import MetaTrader5 as mt5
from dataclasses import asdict
from ouroboros_calibration import score_symbol

TERMINAL = r"REDACTED-PATH"
LOG_DIR = Path(r"C:\Users\bravo-usr1\ftmo_scan_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# FTMO house rules
RISK_PER_TRADE_PCT = 1.5
MAX_PORTFOLIO_RISK_PCT = 7.0
SL_ATR_MULT = 2.0
TP_ATR_MULT = 4.0
MAX_EXECUTION_SECONDS = 60
LIMIT_ORDERS_PREFERRED = True
NO_NAKED_POSITIONS = True

def category_from_path(info):
    if not info:
        return 'unknown'
    path = (info.path or '').lower()
    if 'crypto' in path:
        return 'crypto'
    if 'forex' in path or path.startswith('forex'):
        return 'forex'
    if 'index' in path or 'cash' in path:
        return 'indices'
    if any(k in path for k in ['xau', 'xag', 'xpd', 'xpt', 'copper']):
        return 'commodities'
    return 'unknown'

def initialize():
    init = mt5.initialize(TERMINAL)
    if not init:
        return False
    acc = mt5.account_info()
    if acc:
        return True
    return False

def get_rates(symbol, bars=90):
    return mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, bars)

def main():
    start = datetime.now()
    scan_start = time.time()

    if not initialize():
        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "ERROR",
            "error": "MT5 initialization failed",
            "candidate_trades": [],
            "execution": "NO EXECUTION PERFORMED"
        }
        out = LOG_DIR / f"ftmo_scan_{start.strftime('%Y-%m-%d_%H%M')}.json"
        with open(out, 'w') as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2))
        return

    acc = mt5.account_info()
    eq = float(acc.equity) if acc else 0.0
    positions_raw = mt5.positions_get()
    positions = []
    if positions_raw:
        for p in positions_raw:
            positions.append({
                "symbol": p.symbol,
                "volume": float(p.volume),
                "type": "LONG" if p.type == 0 else "SHORT",
                "sl": round(float(p.sl), 5) if p.sl else None,
                "tp": round(float(p.tp), 5) if p.tp else None,
                "profit": round(float(p.profit), 2)
            })

    scored_positions = []
    bottomed_out = []
    for p in positions_raw or []:
        info = mt5.symbol_info(p.symbol)
        cat = category_from_path(info)
        rates = get_rates(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        price = getattr(tick, 'bid', None) if tick else None
        res = score_symbol(p.symbol, cat, rates, current_price=price)
        scored_positions.append({
            "symbol": p.symbol,
            "type": p.type,
            "ticket": int(p.ticket),
            "calibration": asdict(res)
        })
        if res.bottomed_out:
            bottomed_out.append({"symbol": p.symbol, "ticket": int(p.ticket), "calibration": asdict(res)})

    syms = [s for s in mt5.symbols_get() if s.visible]
    seen = set()
    candidates = []
    for s in syms:
        symbol = s.name
        if symbol in seen:
            continue
        seen.add(symbol)
        info = mt5.symbol_info(symbol)
        cat = category_from_path(info)
        rates = get_rates(symbol)
        tick = mt5.symbol_info_tick(symbol)
        price = getattr(tick, 'bid', None) if tick else None
        res = score_symbol(symbol, cat, rates, current_price=price)
        candidates.append({
            "symbol": symbol,
            "category": cat,
            "calibration": asdict(res)
        })
        if res.bottomed_out:
            bottomed_out.append({"symbol": symbol, "candidate": True, "calibration": asdict(res)})

    candidates.sort(key=lambda x: x['calibration']['score'], reverse=True)

    elapsed = time.time() - scan_start
    result = {
        "timestamp": start.isoformat(),
        "terminal": "FTMO Global Markets MT5 Terminal",
        "account": f"{acc.login} ({acc.server})" if acc else None,
        "equity": round(eq, 2),
        "open_positions_count": len(positions),
        "open_positions_scored": scored_positions,
        "candidates_scored": candidates[:50],
        "bottomed_out": bottomed_out,
        "scan_duration_seconds": round(elapsed, 2),
        "ftmo_rules": {
            "risk_per_trade_pct": RISK_PER_TRADE_PCT,
            "max_portfolio_risk_pct": MAX_PORTFOLIO_RISK_PCT,
            "sl_atr_mult": SL_ATR_MULT,
            "tp_atr_mult": TP_ATR_MULT,
            "max_execution_seconds": MAX_EXECUTION_SECONDS,
            "limit_orders_preferred": LIMIT_ORDERS_PREFERRED,
            "no_naked_positions": NO_NAKED_POSITIONS
        },
        "execution": "NO EXECUTION PERFORMED",
        "calibration": "ouroboros_calibration.py",
        "note": "Calibrated scan complete. Trade signals scored per OuroBoros framework. No orders placed in cron run."
    }

    out = LOG_DIR / f"ftmo_scan_{start.strftime('%Y-%m-%d_%H%M')}.json"
    with open(out, 'w') as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2)[:8000])
    print('\n...truncated... full report at', out)
    mt5.shutdown()

if __name__ == "__main__":
    main()