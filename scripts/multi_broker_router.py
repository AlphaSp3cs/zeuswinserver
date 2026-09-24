#!/usr/bin/env python3
"""
Multi-Broker Router — Zeus Trade Firm
Routes signals to correct broker by sector. Covers all asset classes.
Brokers: IBKR (US equities/options), IC Markets (CFDs: crypto/forex/metals/energy/indices), Capital demo (backup)
"""
import json, os, sys, subprocess, time
from datetime import datetime
from pathlib import Path

ROOT = Path("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm")
CONFIG = ROOT / "workflow" / "broker_router_config.json"

# Sector → broker priority (first available wins)
# FTMO = challenge account (careful sizing), IC Markets = CFDs, IBKR = US equities/options
SECTOR_BROKERS = {
    "Crypto":      ["ic_markets", "ftmo"],
    "Forex":       ["ftmo", "ic_markets"],
    "Metals":      ["ic_markets", "ftmo"],
    "Energy":      ["ic_markets", "ftmo"],
    "Indices":     ["ftmo", "ic_markets"],
    "US Stocks":   ["ibkr"],
    "US Options":  ["ibkr"],
    "ETF":         ["ibkr"],
    "Biotech":     ["ibkr"],
    "Finance":     ["ibkr"],
    "Retail":      ["ibkr"],
    "Tech":        ["ibkr"],
    "Penny Stocks":["ftmo"],
}

BROKER_TERMINALS = {
    "ftmo":        "C:/Program Files/FTMO Global Markets MT5 Terminal/terminal64.exe",
    "ic_markets":  "C:/Program Files/MetaTrader 5 IC Markets Global/terminal64.exe",
    "capital_demo":"C:/Program Files/Capital.com MetaTrader 5/terminal64.exe",
}

BROKER_SERVERS = {
    "ftmo":        "FTMO-Demo",
    "ic_markets":  "ICMarketsSC-Demo",  # adjust per your IC account
    "capital_demo":"Capital.ComBah-Demo",
}

IBKR_HOST = "127.0.0.1"
IBKR_PORT = 7497
IBKR_CLIENT_ID = 2002

def classify_sector(symbol: str) -> str:
    """Classify symbol into sector for routing."""
    crypto_syms = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "AVAX", "LINK", "MATIC", "UNI", "LTC", "XMR", "ZEC", "ARB", "LSK", "SUI", "INJ", "MKR", "AAVE", "SHIB", "PEPE", "NEAR", "ATOM"}
    metals_syms = {"XAU", "XAG", "XPT", "XPD", "GOLD", "SILVER", "PLATINUM", "PALLADIUM"}
    forex_syms  = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "EURCHF", "GBPCHF", "AUDNZD", "USDSGD"}
    energy_syms = {"WTI", "BRENT", "USO", "XLE", "XOM", "CVX", "EOG"}
    index_syms  = {"SPX", "NDX", "DJI", "AUS200", "HK50", "JP225", "GER40", "UK100", "EUSTX50"}
    # US equities / ETFs
    etf_syms = {"SPY", "QQQ", "DIA", "IWM", "VTI", "XLF", "XLV", "XLP", "XLU", "XLE", "XLY", "XLK", "XLI", "XLB", "XOP", "IEMG", "EFA", "VEA", "AGG", "TLT", "IEF", "SHY", "BIL", "GLD", "SLV", "USO", "VNQ"}
    biotech_syms = {"MRNA", "CRSP", "BIIB", "REGN", "VRTX", "GILD", "BMRN", "ALNY", "INSM", "SRPT"}
    finance_syms = {"GS", "MS", "JPM", "BAC", "WFC", "C", "BLK", "SPGI", "MCO", "AXP", "USB", "PNC", "TFC"}
    retail_syms  = {"WMT", "TGT", "COST", "HD", "LOW", "M", "KSS", "TJX", "DG", "DLTR", "DAL", "UAL", "AAL", "LUV", "JBLU", "ALK"}
    tech_syms    = {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AMD", "INTC", "PLTR", "CRM", "ORCL", "NOW", "SNOW", "CRWD", "NET", "DDOG", "ZS", "PANW", "FTNT", "CYBR"}

    s = symbol.upper()
    # Check forex pairs BEFORE stripping USD
    if s in forex_syms:      return "Forex"
    # Strip stablecoin/fiat suffixes — longest first (USDT before USD)
    for suffix in ("USDT", "USDC", "USD"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    s = s.split("-")[0].split("/")[0]
    if s in crypto_syms:     return "Crypto"
    if s in metals_syms:     return "Metals"
    if s in energy_syms:     return "Energy"
    if s in index_syms:      return "Indices"
    if s in etf_syms:        return "ETF"
    if s in biotech_syms:    return "Biotech"
    if s in finance_syms:    return "Finance"
    if s in retail_syms:     return "Retail"
    if s in tech_syms:       return "Tech"
    return "US Stocks"  # default

def get_mt5_terminal(broker: str) -> str:
    return BROKER_TERMINALS.get(broker, "")

def get_mt5_server(broker: str) -> str:
    return BROKER_SERVERS.get(broker, "")

def check_ibkr() -> bool:
    """Check if IBKR gateway is reachable."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((IBKR_HOST, IBKR_PORT))
        s.close()
        return True
    except:
        return False

def check_mt5(broker: str) -> bool:
    """Check if MT5 terminal is running."""
    terminal = get_mt5_terminal(broker)
    if not terminal or not os.path.exists(terminal):
        return False
    # Check if process is running
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq terminal64.exe"],
            capture_output=True, text=True, timeout=5
        )
        return "terminal64.exe" in result.stdout
    except:
        return False

def route_trade(symbol: str, action: str, quantity: float, stop_loss: float, take_profit: float) -> dict:
    """
    Route a trade to the correct broker based on sector classification.
    Returns routing result with broker, status, and execution details.
    """
    sector = classify_sector(symbol)
    brokers = SECTOR_BROKERS.get(sector, ["ibkr"])
    result = {
        "symbol": symbol,
        "action": action,
        "sector": sector,
        "quantity": quantity,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "timestamp": datetime.now().isoformat(),
        "routed_to": None,
        "status": "pending",
        "details": []
    }

    for broker in brokers:
        if broker == "ibkr":
            if check_ibkr():
                result["routed_to"] = "ibkr"
                result["status"] = "routed"
                result["details"].append(f"IBKR gateway reachable at {IBKR_HOST}:{IBKR_PORT}")
                result["execution_method"] = "ib_insync"
                return result
            else:
                result["details"].append("IBKR gateway not responding")
        elif broker in BROKER_TERMINALS:
            if check_mt5(broker):
                result["routed_to"] = broker
                result["status"] = "routed"
                result["details"].append(f"MT5 terminal running: {broker}")
                result["execution_method"] = "mt5_python_api"
                result["mt5_server"] = get_mt5_server(broker)
                return result
            else:
                result["details"].append(f"MT5 terminal not running: {broker}")

    result["status"] = "failed"
    result["details"].append("No available broker for sector")
    return result

def execute_mt5(broker: str, symbol: str, action: str, volume: float, sl: float, tp: float) -> dict:
    """
    Execute trade via MT5 Python API.
    Requires MT5 terminal running with correct broker.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"status": "error", "message": "MetaTrader5 library not installed"}

    terminal = get_mt5_terminal(broker)
    server = get_mt5_server(broker)

    # Initialize MT5 — try path-only first (uses saved login), fall back to server+path
    if not mt5.initialize(path=terminal):
        if not mt5.initialize(server=server, path=terminal):
            return {"status": "error", "message": f"MT5 initialize failed: {mt5.last_error()}"}

    # Get symbol info
    info = mt5.symbol_info(symbol)
    if info is None:
        mt5.shutdown()
        return {"status": "error", "message": f"Symbol {symbol} not found on {server}"}

    # Get current price
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        mt5.shutdown()
        return {"status": "error", "message": f"No tick for {symbol}"}

    # Determine action
    is_buy = action.upper() in ("BUY", "LONG")
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    price = tick.ask if is_buy else tick.bid

    # Calculate SL/TP
    sl_price = round(price * (1 - sl), info.digits) if is_buy else round(price * (1 + sl), info.digits)
    tp_price = round(price * (1 + tp), info.digits) if is_buy else round(price * (1 - tp), info.digits)

    # Build order
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": 20,
        "magic": 20260923,
        "comment": "zeus_router",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    mt5.shutdown()

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"status": "error", "message": f"Order failed: {result.retcode} - {result.comment}"}

    return {
        "status": "filled",
        "broker": broker,
        "symbol": symbol,
        "action": action,
        "volume": volume,
        "price": price,
        "sl": sl_price,
        "tp": tp_price,
        "deal": result.deal,
        "order": result.order,
    }

def main():
    if len(sys.argv) < 5:
        print("Usage: multi_broker_router.py <symbol> <action> <quantity> <stop_loss> [take_profit]")
        print("Example: multi_broker_router.py BTCUSD BUY 0.1 0.03 0.06")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    action = sys.argv[2].upper()
    quantity = float(sys.argv[3])
    stop_loss = float(sys.argv[4])
    take_profit = float(sys.argv[5]) if len(sys.argv) > 5 else stop_loss * 2

    sector = classify_sector(symbol)
    print(f"=== Zeus Multi-Broker Router ===")
    print(f"Symbol: {symbol} | Sector: {sector}")
    print(f"Action: {action} | Qty: {quantity} | SL: {stop_loss} | TP: {take_profit}")
    print()

    # Check broker availability
    print("Broker Status:")
    print(f"  IBKR Gateway ({IBKR_HOST}:{IBKR_PORT}): {'UP' if check_ibkr() else 'DOWN'}")
    for broker in ["ic_markets", "capital_demo", "ftmo"]:
        terminal = get_mt5_terminal(broker)
        exists = os.path.exists(terminal) if terminal else False
        running = check_mt5(broker)
        print(f"  {broker}: terminal={'YES' if exists else 'NO'} running={'YES' if running else 'NO'}")
    print()

    # Route
    result = route_trade(symbol, action, quantity, stop_loss, take_profit)
    print(f"Routed to: {result['routed_to']}")
    print(f"Status: {result['status']}")
    for d in result["details"]:
        print(f"  → {d}")

    if result["status"] == "routed":
        print()
        print("To execute, run:")
        if result.get("execution_method") == "mt5_python_api":
            print(f'  python multi_broker_router.py {symbol} {action} {quantity} {stop_loss} {take_profit}')

    # Save routing log
    log_file = ROOT / "workflow" / "routing_log.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(result) + "\n")

    print(f"\nLog: {log_file}")

if __name__ == "__main__":
    main()
