import json, os, sys, time, traceback
from datetime import datetime, timezone

PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
OUT = os.path.join(PROJECT, "workflow")
os.makedirs(OUT, exist_ok=True)

results = {
    "generated": datetime.now(timezone.utc).isoformat(),
    "brokers": {},
    "summary": {
        "total_positions": 0,
        "profitable_count": 0,
        "loser_count": 0,
        "close_candidates": [],
        "review_candidates": [],
        "executable_brokers": [],
        "blocked_brokers": []
    }
}

# ============ IBKR ============
try:
    from ib_insync import IB, util
    util.startLoop()
    ib = IB()
    ib.connect("127.0.0.1", 4002, clientId=2002)
    connected = ib.isConnected()
    accts = ib.managedAccounts()
    summary_bal = None
    positions = []
    if connected and accts:
        acc = accts[0]
        try:
            summary_bal = float(ib.accountSummary(acc).totalValue or 0)
        except Exception:
            summary_bal = None
        try:
            for p in ib.positions():
                positions.append({
                    "symbol": p.contract.symbol,
                    "secType": p.contract.secType,
                    "position": p.position,
                    "avgCost": float(p.avgCost or 0),
                    "unrealized_pnl": float(p.unrealizedPNL or 0),
                })
        except Exception:
            positions = []
    results["brokers"]["ibkr"] = {
        "port": "4002",
        "host": "127.0.0.1",
        "connected": connected,
        "account": accts[0] if accts else None,
        "balance_estimate": summary_bal,
        "positions_count": len(positions),
        "positions": positions,
        "status": "executable" if connected else "unverified"
    }
    ib.disconnect()
except Exception as e:
    results["brokers"]["ibkr"] = {"status": "broken", "error": str(e), "trace": traceback.format_exc().splitlines()[-3:]}

# ============ MT5 brokers ============
MT5_TERMINALS = {
    "ftmo": r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe",
    "capital": r"C:\Program Files\Capital.com MetaTrader 5\terminal64.exe",
}

# Ensure MT5 path exists for import on Windows Python 3.13 in this venv
sys.path.insert(0, os.path.join(PROJECT, "scripts"))

try:
    import MetaTrader5 as mt5
except Exception as e:
    mt5 = None
    _mt5_import_err = str(e)

for name, path in MT5_TERMINALS.items():
    try:
        if mt5 is None:
            raise RuntimeError(f"MT5 import failed: {_mt5_import_err}")
        mt5.shutdown()
        ok = mt5.initialize(path=path, login=0, password="", server="", timeout=15000)
        if not ok:
            results["brokers"][name] = {"status": "broken", "error": f"initialize failed err={mt5.last_error()}"}
            continue
        ai = mt5.account_info()
        positions = mt5.positions_get() or []
        pos_list = []
        for p in positions:
            pos_list.append({
                "symbol": p.symbol,
                "ticket": int(p.ticket),
                "volume": float(p.volume),
                "type": int(p.type),
                "price_open": float(p.price_open),
                "sl": float(p.sl),
                "tp": float(p.tp),
                "profit": float(p.profit),
                "comment": p.comment,
            })
        results["brokers"][name] = {
            "terminal": path,
            "login": int(getattr(ai, 'login', 0) or 0),
            "server": getattr(ai, 'server', ''),
            "trade_allowed": bool(getattr(ai, 'trade_allowed', False)),
            "equity": float(getattr(ai, 'equity', 0) or 0),
            "balance": float(getattr(ai, 'balance', 0) or 0),
            "positions_count": len(pos_list),
            "positions": pos_list,
            "status": "executable" if (ai and ai.trade_allowed) else "order-blocked"
        }
        mt5.shutdown()
    except Exception as e:
        results["brokers"][name] = {"status": "broken", "error": str(e), "trace": traceback.format_exc().splitlines()[-3:]}

# ============ Alpaca ============
try:
    import requests
    from pathlib import Path
    env_path = os.path.join(PROJECT, ".env")
    env = {}
    if os.path.exists(env_path):
        for line in Path(env_path).read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    key = env.get("ALPACA_API_KEY", "")
    secret = env.get("ALPACA_SECRET_KEY", "")
    base = env.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    r = requests.get(f"{base}/v2/account", headers=headers, timeout=20)
    acct = r.json() if r.status_code == 200 else {}
    rpos = requests.get(f"{base}/v2/positions", headers=headers, timeout=20)
    positions = rpos.json() if rpos.status_code == 200 else []
    if isinstance(positions, dict) and "positions" in positions:
        positions = positions["positions"]
    pos_list = []
    for p in positions[:50]:
        pos_list.append({
            "symbol": p.get("symbol"),
            "qty": float(p.get("qty", 0) or 0),
            "avg_entry_price": float(p.get("avg_entry_price", 0) or 0),
            "market_value": float(p.get("market_value", 0) or 0),
            "unrealized_pnl": float(p.get("unrealized_pl", 0) or 0),
            "side": p.get("side"),
        })
    results["brokers"]["alpaca"] = {
        "status": "executable" if r.status_code == 200 else "auth-blocked",
        "status_code": r.status_code,
        "account_id": acct.get("id"),
        "equity": float(acct.get("equity", 0) or 0),
        "cash": float(acct.get("cash", 0) or 0),
        "positions_count": len(pos_list),
        "positions": pos_list
    }
except Exception as e:
    results["brokers"]["alpaca"] = {"status": "broken", "error": str(e), "trace": traceback.format_exc().splitlines()[-3:]}

# ============ eToro ============
try:
    import requests, uuid
    creds_path = os.path.join(PROJECT, "secrets", "broker_creds.json")
    etoro_creds = {}
    if os.path.exists(creds_path):
        etoro_creds = json.loads(Path(creds_path).read_text()).get("etoro", {})
    headers = {
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": etoro_creds.get("api_key", ""),
        "x-user-key": etoro_creds.get("user_key", ""),
        "Accept": "application/json",
    }
    me = requests.get("https://public-api.etoro.com/api/v1/me", headers=headers, timeout=20)
    demo = requests.get("https://public-api.etoro.com/api/v1/trading/info/demo/pnl", headers=headers, timeout=20)
    real = requests.get("https://public-api.etoro.com/api/v1/trading/info/real/pnl", headers=headers, timeout=20)
    demo_positions = demo.json().get("positions", []) if demo.status_code == 200 else []
    real_positions = real.json().get("positions", []) if real.status_code == 200 else []
    results["brokers"]["etoro"] = {
        "status": "executable" if me.status_code == 200 else "auth-blocked",
        "me_status": me.status_code,
        "demo_positions_count": len(demo_positions),
        "real_positions_count": len(real_positions),
        "positions_sample": (demo_positions or real_positions)[:20],
    }
except Exception as e:
    results["brokers"]["etoro"] = {"status": "broken", "error": str(e), "trace": traceback.format_exc().splitlines()[-3:]}

# ============ Kraken ============
try:
    import requests as _req
    pub = _req.get("https://api.kraken.com/0/public/AssetPairs", timeout=20)
    pubj = pub.json() if pub.status_code == 200 else {}
    bal = _req.get("https://api.kraken.com/0/private/Balance", timeout=20, headers={})
    results["brokers"]["kraken"] = {
        "status": "read-only" if pub.status_code == 200 else "broken",
        "public_ok": pub.status_code == 200,
        "private_status": bal.status_code,
    }
except Exception as e:
    results["brokers"]["kraken"] = {"status": "broken", "error": str(e)}

# ============ Summarize ============
for broker, data in results["brokers"].items():
    status = data.get("status", "unknown")
    if status == "executable":
        results["summary"]["executable_brokers"].append(broker)
    else:
        results["summary"]["blocked_brokers"].append(broker)
    positions = data.get("positions") or []
    for p in positions:
        results["summary"]["total_positions"] += 1
        pnl = float(p.get("profit", p.get("unrealized_pnl", 0)) or 0)
        if pnl > 0:
            results["summary"]["profitable_count"] += 1
            results["summary"]["close_candidates"].append({
                "broker": broker,
                "symbol": p.get("symbol", p.get("symbol")),
                "ticket": p.get("ticket"),
                "profit": pnl,
                "side": p.get("side", "LONG" if p.get("type", 0) in (0, 2) else "SHORT")
            })
        else:
            results["summary"]["loser_count"] += 1
            results["summary"]["review_candidates"].append({
                "broker": broker,
                "symbol": p.get("symbol", p.get("symbol")),
                "ticket": p.get("ticket"),
                "pnl": pnl,
                "side": p.get("side", "LONG" if p.get("type", 0) in (0, 2) else "SHORT")
            })

# Save artifacts
now_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
paths = {
    "broker_audit": os.path.join(OUT, f"broker_audit_{now_tag}.json"),
    "broker_audit_latest": os.path.join(OUT, "broker_audit_latest.json"),
    "close_candidates": os.path.join(OUT, f"close_candidates_{now_tag}.json"),
}
with open(paths["broker_audit"], "w") as f:
    json.dump(results, f, indent=2)
with open(paths["broker_audit_latest"], "w") as f:
    json.dump(results, f, indent=2)
with open(paths["close_candidates"], "w") as f:
    json.dump({
        "generated": now_tag,
        "profitable": results["summary"]["close_candidates"],
        "losers_for_review": results["summary"]["review_candidates"],
        "blocked_brokers": results["summary"]["blocked_brokers"],
        "executable_brokers": results["summary"]["executable_brokers"],
    }, f, indent=2)

print(json.dumps({
    "paths": paths,
    "summary": results["summary"]
}, indent=2))
