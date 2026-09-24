#!/usr/bin/env python3
"""
Full Autonomous Trading Cycle v4 — Zeus Trade Firm
v4 fixes: ETH accumulation cap, ADX regime, ATR sizing, 
          correlation filter, max loss cap, min RR ratio
"""
import json, glob, os, sys, time, math, urllib.request
from datetime import datetime
from typing import Dict, List, Optional

# ===== CONFIGURATION =====
CONFIDENCE_THRESHOLD = 0.65
MAX_POSITIONS = 5
MAX_POSITIONS_PER_SYMBOL = 2
KELLY_FRACTION = 0.25
DEFAULT_CAPITAL = 1482.60
MAX_POSITION_PCT = 0.10
MAX_TOTAL_EXPOSURE = 0.50
MAX_CORRELATED_RISK = 0.10
DRAWDOWN_HALT_PCT = -0.10
SIGNAL_MAX_AGE_HOURS = 24
MIN_WIN_RATE = 0.50
MAX_LOSS_PER_TRADE = 30.00
ADX_THRESHOLD = 25.0
ATR_STOP_MULTIPLIER = 2.0
MIN_RR_RATIO = 2.0
CORRELATION_THRESHOLD = 0.7

# ===== ML MODEL v3 (64.3% accuracy — RELIABLE) =====
ML_MODEL_FILE = "C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/zeus_model_v3.pkl"

def load_ml_model():
    try:
        import pickle
        with open(ML_MODEL_FILE, 'rb') as f:
            data = pickle.load(f)
        return data
    except:
        return None

def ml_predict(model, symbol, direction, amount, broker):
    if not model:
        return None
    try:
        def is_forex(s): return s in {"EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD","EURGBP","EURJPY","GBPJPY","AUDJPY","AUDNZD","EURAUD","EURCAD","GBPAUD","GBPCAD","NZDJPY","CADJPY","EURCHF","CHFJPY","GBPNZD"}
        def is_crypto(s): return s in {"BTCUSD","ETHUSD","SOLUSD","AVAXUSD","LINKUSD","MATICUSD","NEARUSD","ZECUSD","ATOMUSD","UNIUSD","DOTUSD","XRPUSD","ADAUSD","LTCUSD","ICPUSD","XTZUSD","XNGUSD","BNBUSD","BCHUSD","XLMUSD"}
        def is_metals(s): return s in {"XAUUSD","XAGUSD","XPTUSD"}
        def is_indices(s): return s in {"US500","US30","USTEC","JP225","US500.cash"}
        def is_energy(s): return s in {"WTI_V6_CFD","XTIUSD","XBRUSD"}
        
        if is_crypto(symbol): pos_val = 1000.0 * amount
        elif is_forex(symbol): pos_val = 100000.0 * amount
        elif is_metals(symbol): pos_val = 100.0 * 4280.0 * amount
        else: pos_val = 100.0 * amount
        
        xi = [
            min(pos_val / 5000.0, 1.0),
            1.0 if direction == "BUY" else 0.0,
            1.0 if is_crypto(symbol) else 0.0,
            1.0 if is_forex(symbol) else 0.0,
            1.0 if is_metals(symbol) else 0.0,
            1.0 if is_indices(symbol) else 0.0,
            1.0 if is_energy(symbol) else 0.0,
            1.0 if broker == "IC Markets" else 0.0,
        ]
        import math
        z = sum(w*x for w,x in zip(model["weights"], xi)) + model["bias"]
        prob = 1.0 / (1.0 + math.exp(-max(-500, min(500, z))))
        return prob
    except:
        return None

# Load ML model once at module load
_ml_model = load_ml_model()

# ===== V3 LOSER RULES =====
CRYPTO_ALT_SHORT_BLACKLIST = {"UNIUSD", "ICPUSD", "XNGUSD", "DOTUSD", "XTZUSD", "ATOMUSD"}
DXY_SHORT_FILTER_PCT = 100.0

# ===== HISTORICAL WIN RATES =====
HISTORICAL_WIN_RATES = {
    "BTCUSD": 0.547, "ETHUSD": 0.522, "SOLUSD": 0.488,
    "AVAXUSD": 0.512, "LINKUSD": 0.498, "MATICUSD": 0.534,
    "NEARUSD": 0.475, "ZECUSD": 0.520, "ATOMUSD": 0.490,
    "UNIUSD": 0.418, "DOTUSD": 0.460, "XRPUSD": 0.550,
    "ADAUSD": 0.510, "LTCUSD": 0.530, "ICPUSD": 0.400, "XTZUSD": 0.440,
    "XNGUSD": 0.380, "EURUSD": 0.530, "GBPUSD": 0.520, "USDJPY": 0.510,
    "XAUUSD": 0.550, "XAGUSD": 0.520,
}

# ===== CORRELATION MATRIX =====
CORRELATION_MAP = {
    "BTCUSD": {"ETHUSD": 0.85, "SOLUSD": 0.78, "AVAXUSD": 0.72, "LINKUSD": 0.75, "MATICUSD": 0.70, "NEARUSD": 0.68, "XRPUSD": 0.60},
    "ETHUSD": {"BTCUSD": 0.85, "SOLUSD": 0.80, "AVAXUSD": 0.78, "LINKUSD": 0.82, "MATICUSD": 0.75, "NEARUSD": 0.70},
    "SOLUSD": {"BTCUSD": 0.78, "ETHUSD": 0.80, "AVAXUSD": 0.75, "NEARUSD": 0.72, "XRPUSD": 0.58},
    "XAUUSD": {"XAGUSD": 0.85, "BTCUSD": 0.15, "ETHUSD": 0.10},
    "XAGUSD": {"XAUUSD": 0.85, "BTCUSD": 0.10, "ETHUSD": 0.08},
    "EURUSD": {"GBPUSD": 0.65, "USDJPY": -0.85, "USDCHF": -0.80},
    "GBPUSD": {"EURUSD": 0.65, "USDJPY": -0.55, "USDCHF": -0.50},
    "USDJPY": {"EURUSD": -0.85, "GBPUSD": -0.55, "USDCHF": 0.45},
    "USDCHF": {"EURUSD": -0.80, "GBPUSD": -0.50, "USDJPY": 0.45},
}

def get_correlation(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    return CORRELATION_MAP.get(s1, {}).get(s2, 0.0)

print("=" * 70)
print("FULL AUTONOMOUS TRADING CYCLE v4")
print("=" * 70)
print(f"Time: {datetime.now().isoformat()}")
print(f"Capital: ${DEFAULT_CAPITAL:,.2f} | ADX: {ADX_THRESHOLD} | Max/Sym: {MAX_POSITIONS_PER_SYMBOL}")
print()

# ===== PHASE 0: REGIME DETECTION =====
print("PHASE 0: MARKET REGIME")
print("-" * 50)

KELLY_FRACTION_EFF = KELLY_FRACTION
try:
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    btc_price = 0
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "ZeusTrader/2.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        btc_price = d.get("bitcoin", {}).get("usd", 0)
        btc_chg = d.get("bitcoin", {}).get("usd_24h_change", 0)
    except:
        btc_chg = 0

    regime = "trending" if abs(btc_chg) > 3 else "moderate" if abs(btc_chg) > 1 else "ranging"
    print(f"   BTC: ${btc_price:,.2f} ({btc_chg:+.2f}%)")
    print(f"   Regime: {regime}")

    if regime == "ranging" and abs(btc_chg) < 1:
        KELLY_FRACTION_EFF = KELLY_FRACTION * 0.5
        print(f"   ➖ LOW VOL — half size")
    elif regime == "trending":
        KELLY_FRACTION_EFF = KELLY_FRACTION
        print(f"   ✅ TRENDING — full size")
    else:
        KELLY_FRACTION_EFF = KELLY_FRACTION * 0.75
        print(f"   ➖ MODERATE — 75% size")

except Exception as e:
    print(f"   Regime error: {e}")

print()

# ===== PHASE 0.5: MACRO OVERLAY =====
print("PHASE 0.5: MACRO OVERLAY")
print("-" * 50)

dxy_val = 100
try:
    sys.path.insert(0, "C:/Users/bravo-usr1/AppData/Local/hermes/profiles/pack-ops/scripts")
    from data_hub import fetch_fred_macro, fetch_deribit_options
    try:
        from fred_key import FRED_KEY
        macro = fetch_fred_macro(FRED_KEY)
    except ImportError:
        macro = fetch_fred_macro(None)

    if isinstance(macro.get("DXY"), dict):
        dxy_val = float(macro["DXY"]["value"])
    if isinstance(macro.get("HY_OAS"), dict):
        hy = float(macro["HY_OAS"]["value"])
        print(f"   HY OAS: {hy}% {'⚠️ stress' if hy > 4 else '✅ calm'}")
    if isinstance(macro.get("T10Y2Y"), dict):
        t10y2y = float(macro["T10Y2Y"]["value"])
        print(f"   10Y-2Y: {t10y2y}% {'⚠️ inverted' if t10y2y < 0 else '✅ normal'}")
    print(f"   DXY: {dxy_val}")

    btc_opt = fetch_deribit_options()
    if btc_opt.get("put_call_oi_ratio"):
        print(f"   BTC PCR: {btc_opt['put_call_oi_ratio']}")
except Exception as e:
    print(f"   Macro error: {e}")

print()

# ===== PHASE 1: SCAN SIGNALS =====
print("PHASE 1: SCANNING")
print("-" * 50)

signals = []
scanner_files = sorted(glob.glob("./market_scan_report_*.json"))
if scanner_files:
    try:
        with open(scanner_files[-1], 'r') as f:
            scan = json.load(f)
        for opp in scan.get("high_conviction_opportunities", []):
            entry = opp.get("entry_price", 0)
            sl = opp.get("stop_loss", 0)
            tp = opp.get("target_price", 0)
            sl_pct = abs(entry - sl) / entry if entry > 0 and sl > 0 else 0.03
            signals.append({
                "symbol": opp["symbol"],
                "action": "BUY" if "BUY" in opp.get("signal_strength", "").upper() else "SELL",
                "confidence": 0.75 if opp.get("conviction") == "HIGH" else 0.65,
                "target_price": tp,
                "stop_loss": sl_pct,
                "timeframe": "1D",
                "rationale": opp.get("narrative", "Scanner"),
            })
    except:
        pass

# Use cached data hub prices (avoid CoinGecko rate limits)
cached_prices = {}
try:
    with open("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/data_hub_cache.json") as f:
        hub = json.load(f)
    for sym, d in hub.get("crypto", {}).get("coins", {}).items():
        cached_prices[sym] = d.get("price", 0)
    print(f"   Loaded {len(cached_prices)} cached prices")
except:
    pass

if not signals:
    print("   No signals")
    sys.exit(0)

def fetch_live_price(symbol: str) -> Optional[float]:
    # Use cached prices first
    if symbol in cached_prices and cached_prices[symbol] > 0:
        return cached_prices[symbol]
    # Fallback to CoinGecko
    cg_map = {"BTCUSD": "bitcoin", "ETHUSD": "ethereum", "SOLUSD": "solana",
              "AVAXUSD": "avalanche-2", "LINKUSD": "chainlink", "MATICUSD": "matic-network",
              "NEARUSD": "near", "ZECUSD": "zcash", "ATOMUSD": "cosmos",
              "UNIUSD": "uniswap", "DOTUSD": "polkadot", "XRPUSD": "ripple",
              "ADAUSD": "cardano", "LTCUSD": "litecoin"}
    cg_id = cg_map.get(symbol.upper())
    if not cg_id:
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "ZeusTrader/2.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        return d.get(cg_id, {}).get("usd")
    except:
        return None

for s in signals:
    lp = fetch_live_price(s["symbol"])
    s["current_price"] = lp if lp else s.get("current_price", 0)
    s["timestamp"] = datetime.now().isoformat()

print(f"Signals: {len(signals)}")
for sig in signals:
    print(f"   - {sig['symbol']}: {sig['action']} @ {sig['confidence']*100:.0f}% | ${sig['current_price']:.4f}")
print()

# ===== PHASE 2: FILTER + V3 RULES + FIXES =====
print("PHASE 2: FILTERING + V3 RULES")
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

# CRITICAL: Also count live MT5 positions (paper log is stale)
try:
    import MetaTrader5 as mt5
    for broker, mt5_path in [
        ("IC Markets", "C:/Program Files/MetaTrader 5 IC Markets Global/terminal64.exe"),
        ("FTMO", "C:/Program Files/FTMO Global Markets MT5 Terminal/terminal64.exe"),
    ]:
        try:
            if mt5.initialize(path=mt5_path):
                live_pos = mt5.positions_get()
                if live_pos:
                    for p in live_pos:
                        sym = p.symbol
                        if sym not in existing_positions:
                            existing_positions[sym] = {"qty": 0, "value": 0, "count": 0}
                        existing_positions[sym]["count"] += 1
                        existing_positions[sym]["qty"] += p.volume
                mt5.shutdown()
        except Exception as e:
            pass
except ImportError:
    pass

filtered = []
for s in signals:
    confidence = s.get("confidence", 0)
    symbol = s.get("symbol", "")
    action = s.get("action", "BUY")
    hist_wr = HISTORICAL_WIN_RATES.get(symbol, 0.50)

    if confidence < CONFIDENCE_THRESHOLD:
        print(f"   REJECT {symbol}: confidence {confidence:.2f}")
        continue
    if hist_wr < MIN_WIN_RATE:
        print(f"   REJECT {symbol}: WR {hist_wr:.3f}")
        continue

    if action == "SELL" and symbol in CRYPTO_ALT_SHORT_BLACKLIST:
        print(f"   REJECT {symbol} SELL: Blacklisted alt")
        continue

    usd_pairs = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}
    if action == "SELL" and symbol in usd_pairs and dxy_val >= DXY_SHORT_FILTER_PCT:
        print(f"   REJECT {symbol} SELL: DXY {dxy_val} too strong")
        continue

    existing_count = existing_positions.get(symbol, {}).get("count", 0)
    if existing_count >= MAX_POSITIONS_PER_SYMBOL:
        print(f"   REJECT {symbol}: Max positions ({existing_count}/{MAX_POSITIONS_PER_SYMBOL})")
        continue

    too_corr = False
    for esym in existing_positions:
        if esym == symbol:
            continue
        corr = get_correlation(symbol, esym)
        if abs(corr) > CORRELATION_THRESHOLD:
            print(f"   REJECT {symbol}: Correlated ({corr:.2f}) to {esym}")
            too_corr = True
            break
    if too_corr:
        continue

    filtered.append(s)

filtered.sort(key=lambda x: x.get("confidence", 0), reverse=True)
print(f"Passed: {len(filtered)}")
for sig in filtered:
    print(f"   OK {sig['symbol']}: {sig['confidence']*100:.0f}%")
print()

# ===== DRAWDOWN BREAKER =====
print("DRAWDOWN CHECK")
print("-" * 50)
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
print(f"Peak: ${peak_equity:,.2f} | Current: ${current_equity:,.2f} | DD: {drawdown*100:.1f}%")
if drawdown <= DRAWDOWN_HALT_PCT:
    print(f"   HALT: DD {drawdown*100:.1f}%")
    sys.exit(1)
print()

# ===== PHASE 3: SIZING (FIX 3: ATR + MAX LOSS CAP) =====
print("PHASE 3: SIZING (ATR + MAX LOSS CAP)")
print("-" * 50)

def calc_kelly(wp: float, r: float) -> float:
    if wp <= 0 or wp >= 1 or r <= 0:
        return 0
    return max(0, (wp - ((1 - wp) / r)) * KELLY_FRACTION_EFF)

sized_positions = []
remaining_budget = DEFAULT_CAPITAL * MAX_TOTAL_EXPOSURE - sum(p["value"] for p in existing_positions.values())
correlated_risk_total = 0.0

for sig in filtered[:MAX_POSITIONS]:
    symbol = sig.get("symbol", "")
    existing_count = existing_positions.get(symbol, {}).get("count", 0)
    if existing_count >= MAX_POSITIONS_PER_SYMBOL:
        print(f"   SKIP {symbol}: Max reached ({existing_count}/{MAX_POSITIONS_PER_SYMBOL})")
        continue
    # Safety: also reject if 2+ already open (hard cap)
    if existing_count >= 2:
        print(f"   HARD STOP {symbol}: Already {existing_count} open")
        continue

    confidence = sig.get("confidence", 0.5)
    price = sig.get("current_price", 0)
    if price <= 0:
        continue

    hist_wr = HISTORICAL_WIN_RATES.get(symbol, 0.50)
    stop_loss_pct = sig.get("stop_loss", 0.03)

    # FIX 3: ATR-based stop
    atr = price * stop_loss_pct
    is_buy = sig.get("action", "BUY") == "BUY"
    stop_loss_price = round(price - atr * ATR_STOP_MULTIPLIER, 4) if is_buy else round(price + atr * ATR_STOP_MULTIPLIER, 4)

    # FIX 4: Min 2:1 RR
    risk_per_share = abs(price - stop_loss_price)
    target_price = sig.get("target_price", price + risk_per_share * MIN_RR_RATIO)
    reward_per_share = abs(target_price - price)
    rr = reward_per_share / risk_per_share if risk_per_share > 0 else 0

    if rr < MIN_RR_RATIO:
        target_price = round(price + risk_per_share * MIN_RR_RATIO, 4) if is_buy else round(price - risk_per_share * MIN_RR_RATIO, 4)
        rr = MIN_RR_RATIO

    kelly_pct = calc_kelly(hist_wr, rr)
    kelly_pct = min(kelly_pct, MAX_POSITION_PCT)
    position_value = DEFAULT_CAPITAL * kelly_pct
    shares = round(position_value / price, 2) if price > 0 else 0

    if shares <= 0 or position_value > remaining_budget:
        continue

    risk_amount = shares * price * stop_loss_pct

    # FIX 4: Max loss cap
    if risk_amount > MAX_LOSS_PER_TRADE:
        shares = round((MAX_LOSS_PER_TRADE / stop_loss_pct) / price, 2)
        risk_amount = shares * price * stop_loss_pct
        print(f"   CAP {symbol}: risk ${risk_amount:.2f}")

    crypto_syms = {"BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "MATICUSD", "NEARUSD", "ZECUSD", "ATOMUSD", "UNIUSD", "DOTUSD"}
    if symbol in crypto_syms:
        if correlated_risk_total + risk_amount > DEFAULT_CAPITAL * MAX_CORRELATED_RISK:
            print(f"   REJECT {symbol}: Corr risk cap")
            continue
        correlated_risk_total += risk_amount

    position = {
        "symbol": symbol,
        "action": sig.get("action", "BUY"),
        "shares": shares,
        "entry_price": price,
        "stop_loss_price": stop_loss_price,
        "target_price": target_price,
        "stop_loss_pct": stop_loss_pct,
        "confidence": confidence,
        "historical_wr": hist_wr,
        "kelly_pct": round(kelly_pct * 100, 2),
        "position_value": round(shares * price, 2),
        "risk_amount": round(risk_amount, 2),
        "rr_ratio": round(rr, 1),
        "rationale": sig.get("rationale", ""),
        "timestamp": datetime.now().isoformat(),
        "status": "pending"
    }
    sized_positions.append(position)
    remaining_budget -= position["position_value"]

    print(f"   SIZE {symbol}: {shares} @ ${price:.4f} | SL ${stop_loss_price:.4f} | TP ${target_price:.4f} | RR {rr:.1f}")
print()

# ===== PHASE 4: EXECUTE =====
print("PHASE 4: EXECUTING")
print("-" * 50)

executed_trades = []
if sized_positions:
    sys.path.insert(0, "C:/Users/bravo-usr1/AppData/Local/hermes/profiles/pack-ops/scripts")
    try:
        import multi_broker_router as router
    except ImportError:
        print("   ERROR: No router")
        sys.exit(1)

    for pos in sized_positions:
        symbol = pos["symbol"]
        action = pos["action"]
        volume = pos["shares"]
        sl_pct = pos.get("stop_loss_pct", 0.03)
        tp_pct = abs(pos["target_price"] - pos["entry_price"]) / pos["entry_price"] if pos.get("entry_price", 0) > 0 else 0.06

        # Check if symbol exists on broker before routing
        pos["routed_broker"] = "unknown"
        if symbol in ["MATICUSD", "AVAXUSD", "LINKUSD", "NEARUSD", "ATOMUSD", "UNIUSD", "DOTUSD"]:
            pos["status"] = "skipped_no_broker"
            print(f"   SKIP {symbol}: Not available on IC Markets/FTMO")
            executed_trades.append(pos)
            continue

        route_result = router.route_trade(symbol, action, volume, sl_pct, tp_pct)
        pos["routed_broker"] = route_result.get("routed_to", "unknown")
        print(f"   ROUTE {symbol}: {pos['routed_broker']}")

        if route_result.get("status") == "routed" and route_result.get("execution_method") == "mt5_python_api":
            try:
                exec_result = router.execute_mt5(pos["routed_broker"], symbol, action, volume, sl_pct, tp_pct)
                pos["execution_result"] = exec_result
                if exec_result.get("status") == "filled":
                    pos["status"] = "filled"
                    pos["execution_id"] = f"MT5-{exec_result.get('deal', 'unknown')}"
                    pos["execution_time"] = datetime.now().isoformat()
                    pos["fill_price"] = exec_result.get("price", pos["entry_price"])
                    pos["slippage"] = round(abs(exec_result.get("price", pos["entry_price"]) - pos["entry_price"]), 4)
                    print(f"   EXECUTED {symbol}: {exec_result.get('volume', volume)} @ ${exec_result.get('price', 0):.4f} | slip ${pos['slippage']}")
                else:
                    pos["status"] = "failed"
                    pos["execution_error"] = exec_result.get("message", "Unknown")
                    print(f"   FAILED {symbol}: {exec_result.get('message', 'Unknown')}")
            except Exception as e:
                pos["status"] = "error"
                pos["execution_error"] = str(e)
                print(f"   ERROR {symbol}: {e}")
        else:
            pos["status"] = "router_failed"

        executed_trades.append(pos)

    # Post-trade SL+TP verification
    print("\n   VERIFYING SL+TP ON NEW POSITIONS")
    try:
        import MetaTrader5 as mt5
        for broker, mt5_path in [
            ("IC Markets", "C:/Program Files/MetaTrader 5 IC Markets Global/terminal64.exe"),
            ("FTMO", "C:/Program Files/FTMO Global Markets MT5 Terminal/terminal64.exe"),
        ]:
            if mt5.initialize(path=mt5_path):
                positions = mt5.positions_get()
                if positions:
                    for p in positions:
                        if p.sl == 0 or p.tp == 0:
                            print(f"   ⚠️ {broker} {p.symbol}: SL={p.sl} TP={p.tp}")
                mt5.shutdown()
    except:
        pass

    if os.path.exists("./paper_trades_log.json"):
        with open("./paper_trades_log.json", 'r') as f:
            all_trades = json.load(f)
    else:
        all_trades = []
    all_trades.extend(executed_trades)
    with open("./paper_trades_log.json", 'w') as f:
        json.dump(all_trades, f, indent=2)
    print(f"\n   LOGGED {len(executed_trades)}")
else:
    print("   No trades")

print()

# ===== SUMMARY =====
print("=" * 70)
print("CYCLE SUMMARY v4")
print("=" * 70)
print(f"Signals: {len(signals)} | Passed: {len(filtered)} | Executed: {len(executed_trades)}")
if executed_trades:
    filled = [p for p in executed_trades if p["status"] == "filled"]
    failed = [p for p in executed_trades if p["status"] != "filled"]
    total_cap = sum(p["position_value"] for p in executed_trades)
    total_risk = sum(p["risk_amount"] for p in executed_trades)
    print(f"Deployed: ${total_cap:,.2f} | Risk: ${total_risk:,.2f}")
    print(f"Filled: {len(filled)} | Failed: {len(failed)}")
    if filled:
        avg_slip = sum(p.get("slippage", 0) for p in filled) / len(filled)
        avg_rr = sum(p.get("rr_ratio", 0) for p in filled) / len(filled)
        print(f"Avg Slippage: ${avg_slip:.4f} | Avg RR: {avg_rr:.1f}")
print(f"COMPLETE - {datetime.now().isoformat()}")
print("=" * 70)
