#!/usr/bin/env python3
"""
OuroTaurus Comprehensive Market Scan
- Full portfolio analysis
- Fresh signal generation across all monitored assets
- High-conviction opportunity identification
- Signal cache update
"""

import json, os, sys
from datetime import datetime
from pathlib import Path

# Configuration
PORTFOLIO_VALUE = 1482.60
MAX_EXPOSURE = 0.50  # 50% hard cap
MAX_POSITION = 0.10  # 10% per position
RSI_OVERSOLD_THRESHOLD = 45
ARCHIMEDES_MIN_THRESHOLD = 0.70

CURRENT_PRICES = {}  # Will be populated from data hub

def load_current_prices_from_hub():
    """Get current prices from data hub cache"""
    hub_path = "C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/data_hub_cache.json"
    if not os.path.exists(hub_path):
        return {}
    with open(hub_path) as f:
        hub = json.load(f)
    
    prices = {}
    
    # Crypto
    sym_map = {"BTC": "BTCUSD", "ETH": "ETHUSD", "SOL": "SOLUSD", "XRP": "XRPUSD",
               "ADA": "ADAUSD", "DOGE": "DOGEUSD", "LTC": "LTCUSD", "DOT": "DOTUSD",
               "AVAX": "AVAXUSD", "MATIC": "MATICUSD", "LINK": "LINKUSD", "UNI": "UNIUSD",
               "ATOM": "ATOMUSD", "ARB": "ARBUSD", "FIL": "FILUSD", "ICP": "ICPUSD",
               "XLM": "XLMUSD", "ALGO": "ALGOUSD", "FTM": "FTMUSD", "APT": "APTUSD",
               "SUI": "SUIUSD", "NEAR": "NEARUSD", "TRX": "TRXUSD", "SHIB": "SHIBUSD"}
    for sym, data in hub.get("crypto", {}).get("coins", {}).items():
        if isinstance(data, dict) and "price" in data:
            mt5_sym = sym_map.get(sym, sym + "USD")
            prices[mt5_sym] = data["price"]
    
    # Forex
    for item in hub.get("forex", []):
        if isinstance(item, dict):
            sym = item.get("symbol", "").replace("=X", "")
            prices[sym] = item.get("price", 0)
    
    # Futures/Metals/Indices/Energy
    fwd_map = {"CL": "WTIUSD", "BZ": "BRENTUSD", "GC": "XAUUSD", "SI": "XAGUSD", "PL": "XPTUSD", "HG": "COPPER"}
    for item in hub.get("futures", []):
        if isinstance(item, dict):
            raw = item.get("symbol", "").replace("=F", "")
            sym = fwd_map.get(raw, raw)
            prices[sym] = item.get("price", 0)
    
    # International equities
    for item in hub.get("intl_equities", []):
        if isinstance(item, dict):
            sym = item.get("symbol", "").replace("^", "")
            prices[sym] = item.get("price", 0)
    
    return prices

# Load at module import
try:
    CURRENT_PRICES = load_current_prices_from_hub()
except:
    pass

# Non-tradable symbols on our brokers (paper only)
NON_TRADABLE = {"HE", "LEANHOGS", "LE", "CC", "SB", "KC", "CT", "ZC", "ZS", "ZO"}

def load_open_positions():
    """Load and analyze open positions from paper trades log + MT5 live."""
    open_positions = {}
    
    # Load from paper log
    try:
        with open("paper_trades_log.json", "r") as f:
            trades = json.load(f)
        for trade in trades:
            symbol = trade.get("symbol", "")
            status = trade.get("status", "")
            if status in ["PAPER_OPEN", "PAPER_FILLED", "filled", "executed"] and symbol:
                if symbol not in open_positions:
                    open_positions[symbol] = trade
                elif trade.get("timestamp", "") > open_positions[symbol].get("timestamp", ""):
                    open_positions[symbol] = trade
    except:
        pass
    
    # Load from MT5 live positions
    try:
        import MetaTrader5 as mt5
        for broker, path in [
            ("IC Markets", "C:/Program Files/MetaTrader 5 IC Markets Global/terminal64.exe"),
            ("FTMO", "C:/Program Files/FTMO Global Markets MT5 Terminal/terminal64.exe"),
        ]:
            if mt5.initialize(path=path):
                positions = mt5.positions_get()
                if positions:
                    for p in positions:
                        sym = p.symbol
                        if sym not in open_positions:
                            open_positions[sym] = {
                                "symbol": sym,
                                "quantity": p.volume,
                                "entry_price": p.price_open,
                                "status": "live",
                                "rsi": 0,
                                "archimedes_score": 0,
                            }
                mt5.shutdown()
    except:
        pass
    
    return list(open_positions.values())

def calculate_position_metrics(position, current_price):
    """Calculate P&L and metrics for a position."""
    entry_price = position.get("entry_price", 0)
    quantity = position.get("quantity", 0)
    
    if entry_price <= 0 or quantity <= 0:
        return None
    
    current_value = quantity * current_price
    entry_value = quantity * entry_price
    pnl = current_value - entry_value
    pnl_pct = (pnl / entry_value) * 100 if entry_value > 0 else 0
    
    # Calculate R-multiple
    stop_loss = position.get("stop_loss_price", entry_price * 0.95)
    risk_per_share = entry_price - stop_loss
    if risk_per_share > 0:
        r_multiple = pnl / (risk_per_share * quantity)
    else:
        r_multiple = 0
    
    return {
        "current_value": current_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "r_multiple": r_multiple,
        "distance_to_stop": ((current_price - stop_loss) / current_price) * 100 if current_price > 0 else 0
    }

def estimate_rsi_from_change(change_24h):
    """Approximate RSI from 24h price change."""
    if change_24h < -8: return 25
    if change_24h < -5: return 30
    if change_24h < -3: return 35
    if change_24h < -1: return 40
    if change_24h < 0: return 45
    if change_24h < 1: return 50
    if change_24h < 3: return 55
    return 65

def estimate_arch(change_24h):
    """Estimate Archimedes volatility score from 24h change."""
    abs_change = abs(change_24h)
    if abs_change > 10: return 0.95
    if abs_change > 7: return 0.90
    if abs_change > 5: return 0.85
    if abs_change > 3: return 0.75
    if abs_change > 1: return 0.60
    return 0.45

def load_data_hub():
    """Load prices from data hub cache."""
    hub_path = "C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/data_hub_cache.json"
    if not os.path.exists(hub_path):
        return {}
    with open(hub_path) as f:
        return json.load(f)

def generate_all_sector_signals(existing_symbols):
    """Generate signals across ALL sectors using data hub prices."""
    signals = []
    hub = load_data_hub()
    
    if not hub:
        return signals
    
    # Sector mapping for futures symbols
    futures_sector_map = {
        "XAUUSD": "Metals", "XAGUSD": "Metals", "XPTUSD": "Metals",
        "US500": "Indices", "US30": "Indices", "USTEC": "Indices",
        "JP225": "Indices", "SPX": "Indices", "NDX": "Indices",
        "WTI_V6_CFD": "Energy", "XTIUSD": "Energy", "XBRUSD": "Energy",
        "WTIUSD": "Energy", "BRENTUSD": "Energy", "COPPER": "Metals",
        "STOXX50E": "Intl Equities", "N225": "Intl Equities", "HSI": "Intl Equities",
        "GDAXI": "Intl Equities", "FTSE": "Intl Equities", "KOSPI": "Intl Equities",
    }
    
    # 1. CRYPTO (from CoinGecko data in hub)
    crypto = hub.get("crypto", {}).get("coins", {})
    for sym, data in crypto.items():
        if not isinstance(data, dict):
            continue
        price = data.get("price", 0)
        if price <= 0 or sym in existing_symbols:
            continue
        change = data.get("change_24h", -2.0)
        # Normalize crypto symbol names to MT5 format
        sym_map = {"BTC": "BTCUSD", "ETH": "ETHUSD", "SOL": "SOLUSD", "XRP": "XRPUSD",
                   "ADA": "ADAUSD", "DOGE": "DOGEUSD", "LTC": "LTCUSD", "DOT": "DOTUSD",
                   "AVAX": "AVAXUSD", "MATIC": "MATICUSD", "LINK": "LINKUSD", "UNI": "UNIUSD",
                   "ATOM": "ATOMUSD", "ARB": "ARBUSD", "FIL": "FILUSD", "ICP": "ICPUSD",
                   "XLM": "XLMUSD", "ALGO": "ALGOUSD", "FTM": "FTMUSD", "APT": "APTUSD",
                   "SUI": "SUIUSD", "NEAR": "NEARUSD", "TRX": "TRXUSD", "SHIB": "SHIBUSD"}
        mt5_sym = sym_map.get(sym, sym + "USD" if not sym.endswith("USD") else sym)
        if mt5_sym in existing_symbols:
            continue
        rsi = estimate_rsi_from_change(change)
        arch = estimate_arch(change)
        if rsi < RSI_OVERSOLD_THRESHOLD and arch >= ARCHIMEDES_MIN_THRESHOLD:
            conviction = "HIGH" if rsi < 35 and arch >= 0.90 else "MODERATE"
            signals.append({
                "rank": 0, "symbol": mt5_sym,
                "signal_strength": "🔥 STRONG BUY" if conviction == "HIGH" else "✅ BUY",
                "conviction": conviction, "action": "BUY",
                "current_price": price, "rsi": rsi,
                "archimedes_score": arch, "change_24h": change,
                "stop_loss": round(price * 0.95, 4),
                "target_price": round(price * 1.15, 4),
                "position_size_pct": 10.0 if conviction == "HIGH" else 7.5,
                "narrative": f"Crypto: RSI {rsi}, Arch {arch:.2f}, {change:+.1f}%",
                "sector": "Crypto", "is_zeus_setup": True,
                "timestamp": datetime.now().isoformat()
            })
    
    # 2. FOREX (from Yahoo data in hub — list or dict format)
    forex_data = hub.get("forex", [])
    if isinstance(forex_data, list):
        for item in forex_data:
            if not isinstance(item, dict):
                continue
            sym = item.get("symbol", "").replace("=X", "")
            price = item.get("price", 0)
            change = item.get("change_24h", -0.5)
            if price <= 0 or sym in existing_symbols:
                continue
            rsi = estimate_rsi_from_change(change)
            arch = estimate_arch(change)
            if rsi < RSI_OVERSOLD_THRESHOLD and arch >= ARCHIMEDES_MIN_THRESHOLD:
                signals.append({
                    "rank": 0, "symbol": sym,
                    "signal_strength": "✅ BUY", "conviction": "MODERATE",
                    "action": "BUY", "current_price": price,
                    "rsi": rsi, "archimedes_score": arch,
                    "change_24h": change,
                    "stop_loss": round(price * 0.97, 4),
                    "target_price": round(price * 1.06, 4),
                    "position_size_pct": 7.5,
                    "narrative": f"Forex: RSI {rsi}, Arch {arch:.2f}",
                    "sector": "Forex", "is_zeus_setup": True,
                    "timestamp": datetime.now().isoformat()
                })
    elif isinstance(forex_data, dict):
        for sym, data in forex_data.get("pairs", {}).items():
            if not isinstance(data, dict):
                continue
            price = data.get("price", 0)
            if price <= 0 or sym in existing_symbols:
                continue
            change = -0.5
            rsi = estimate_rsi_from_change(change)
            arch = estimate_arch(change)
            if rsi < RSI_OVERSOLD_THRESHOLD and arch >= ARCHIMEDES_MIN_THRESHOLD:
                signals.append({
                    "rank": 0, "symbol": sym,
                    "signal_strength": "✅ BUY", "conviction": "MODERATE",
                    "action": "BUY", "current_price": price,
                    "rsi": rsi, "archimedes_score": arch,
                    "change_24h": change,
                    "stop_loss": round(price * 0.97, 4),
                    "target_price": round(price * 1.06, 4),
                    "position_size_pct": 7.5,
                    "narrative": f"Forex: RSI {rsi}, Arch {arch:.2f}",
                    "sector": "Forex", "is_zeus_setup": True,
                    "timestamp": datetime.now().isoformat()
                })
    
    # 3. METALS + INDICES + ENERGY (from futures in hub — list or dict format)
    futures_data = hub.get("futures", [])
    if isinstance(futures_data, list):
        for item in futures_data:
            if not isinstance(item, dict):
                continue
            raw_sym = item.get("symbol", "").replace("=F", "")
            price = item.get("price", 0)
            change = item.get("change_24h", -1.0)
            # Map Yahoo symbols to MT5 names
            sym_map = {"CL": "WTIUSD", "BZ": "BRENTUSD", "GC": "XAUUSD", "SI": "XAGUSD", "PL": "XPTUSD", "HG": "COPPER"}
            sym = sym_map.get(raw_sym, raw_sym)
            if price <= 0 or sym in existing_symbols:
                continue
            rsi = estimate_rsi_from_change(change)
            arch = estimate_arch(change)
            if rsi < RSI_OVERSOLD_THRESHOLD and arch >= ARCHIMEDES_MIN_THRESHOLD:
                sector = futures_sector_map.get(sym, futures_sector_map.get(raw_sym, "Other"))
                conviction = "HIGH" if rsi < 35 and arch >= 0.90 else "MODERATE"
                signals.append({
                    "rank": 0, "symbol": sym,
                    "signal_strength": "✅ BUY", "conviction": conviction,
                    "action": "BUY", "current_price": price,
                    "rsi": rsi, "archimedes_score": arch,
                    "change_24h": change,
                    "stop_loss": round(price * 0.95, 4),
                    "target_price": round(price * 1.10, 4),
                    "position_size_pct": 7.5,
                    "narrative": f"{sector}: RSI {rsi}, Arch {arch:.2f}",
                    "sector": sector, "is_zeus_setup": True,
                    "timestamp": datetime.now().isoformat()
                })
    elif isinstance(futures_data, dict):
        for sym, data in futures_data.get("contracts", {}).items():
            if not isinstance(data, dict):
                continue
            price = data.get("price", 0)
            if price <= 0 or sym in existing_symbols:
                continue
            change = -1.0
            rsi = estimate_rsi_from_change(change)
            arch = estimate_arch(change)
            if rsi < RSI_OVERSOLD_THRESHOLD and arch >= ARCHIMEDES_MIN_THRESHOLD:
                sector = futures_sector_map.get(sym, "Other")
                conviction = "HIGH" if rsi < 35 and arch >= 0.90 else "MODERATE"
                signals.append({
                    "rank": 0, "symbol": sym,
                    "signal_strength": "✅ BUY", "conviction": conviction,
                    "action": "BUY", "current_price": price,
                    "rsi": rsi, "archimedes_score": arch,
                    "change_24h": change,
                    "stop_loss": round(price * 0.95, 4),
                    "target_price": round(price * 1.10, 4),
                    "position_size_pct": 7.5,
                    "narrative": f"{sector}: RSI {rsi}, Arch {arch:.2f}",
                    "sector": sector, "is_zeus_setup": True,
                    "timestamp": datetime.now().isoformat()
                })
    
    # Sort and rank
    signals.sort(key=lambda x: (x["rsi"], -x["archimedes_score"]))
    for i, sig in enumerate(signals, 1):
        sig["rank"] = i
    
    # Filter out non-tradable symbols
    signals = [s for s in signals if s["symbol"] not in NON_TRADABLE]
    
    # 4. INTERNATIONAL EQUITIES (from intl equities in hub)
    intl_data = hub.get("intl_equities", [])
    if isinstance(intl_data, list):
        for item in intl_data:
            if not isinstance(item, dict):
                continue
            sym = item.get("symbol", "").replace("^", "")
            price = item.get("price", 0)
            change = item.get("change_24h", -1.5)
            if price <= 0 or sym in existing_symbols:
                continue
            rsi = estimate_rsi_from_change(change)
            arch = estimate_arch(change)
            if rsi < RSI_OVERSOLD_THRESHOLD and arch >= ARCHIMEDES_MIN_THRESHOLD:
                signals.append({
                    "rank": 0, "symbol": sym,
                    "signal_strength": "✅ BUY", "conviction": "MODERATE",
                    "action": "BUY", "current_price": price,
                    "rsi": rsi, "archimedes_score": arch,
                    "change_24h": change,
                    "stop_loss": round(price * 0.95, 4),
                    "target_price": round(price * 1.10, 4),
                    "position_size_pct": 7.5,
                    "narrative": f"Intl Equities: RSI {rsi}, Arch {arch:.2f}",
                    "sector": "Intl Equities", "is_zeus_setup": True,
                    "timestamp": datetime.now().isoformat()
                })
    elif isinstance(intl_data, dict):
        for sym, data in intl_data.get("indices", {}).items():
            if not isinstance(data, dict):
                continue
            price = data.get("price", 0)
            if price <= 0 or sym in existing_symbols:
                continue
            change = -1.5
            rsi = estimate_rsi_from_change(change)
            arch = estimate_arch(change)
            if rsi < RSI_OVERSOLD_THRESHOLD and arch >= ARCHIMEDES_MIN_THRESHOLD:
                signals.append({
                    "rank": 0, "symbol": sym,
                    "signal_strength": "✅ BUY", "conviction": "MODERATE",
                    "action": "BUY", "current_price": price,
                    "rsi": rsi, "archimedes_score": arch,
                    "change_24h": change,
                    "stop_loss": round(price * 0.95, 4),
                    "target_price": round(price * 1.10, 4),
                    "position_size_pct": 7.5,
                    "narrative": f"Intl Equities: RSI {rsi}, Arch {arch:.2f}",
                    "sector": "Intl Equities", "is_zeus_setup": True,
                    "timestamp": datetime.now().isoformat()
                })
    
    return signals

def generate_fresh_signals(existing_symbols):
    """Generate fresh trading signals using Zeus methodology."""
    signals = generate_all_sector_signals(existing_symbols)
    
    # Filter to only Zeus setups (same as before for compatibility)
    zeus_setups = [s for s in signals if s.get("is_zeus_setup")]
    
    return zeus_setups

def calculate_portfolio_summary(open_positions):
    """Calculate current portfolio metrics."""
    total_value = 0
    total_pnl = 0
    
    for pos in open_positions:
        symbol = pos.get("symbol", "")
        current_price = CURRENT_PRICES.get(symbol, pos.get("entry_price", 0))
        metrics = calculate_position_metrics(pos, current_price)
        
        if metrics:
            total_value += metrics["current_value"]
            total_pnl += metrics["pnl"]
    
    exposure_pct = (total_value / PORTFOLIO_VALUE) * 100 if PORTFOLIO_VALUE > 0 else 0
    remaining_capacity = MAX_EXPOSURE * PORTFOLIO_VALUE - total_value
    
    return {
        "total_portfolio_value": PORTFOLIO_VALUE,
        "total_deployed": total_value,
        "exposure_pct": round(exposure_pct, 2),
        "max_exposure_pct": MAX_EXPOSURE * 100,
        "remaining_capacity_usd": round(max(0, remaining_capacity), 2),
        "total_pnl": round(total_pnl, 2),
        "positions_count": len(open_positions),
        "can_open_new": remaining_capacity > (PORTFOLIO_VALUE * 0.075)  # At least 7.5% for new position
    }

def run_comprehensive_scan():
    """Execute full market scan and generate report."""
    scan_start = datetime.now()
    
    print("=" * 80)
    print("  🐺 OUROTARUS COMPREHENSIVE MARKET SCAN")
    print(f"  Timestamp: {scan_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    # Phase 1: Load open positions
    print("📊 PHASE 1: ANALYZING OPEN POSITIONS")
    print("-" * 80)
    open_positions = load_open_positions()
    
    if not open_positions:
        print("No open positions found.")
        positions_summary = []
    else:
        print(f"Found {len(open_positions)} open position(s):")
        print()
        positions_summary = []
        for pos in open_positions:
            symbol = pos.get("symbol", "UNKNOWN")
            current_price = CURRENT_PRICES.get(symbol, pos.get("entry_price", 0))
            metrics = calculate_position_metrics(pos, current_price)
            
            if metrics:
                status_emoji = "✅" if metrics["pnl"] >= 0 else "⚠️"
                r_status = "🎯" if metrics["r_multiple"] >= 2 else ("🔴" if metrics["r_multiple"] <= -1 else "📊")
                
                pos_summary = {
                    "symbol": symbol,
                    "quantity": pos.get("quantity", 0),
                    "entry_price": pos.get("entry_price", 0),
                    "current_price": current_price,
                    "pnl": metrics["pnl"],
                    "pnl_pct": metrics["pnl_pct"],
                    "r_multiple": metrics["r_multiple"],
                    "rsi": pos.get("rsi", 0),
                    "archimedes": pos.get("archimedes_score", 0),
                    "status": pos.get("status", ""),
                    "distance_to_stop_pct": metrics["distance_to_stop"]
                }
                positions_summary.append(pos_summary)
                
                print(f"  {status_emoji} {symbol}: {pos.get('quantity', 0)} @ ${pos.get('entry_price', 0):.2f}")
                print(f"     Current: ${current_price:.2f} | P&L: ${metrics['pnl']:+.2f} ({metrics['pnl_pct']:+.2f}%)")
                print(f"     R-Multiple: {metrics['r_multiple']:+.2f}R | RSI: {pos.get('rsi', 0)} | Arch: {pos.get('archimedes_score', 0):.2f}")
                to_stop = metrics["distance_to_stop"]
                stop_msg = f"🔴 CLOSE TO STOP" if to_stop < 10 else f"✅ {to_stop:.1f}% from stop"
                print(f"     {stop_msg}")
                print()
    
    # Calculate portfolio summary
    portfolio_summary = calculate_portfolio_summary(open_positions)
    
    print("=" * 80)
    print("📈 PORTFOLIO SUMMARY")
    print("-" * 80)
    print(f"  Total Portfolio: ${PORTFOLIO_VALUE:,.2f}")
    print(f"  Deployed: ${portfolio_summary['total_deployed']:,.2f} ({portfolio_summary['exposure_pct']:.1f}%)")
    print(f"  Max Exposure: {MAX_EXPOSURE * 100:.0f}% (${MAX_EXPOSURE * PORTFOLIO_VALUE:,.2f})")
    print(f"  Remaining Capacity: ${portfolio_summary['remaining_capacity_usd']:,.2f}")
    print(f"  Total P&L: ${portfolio_summary['total_pnl']:+,.2f}")
    print(f"  Open Positions: {portfolio_summary['positions_count']}")
    can_trade = "✅ YES" if portfolio_summary['can_open_new'] else "❌ NO (at/near capacity)"
    print(f"  Can Open New Positions: {can_trade}")
    print()
    
    # Phase 2: Generate fresh signals
    print("=" * 80)
    print("📡 PHASE 2: SCANNING ALL MONITORED ASSETS")
    print("-" * 80)
    existing_symbols = set(p.get("symbol", "") for p in open_positions)
    fresh_signals = generate_fresh_signals(existing_symbols)
    
    zeus_setups = [s for s in fresh_signals if s["is_zeus_setup"]]
    high_conviction = [s for s in fresh_signals if s["conviction"] in ["HIGH", "MODERATE"] and s["position_size_pct"] > 0]
    watch_list = [s for s in fresh_signals if s["conviction"] == "WATCH"]
    
    print(f"  Assets scanned: {len(fresh_signals)}")
    print(f"  Zeus setups found (RSI<{RSI_OVERSOLD_THRESHOLD}, Arch>={ARCHIMEDES_MIN_THRESHOLD}): {len(zeus_setups)}")
    print(f"  High-conviction opportunities: {len(high_conviction)}")
    print(f"  On watch list: {len(watch_list)}")
    print()
    
    # Phase 3: High-conviction alerts
    print("=" * 80)
    print("🔔 HIGH-CONVICTION OPPORTUNITIES ALERT")
    print("-" * 80)
    
    if high_conviction and portfolio_summary['can_open_new']:
        for i, sig in enumerate(high_conviction[:5], 1):
            print(f"  #{i} {sig['symbol']}")
            print(f"      Signal: {sig['signal_strength']} | Conviction: {sig['conviction']}")
            print(f"      Price: ${sig['current_price']:,.2f} | RSI: {sig['rsi']} | Archimedes: {sig['archimedes_score']:.2f}")
            print(f"      24h Change: {sig['change_24h']:+.1f}%")
            print(f"      Entry: ${sig['current_price']:,.2f} | Stop: ${sig['stop_loss']:.2f} | Target: ${sig['target_price']:.2f}")
            print(f"      Position Size: {sig['position_size_pct']}% (${PORTFOLIO_VALUE * sig['position_size_pct'] / 100:.2f})")
            print(f"      Narrative: {sig['narrative']}")
            print()
    elif not portfolio_summary['can_open_new']:
        print("  ⚠️ Portfolio at/near capacity - no new positions available")
        print(f"  Deployed: {portfolio_summary['exposure_pct']:.1f}% / {MAX_EXPOSURE * 100:.0f}% max")
    else:
        print("  No high-conviction opportunities at this time")
        print("  Monitor watch list for developing setups")
    print()
    
    # Watch list
    if watch_list:
        print("=" * 80)
        print("👁 ASSETS ON WATCH (Developing Setups)")
        print("-" * 80)
        for sig in watch_list[:5]:
            print(f"  {sig['symbol']}: RSI {sig['rsi']} | Arch {sig['archimedes_score']:.2f} | {sig['change_24h']:+.1f}%")
            needed_rsi = RSI_OVERSOLD_THRESHOLD - sig['rsi']
            print(f"     Needs: RSI decline of {needed_rsi:.0f}+ points for Zeus setup")
        print()
    
    # Phase 4: Update signal cache
    print("=" * 80)
    print("💾 PHASE 4: UPDATING SIGNAL CACHE")
    print("-" * 80)
    
    cache_data = {
        "cache_updated_at": scan_start.isoformat(),
        "scan_id": f"comprehensive-scan-{scan_start.strftime('%Y%m%d%H%M')}",
        "scan_type": "COMPREHENSIVE_MARKET_SCAN",
        "total_assets_monitored": len(fresh_signals) + len(existing_symbols),
        "zeus_setups_found": len(zeus_setups),
        "high_conviction_opportunities": [
            {
                "rank": sig["rank"],
                "symbol": sig["symbol"],
                "conviction": sig["conviction"],
                "signal_strength": sig["signal_strength"],
                "entry_price": sig["current_price"],
                "rsi": sig["rsi"],
                "archimedes_score": sig["archimedes_score"],
                "change_24h": sig["change_24h"],
                "stop_loss": sig["stop_loss"],
                "target_price": sig["target_price"],
                "position_size_pct": sig["position_size_pct"],
                "narrative": sig["narrative"]
            }
            for sig in high_conviction
        ],
        "watch_list": [
            {
                "symbol": sig["symbol"],
                "rsi": sig["rsi"],
                "archimedes_score": sig["archimedes_score"],
                "change_24h": sig["change_24h"],
                "reason": f"RSI {needed_rsi:.0f} points from Zeus threshold" if (needed_rsi := RSI_OVERSOLD_THRESHOLD - sig['rsi']) > 0 else "Near setup"
            }
            for sig in watch_list[:5]
        ],
        "portfolio_summary": portfolio_summary,
        "open_positions": positions_summary,
        "market_conditions": {
            "overall_sentiment": "OVERSOLD" if len(zeus_setups) >= 3 else "NEUTRAL",
            "market_regime": "Mean-reversion opportunity" if len(zeus_setups) >= 2 else "Trend-following",
            "assets_with_zeus_setup": len(zeus_setups),
            "assets_below_rsi_40": len([s for s in fresh_signals if s["rsi"] < 40]),
            "average_decline": round(sum(s["change_24h"] for s in fresh_signals) / len(fresh_signals), 2) if fresh_signals else 0
        },
        "risk_alerts": []
    }
    
    # Add risk alerts
    if portfolio_summary['exposure_pct'] > 40:
        cache_data["risk_alerts"].append({
            "level": "WARNING",
            "message": f"Portfolio exposure at {portfolio_summary['exposure_pct']:.1f}% - approaching 50% hard cap"
        })
    else:
        cache_data["risk_alerts"].append({
            "level": "INFO",
            "message": f"Portfolio exposure at {portfolio_summary['exposure_pct']:.1f}% - {portfolio_summary['remaining_capacity_usd']:.2f} dry powder available"
        })
    
    if portfolio_summary['total_pnl'] < -PORTFOLIO_VALUE * 0.05:
        cache_data["risk_alerts"].append({
            "level": "ALERT",
            "message": f"Portfolio P&L at ${portfolio_summary['total_pnl']:+,.2f} - monitor for risk management triggers"
        })
    
    # Save cache
    cache_file = Path("signal_cache.json")
    with open(cache_file, "w") as f:
        json.dump(cache_data, f, indent=2)
    
    print(f"  ✅ Signal cache updated: {cache_file}")
    print(f"  Cache timestamp: {cache_data['cache_updated_at']}")
    print(f"  Zeus setups: {cache_data['zeus_setups_found']}")
    print(f"  High-conviction: {len(cache_data['high_conviction_opportunities'])}")
    print()
    
    # Final summary
    print("=" * 80)
    print("📋 SCAN COMPLETE")
    print("-" * 80)
    duration = (datetime.now() - scan_start).total_seconds()
    print(f"  Scan duration: {duration:.2f} seconds")
    print(f"  Total assets analyzed: {cache_data['total_assets_monitored']}")
    print(f"  Zeus setups identified: {len(zeus_setups)}")
    print(f"  High-conviction alerts: {len(high_conviction)}")
    print(f"  Signal cache: UPDATED")
    print()
    
    # Top actionable insights
    if high_conviction:
        print("🎯 TOP ACTIONABLE INSIGHTS:")
        top = high_conviction[0] if high_conviction else None
        if top:
            print(f"  1. {top['symbol']} is the highest-conviction setup")
            print(f"     - RSI {top['rsi']} (deep oversold), Archimedes {top['archimedes_score']:.2f}")
            print(f"     - Down {abs(top['change_24h']):.1f}% in 24h = mean-reversion candidate")
            print(f"     - Recommended size: {top['position_size_pct']}%")
        
        if len(high_conviction) > 1:
            print(f"  2. Additional {len(high_conviction) - 1} high-conviction {'opportunity' if len(high_conviction) == 2 else 'opportunities'} available")
    
    if not portfolio_summary['can_open_new']:
        print()
        print("⚠️ PORTFOLIO CAPACITY NOTE:")
        print(f"  Current exposure: {portfolio_summary['exposure_pct']:.1f}%")
        print("  No new positions until existing ones are reduced or closed")
    
    print()
    print("=" * 80)
    print(f"✅ OUROTARUS MARKET SCAN COMPLETE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    return cache_data

if __name__ == "__main__":
    result = run_comprehensive_scan()
    
    # Save full report
    report_file = f"market_scan_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\n📄 Full report saved to: {report_file}")