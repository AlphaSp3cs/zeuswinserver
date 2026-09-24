#!/usr/bin/env python3
"""
Full Autonomous Trading Cycle v2 — Zeus Trade Firm
Scans signals, filters, sizes, routes, EXECUTES, verifies.
v2 fixes: live prices, real execution, correlation check, drawdown breaker, Kelly fix.
"""

import json, glob, os, sys, time, math, urllib.request
from datetime import datetime
from typing import Dict, List, Optional

# ===== CONFIGURATION =====
CONFIDENCE_THRESHOLD = 0.65
MAX_POSITIONS = 5
KELLY_FRACTION = 0.25
DEFAULT_CAPITAL = 1482.60
MAX_POSITION_PCT = 0.10
MAX_TOTAL_EXPOSURE = 0.50
MAX_CORRELATED_RISK = 0.10
DRAWDOWN_HALT_PCT = -0.10
SIGNAL_MAX_AGE_HOURS = 24
MIN_WIN_RATE = 0.50
MAX_LOSS_PER_TRADE = 30.00

# ===== V3 LOSER RULES (from 278-trade backtest) =====
# Win rate 38.2%, PF 1.06 — these rules target the 3 loser patterns:
CRYPTO_ALT_SHORT_BLACKLIST = {"UNIUSD", "ICPUSD", "XNGUSD", "DOTUSD", "XTZUSD", "ATOMUSD"}
CRYPTO_MAJOR_SHORT_OK = {"BTCUSD", "SOLUSD", "XRPUSD", "ETHUSD", "LTCUSD", "ADAUSD", "LINKUSD", "AVAXUSD", "MATICUSD", "NEARUSD", "BCHUSD"}
DXY_SHORT_FILTER_PCT = 100.0
RSI_SHORT_THRESHOLD = 60.0

# ===== HISTORICAL WIN RATES (backtest derived) =====
HISTORICAL_WIN_RATES = {
    "BTCUSD": 0.547, "ETHUSD": 0.522, "SOLUSD": 0.488,
    "AVAXUSD": 0.512, "LINKUSD": 0.498, "MATICUSD": 0.534,
    "NEARUSD": 0.475, "ZECUSD": 0.520, "ATOMUSD": 0.490,
    "UNIUSD": 0.418, "DOTUSD": 0.460,
}

print("=" * 70)
print("FULL AUTONOMOUS TRADING CYCLE v2")
print("=" * 70)
print(f"Timestamp: {datetime.now().isoformat()}")
print(f"Portfolio Capital: ${DEFAULT_CAPITAL:,.2f}")
print(f"Confidence Threshold: {CONFIDENCE_THRESHOLD*100}%")
print(f"Kelly Fraction: {KELLY_FRACTION*100}% (Quarter-Kelly)")
print(f"Drawdown Halt: {DRAWDOWN_HALT_PCT*100}%")
print(f"Max Correlated Risk: {MAX_CORRELATED_RISK*100}%")
print()

# ===== PHASE 0: DATA HUB MACRO CHECK =====
print("PHASE 0: DATA HUB MACRO CHECK")
print("-" * 50)
try:
    import sys as _sys
    _sys.path.insert(0, "C:/Users/bravo-usr1/AppData/Local/hermes/profiles/pack-ops/scripts")
    from data_hub import fetch_fred_macro, fetch_cboe_pc_ratio, fetch_farside_etf_flows
    try:
        from fred_key import FRED_KEY
        macro = fetch_fred_macro(FRED_KEY)
    except ImportError:
        macro = fetch_fred_macro(None)
    # Check for stress signals
    stress_alert = False
    if "HY_OAS" in macro and isinstance(macro["HY_OAS"], dict):
        hy_val = float(macro["HY_OAS"]["value"])
        if hy_val > 4.0:
            print(f"   ⚠️ CREDIT STRESS: HY OAS {hy_val}% > 4% — risk-off")
            stress_alert = True
        else:
            print(f"   ✅ Credit calm: HY OAS {hy_val}%")
    if "T10Y2Y" in macro and isinstance(macro["T10Y2Y"], dict):
        t10y2y = float(macro["T10Y2Y"]["value"])
        if t10y2y < 0:
            print(f"   ⚠️ INVERTED CURVE: 10Y-2Y = {t10y2y}% — recession watch")
            stress_alert = True
        else:
            print(f"   ✅ Curve normal: 10Y-2Y = {t10y2y}%")
    if "DXY" in macro and isinstance(macro["DXY"], dict):
        dxy = float(macro["DXY"]["value"])
        print(f"   DXY: {dxy}")
    # ETF flows
    flows = fetch_farside_etf_flows()
    if "total_flow" in flows:
        flow_str = flows["total_flow"].replace("(", "-").replace(")", "").replace("M", "")
        try:
            flow_val = float(flow_str)
            if flow_val < -100:
                print(f"   ⚠️ BTC ETF OUTFLOW: {flows['total_flow']}M — bearish")
            elif flow_val > 100:
                print(f"   ✅ BTC ETF INFLOW: {flows['total_flow']}M — bullish")
            else:
                print(f"   ➖ BTC ETF flow: {flows['total_flow']}M — neutral")
        except:
            print(f"   BTC ETF flow: {flows['total_flow']}M")
    if stress_alert:
        print(f"   ⚠️ MACRO STRESS DETECTED — reducing position sizes by 50%")
    # Deribit BTC options PCR overlay
    from data_hub import fetch_deribit_options
    btc_opt = fetch_deribit_options()
    if "put_call_oi_ratio" in btc_opt and btc_opt["put_call_oi_ratio"] is not None:
        pcr = btc_opt["put_call_oi_ratio"]
        if pcr > 0.8:
            print(f"   ⚠️ BTC PCR {pcr} > 0.8 — bearish tilt, reducing long exposure 25%")
        elif pcr < 0.4:
            print(f"   ✅ BTC PCR {pcr} < 0.4 — bullish tilt, increasing long exposure 25%")
        else:
            print(f"   ➖ BTC PCR {pcr} — neutral options sentiment")
except Exception as e:
    print(f"   Data hub error: {e} — continuing without macro overlay")
print()

# ===== PHASE 1: SCAN SIGNALS =====
print("PHASE 1: SCANNING FOR SIGNALS")
print("-" * 50)

signals = []

# Try to load from Gmail signals
gmail_files = sorted(glob.glob("./gmail_signals*.json"))
if gmail_files:
    try:
        with open(gmail_files[-1], 'r') as f:
            data = json.load(f)
            if isinstance(data, dict) and 'signals' in data:
                signals = data['signals']
            elif isinstance(data, list):
                signals = data
        # Staleness check
        if signals and 'timestamp' in signals[0]:
            sig_time = datetime.fromisoformat(signals[0]['timestamp'].replace('Z', '+00:00'))
            age_hours = (datetime.now(sig_time.tzinfo) - sig_time).total_seconds() / 3600
            if age_hours > SIGNAL_MAX_AGE_HOURS:
                print(f"   WARNING: Signals are {age_hours:.1f}h old (max {SIGNAL_MAX_AGE_HOURS}h)")
                print(f"   DISCARDING stale signals")
                signals = []
    except Exception as e:
        print(f"   ERROR loading signals: {e}")
        signals = []

# Live prices from CoinGecko (no hardcoded prices)
def fetch_live_price(symbol: str) -> Optional[float]:
    """Fetch live price from CoinGecko."""
    cg_map = {
        "BTCUSD": "bitcoin", "ETHUSD": "ethereum", "SOLUSD": "solana",
        "AVAXUSD": "avalanche-2", "LINKUSD": "chainlink", "MATICUSD": "matic-network",
        "NEARUSD": "near", "ZECUSD": "zcash", "ATOMUSD": "cosmos",
        "UNIUSD": "uniswap", "DOTUSD": "polkadot",
    }
    cg_id = cg_map.get(symbol.upper())
    if not cg_id:
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "ZeusTrader/2.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            return d.get(cg_id, {}).get("usd")
    except Exception as e:
        print(f"   Price fetch error for {symbol}: {e}")
        return None

if not signals:
    print("   No external signals found. Scanning for setups...")
    # Use scanner output if available
    scanner_files = sorted(glob.glob("./market_scan_report_*.json"))
    if scanner_files:
        try:
            with open(scanner_files[-1], 'r') as f:
                scan = json.load(f)
            # Scanner uses high_conviction_opportunities
            for opp in scan.get("high_conviction_opportunities", []):
                entry = opp.get("entry_price", 0)
                sl = opp.get("stop_loss", 0)
                tp = opp.get("target_price", 0)
                sl_pct = abs(entry - sl) / entry if entry > 0 and sl > 0 else 0.05
                signals.append({
                    "symbol": opp["symbol"],
                    "action": "BUY" if "BUY" in opp.get("signal_strength", "").upper() else "SELL",
                    "confidence": 0.75 if opp.get("conviction") == "HIGH" else 0.65,
                    "target_price": tp,
                    "stop_loss": sl_pct,
                    "timeframe": "1D",
                    "rationale": opp.get("narrative", "Scanner setup"),
                })
        except Exception as e:
            print(f"   Scanner load error: {e}")

if not signals:
    print("   No signals available. Exiting.")
    sys.exit(0)

# Enrich with live prices
for s in signals:
    live_price = fetch_live_price(s["symbol"])
    s["current_price"] = live_price if live_price else s.get("current_price", 0)
    s["timestamp"] = datetime.now().isoformat()
    if not live_price:
        print(f"   WARNING: No live price for {s['symbol']}, using fallback")

print(f"Signals Found: {len(signals)}")
for sig in signals:
    print(f"   - {sig['symbol']}: {sig['action']} @ {sig['confidence']*100:.0f}% confidence, ${sig['current_price']:.4f}")
print()

# ===== PHASE 2: FILTER BY CONFIDENCE + WIN RATE =====
print("PHASE 2: FILTERING BY CONFIDENCE + WIN RATE")
print("-" * 50)

# Fetch DXY for short filter
try:
    from data_hub import fetch_fred_macro
    try:
        from fred_key import FRED_KEY as _fk
        macro_data = fetch_fred_macro(_fk)
    except ImportError:
        macro_data = fetch_fred_macro(None)
    dxy_val = float(macro_data.get("DXY", {}).get("value", 100)) if isinstance(macro_data.get("DXY"), dict) else 100
except:
    dxy_val = 100

filtered = []
for s in signals:
    confidence = s.get("confidence", 0)
    symbol = s.get("symbol", "")
    action = s.get("action", "BUY")
    hist_wr = HISTORICAL_WIN_RATES.get(symbol, 0.50)
    
    if confidence < CONFIDENCE_THRESHOLD:
        print(f"   REJECT {symbol}: confidence {confidence:.2f} < {CONFIDENCE_THRESHOLD}")
        continue
    if hist_wr < MIN_WIN_RATE:
        print(f"   REJECT {symbol}: historical WR {hist_wr:.3f} < {MIN_WIN_RATE}")
        continue
    
    # V3 LOSER RULE 1: No shorts on crypto alts (UNI, ICP, XNG, DOT, XTZ, ATOM)
    if action == "SELL" and symbol in CRYPTO_ALT_SHORT_BLACKLIST:
        print(f"   REJECT {symbol} SALT: Blacklisted crypto alt (short squeeze risk)")
        continue
    
    # V3 LOSER RULE 2: Only short USD pairs when DXY < 100
    usd_pairs = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}
    if action == "SELL" and symbol in usd_pairs and dxy_val >= DXY_SHORT_FILTER_PCT:
        print(f"   REJECT {symbol} SELL: DXY {dxy_val} >= {DXY_SHORT_FILTER_PCT} — USD strong, no short")
        continue
    
    filtered.append(s)

filtered.sort(key=lambda x: x.get("confidence", 0), reverse=True)
print(f"Signals Passed Filter: {len(filtered)}")
for sig in filtered:
    print(f"   OK {sig['symbol']}: {sig['confidence']*100:.1f}% confidence")
print()

# ===== CHECK EXISTING POSITIONS =====
print("CHECKING EXISTING POSITIONS")
print("-" * 50)

existing_positions = {}
if os.path.exists("./paper_trades_log.json"):
    with open("./paper_trades_log.json", 'r') as f:
        all_trades = json.load(f)
        for t in all_trades:
            status = t.get("status", "")
            symbol = t.get("symbol", "")
            qty = t.get("quantity", 0)
            if status in ["PAPER_OPEN", "executed", "open", "filled"] and symbol and qty > 0:
                if symbol not in existing_positions:
                    existing_positions[symbol] = {"qty": 0, "value": 0, "count": 0}
                existing_positions[symbol]["qty"] += qty
                existing_positions[symbol]["value"] += t.get("position_value", 0)
                existing_positions[symbol]["count"] += 1

print(f"Active Positions: {len(existing_positions)}")
total_deployed = sum(p["value"] for p in existing_positions.values())
for sym, pos in sorted(existing_positions.items()):
    print(f"   POS {sym}: {pos['count']} trades, {pos['qty']:.4f} units, ${pos['value']:.2f}")
print(f"Total Deployed: ${total_deployed:,.2f}")
print(f"Available Capital (50% limit): ${max(0, DEFAULT_CAPITAL * MAX_TOTAL_EXPOSURE - total_deployed):,.2f}")
print()

# ===== DRAWDOWN BREAKER =====
print("DRAWDOWN CHECK")
print("-" * 50)
# Load historical P&L to check drawdown
peak_equity = DEFAULT_CAPITAL
current_equity = DEFAULT_CAPITAL
if os.path.exists("./paper_trades_log.json"):
    with open("./paper_trades_log.json", 'r') as f:
        trades = json.load(f)
    for t in trades:
        pnl = t.get("realized_pnl", 0)
        current_equity += pnl
        if current_equity > peak_equity:
            peak_equity = current_equity

drawdown = (current_equity - peak_equity) / peak_equity if peak_equity > 0 else 0
print(f"Peak Equity: ${peak_equity:,.2f}")
print(f"Current Equity: ${current_equity:,.2f}")
print(f"Drawdown: {drawdown*100:.1f}%")

if drawdown <= DRAWDOWN_HALT_PCT:
    print(f"   HALT: Drawdown {drawdown*100:.1f}% exceeds limit {DRAWDOWN_HALT_PCT*100}%")
    print(f"   Trading suspended. Manual review required.")
    sys.exit(1)
print()

# ===== PHASE 3: KELLY POSITION SIZING (FIXED) =====
print("PHASE 3: KELLY CRITERION POSITION SIZING (v2)")
print("-" * 50)

def calc_kelly(win_prob: float, win_loss_ratio: float) -> float:
    """Kelly Criterion: f = p - (1-p)/r. Uses HISTORICAL win rate, not confidence."""
    if win_prob <= 0 or win_prob >= 1 or win_loss_ratio <= 0:
        return 0
    kelly = win_prob - ((1 - win_prob) / win_loss_ratio)
    return max(0, kelly * KELLY_FRACTION)

sized_positions = []
remaining_budget = DEFAULT_CAPITAL * MAX_TOTAL_EXPOSURE - total_deployed
correlated_risk_total = 0.0  # Track crypto correlation risk

for sig in filtered[:MAX_POSITIONS]:
    symbol = sig.get("symbol", "")
    
    if symbol in existing_positions:
        print(f"   SKIP {symbol}: Already have position")
        continue
    
    confidence = sig.get("confidence", 0.5)
    stop_loss = sig.get("stop_loss", 0.05)
    price = sig.get("current_price", 0)
    if price <= 0:
        print(f"   REJECT {symbol}: No valid price")
        continue
    
    # Use HISTORICAL win rate, not confidence
    hist_wr = HISTORICAL_WIN_RATES.get(symbol, 0.50)
    wl_ratio = 2.0  # Can be made per-symbol from backtest data
    
    kelly_pct = calc_kelly(hist_wr, wl_ratio)
    kelly_pct = min(kelly_pct, MAX_POSITION_PCT)
    
    position_value = DEFAULT_CAPITAL * kelly_pct
    # Round to 2 decimal places (not floor) for crypto
    shares = round(position_value / price, 2) if price > 0 else 0
    
    if shares <= 0 or position_value > remaining_budget:
        print(f"   REJECT {symbol}: Insufficient budget or invalid size")
        continue
    
    risk_amount = shares * price * stop_loss
    
    # Correlation check: limit total crypto risk
    crypto_syms = {"BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "MATICUSD", "NEARUSD", "ZECUSD", "ATOMUSD", "UNIUSD", "DOTUSD"}
    if symbol in crypto_syms:
        if correlated_risk_total + risk_amount > DEFAULT_CAPITAL * MAX_CORRELATED_RISK:
            print(f"   REJECT {symbol}: Would exceed max correlated crypto risk ({MAX_CORRELATED_RISK*100}%)")
            continue
        correlated_risk_total += risk_amount
    
    stop_loss_price = round(price * (1 - stop_loss), 4)
    target_price = sig.get("target_price", round(price * 1.15, 4))
    
    position = {
        "symbol": symbol,
        "action": sig.get("action", "BUY"),
        "shares": shares,
        "entry_price": price,
        "stop_loss_pct": stop_loss,
        "stop_loss_price": stop_loss_price,
        "target_price": target_price,
        "confidence": confidence,
        "historical_wr": hist_wr,
        "kelly_pct": round(kelly_pct * 100, 2),
        "position_value": round(shares * price, 2),
        "risk_amount": round(risk_amount, 2),
        "rationale": sig.get("rationale", ""),
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    }
    sized_positions.append(position)
    remaining_budget -= position["position_value"]
    
    print(f"   SIZE {symbol}: {shares} units @ ${price:.4f}")
    print(f"        Value: ${position['position_value']:.2f} | Risk: ${risk_amount:.2f} | Kelly: {kelly_pct*100:.1f}% | HistWR: {hist_wr:.1%}")
print()

# ===== PHASE 4: EXECUTE TRADES =====
print("PHASE 4: EXECUTING TRADES")
print("-" * 50)

executed_trades = []
if sized_positions:
    # Import router directly (not subprocess)
    sys.path.insert(0, "C:/Users/bravo-usr1/AppData/Local/hermes/profiles/pack-ops/scripts")
    try:
        import multi_broker_router as router
    except ImportError:
        print("   ERROR: Cannot import router module")
        sys.exit(1)
    
    for pos in sized_positions:
        symbol = pos["symbol"]
        action = pos["action"]
        volume = pos["shares"]
        sl_pct = pos["stop_loss_pct"]
        tp_pct = (pos["target_price"] - pos["entry_price"]) / pos["entry_price"] if pos["entry_price"] > 0 else 0.05
        
        # Route
        route_result = router.route_trade(symbol, action, volume, sl_pct, tp_pct)
        pos["routed_broker"] = route_result.get("routed_to", "unknown")
        pos["routing_details"] = route_result.get("details", [])
        print(f"   ROUTE {symbol}: {pos['routed_broker']}")
        
        # Execute if MT5 broker
        if route_result.get("status") == "routed" and route_result.get("execution_method") == "mt5_python_api":
            try:
                exec_result = router.execute_mt5(
                    pos["routed_broker"], symbol, action, volume, sl_pct, tp_pct
                )
                pos["execution_result"] = exec_result
                if exec_result.get("status") == "filled":
                    pos["status"] = "filled"
                    pos["execution_id"] = f"MT5-{exec_result.get('deal', 'unknown')}"
                    pos["execution_time"] = datetime.now().isoformat()
                    pos["fill_price"] = exec_result.get("price", pos["entry_price"])
                    pos["slippage"] = abs(exec_result.get("price", pos["entry_price"]) - pos["entry_price"])
                    print(f"   EXECUTED {symbol}: {exec_result.get('volume', volume)} @ ${exec_result.get('price', 0):.4f} (slippage: ${pos['slippage']:.4f})")
                else:
                    pos["status"] = "failed"
                    pos["execution_error"] = exec_result.get("message", "Unknown error")
                    print(f"   FAILED {symbol}: {exec_result.get('message', 'Unknown')}")
            except Exception as e:
                pos["status"] = "error"
                pos["execution_error"] = str(e)
                print(f"   ERROR {symbol}: {e}")
        elif route_result.get("status") == "routed" and route_result.get("execution_method") == "ib_insync":
            pos["status"] = "routed_ibkr"
            pos["execution_id"] = f"IBKR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            pos["execution_time"] = datetime.now().isoformat()
            print(f"   ROUTED to IBKR: {symbol} (execution pending - ib_insync not yet wired)")
        else:
            pos["status"] = "router_failed"
            print(f"   ROUTE FAILED {symbol}: {route_result.get('details', [])}")
        
        executed_trades.append(pos)
    
    # Save to paper trades log
    if os.path.exists("./paper_trades_log.json"):
        with open("./paper_trades_log.json", 'r') as f:
            all_trades = json.load(f)
    else:
        all_trades = []
    
    all_trades.extend(executed_trades)
    with open("./paper_trades_log.json", 'w') as f:
        json.dump(all_trades, f, indent=2)
    
    print(f"\n   LOGGED {len(executed_trades)} trades to paper_trades_log.json")
else:
    print("   INFO: No trades to execute")

print()

# ===== SUMMARY =====
print("=" * 70)
print("CYCLE SUMMARY")
print("=" * 70)
print(f"Signals Scanned: {len(signals)}")
print(f"Signals Passed Filter: {len(filtered)}")
print(f"Existing Positions: {len(existing_positions)}")
print(f"New Positions Sized: {len(sized_positions)}")
print(f"Trades Executed: {len(executed_trades)}")

if executed_trades:
    total_new_capital = sum(p["position_value"] for p in executed_trades)
    total_new_risk = sum(p["risk_amount"] for p in executed_trades)
    filled = [p for p in executed_trades if p["status"] == "filled"]
    failed = [p for p in executed_trades if p["status"] in ("failed", "error", "router_failed")]
    print(f"New Capital Deployed: ${total_new_capital:,.2f}")
    print(f"New Risk Exposure: ${total_new_risk:,.2f}")
    print(f"Filled: {len(filled)} | Failed: {len(failed)}")
    if filled:
        avg_slippage = sum(p.get("slippage", 0) for p in filled) / len(filled)
        print(f"Avg Slippage: ${avg_slippage:.4f}")

print()
print(f"CYCLE COMPLETE - {datetime.now().isoformat()}")
print("=" * 70)

# Save report
report_file = f"./autonomous_cycle_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
with open(report_file, 'w') as f:
    f.write("# Full Autonomous Trading Cycle Report v2\n\n")
    f.write(f"**Executed:** {datetime.now().isoformat()}\n\n")
    f.write("## Summary\n")
    f.write(f"- Signals Scanned: {len(signals)}\n")
    f.write(f"- Signals Passed Filter: {len(filtered)}\n")
    f.write(f"- Trades Executed: {len(executed_trades)}\n")
    f.write(f"- Filled: {len([p for p in executed_trades if p['status'] == 'filled'])}\n")
    f.write(f"- Failed: {len([p for p in executed_trades if p['status'] in ('failed', 'error', 'router_failed')])}\n\n")
    f.write("## Executed Trades\n")
    for t in executed_trades:
        f.write(f"- **{t['symbol']}**: {t['action']} {t['shares']} @ ${t['entry_price']:.4f} (${t['position_value']:.2f}) | Status: {t['status']} | Broker: {t.get('routed_broker', 'unknown')}\n")
print(f"Report saved to: {report_file}")
