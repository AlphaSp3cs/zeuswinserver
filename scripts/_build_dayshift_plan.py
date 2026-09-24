import json, os, sys
from datetime import datetime, timezone
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
vault = os.path.join(PROJECT, "vault")
workflow = os.path.join(PROJECT, "workflow")
os.makedirs(vault, exist_ok=True)
os.makedirs(workflow, exist_ok=True)

# Load existing state artifacts
ibkr_path = os.path.join(vault, "ibkr_state_now.json")
ibkr = {}
if os.path.exists(ibkr_path):
    try:
        ibkr = json.loads(open(ibkr_path, encoding='utf-8').read())
    except Exception:
        ibkr = {}

# Load latest sector scan
from pathlib import Path
sector_files = sorted(Path('loads/Scan protocol').glob('sector_scan_results_*.json'))
sector = {}
if sector_files:
    try:
        sector = json.loads(sector_files[-1].read_text(encoding='utf-8'))
    except Exception:
        sector = {}

# Top scanner longs/shorted from latest sector scan as WATCHLIST ONLY
qlongs = sector.get('qualified_longs', [])[:5]
qshorts = sector.get('qualified_shorts', [])[:5]

# FTMO: currently flat after cleanup
ftmo_state = {
    "status": "executable",
    "login": int(os.environ.get('FTMO_MT5_LOGIN', '0')),
    "open_positions": 0,
    "balance": 201281.25,
    "equity": 201020.14,
    "note": "Closed profitable tickets and invalid loser ADAUSD; portfolio not blown."
}

# IBKR: executable, need user confirmation to add positions
ibkr_summary = ibkr.get('summary', {})
ibkr_plan = {
    "account": ibkr.get('account'),
    "net_liquidation": ibkr_summary.get('NetLiquidation'),
    "available_funds": ibkr_summary.get('AvailableFunds'),
    "buying_power": ibkr_summary.get('BuyingPower'),
    "positions_count": ibkr.get('positions_count', 0),
    "action": "PLAN_ONLY",
    "reason": "Need user confirmation before adding IBKR equity positions."
}

# Blocked brokers snapshot
blocked = {
    "capital": "order-blocked or unreachable this tick",
    "alpaca": "auth-blocked this tick",
    "etoro": "auth-blocked this tick",
    "kraken": "read-only this tick"
}

# Equity growth candidates: use existing IBKR holdings as baseline context
# New entries deferred until user confirms broker/symbols
candidates = []
for pos in (ibkr.get('positions') or [])[:8]:
    candidates.append({
        "symbol": pos.get('symbol'),
        "secType": pos.get('secType'),
        "position": pos.get('position'),
        "status": "HOLD"
    })

# Scanner watchlist only
scanner_watch = []
for x in qlongs:
    scanner_watch.append({"symbol": x.get('symbol'), "side": "LONG", "entry": x.get('trade_zones',{}).get('entry',{}).get('primary'), "sl": x.get('trade_zones',{}).get('stop_loss',{}).get('price'), "note": "SCANNER_WATCH_ONLY"})
for x in qshorts:
    scanner_watch.append({"symbol": x.get('symbol'), "side": "SHORT", "entry": x.get('trade_zones',{}).get('entry',{}).get('primary'), "sl": x.get('trade_zones',{}).get('stop_loss',{}).get('price'), "note": "SCANNER_WATCH_ONLY"})

out = {
    "generated": datetime.now(timezone.utc).isoformat(),
    "mode": "dayshift_manual_plan",
    "ftmo": ftmo_state,
    "ibkr": ibkr_plan,
    "blocked_brokers": blocked,
    "existing_candidates": candidates,
    "scanner_watchlist": scanner_watch,
    "notes": [
        "Scanner artifact is stale/crypto-only and produced 0 setups in fresh run.",
        "No new trades executed without explicit user approval.",
        "Equity growth actions are planning-only until symbols and sizing are confirmed."
    ]
}
path = os.path.join(workflow, f"dayshift_manual_plan_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
with open(path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2)
print(path)
