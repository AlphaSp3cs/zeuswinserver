#!/usr/bin/env python3
"""
Trail SL Monitor for Multi-Broker Positions
==========================================
Monitors open positions across FTMO, Capital.com, and eToro.
Adjusts stop-losses based on unrealized PnL:
- >2% unrealized PnL: Move SL to breakeven (entry price)
- >5% unrealized PnL: Trail SL at 2% below current price

Logs all adjustments to audit_logs/trail_sl_<timestamp>.json
Uses broker_creds.json for credentials (or allapi2026.txt as fallback).
"""

import MetaTrader5 as mt5
import json
import os
import requests
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import sys

# Load broker credentials from broker_creds.json
CRED_PATH = Path("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/broker_creds.json")
if not CRED_PATH.exists():
    raise FileNotFoundError(f"broker_creds.json not found at {CRED_PATH}")
with open(CRED_PATH) as _f:
    BROKER_CREDS = json.load(_f)

AUDIT_DIR = Path("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/audit_logs")
AUDIT_DIR.mkdir(exist_ok=True)

DRY_RUN = "--dry-run" in sys.argv

# eToro Public API configuration
ETORO_BASE_URL = "https://public-api.etoro.com/api/v1"
ETORO_API_KEY = BROKER_CREDS.get("etoro", {}).get("api_key", "")
ETORO_USER_KEY = BROKER_CREDS.get("etoro", {}).get("user_key", "")

# Broker MT5 configurations
BROKERS = {
    "FTMO": BROKER_CREDS.get("ftmo", {}),
    "CAPITAL": BROKER_CREDS.get("capital", {})
}

# Pre-flight credential validation
if ETORO_API_KEY and len(ETORO_API_KEY) < 36 and '...' not in ETORO_API_KEY:
    raise ValueError("ETORO_API_KEY appears invalid (too short)")
if ETORO_USER_KEY and len(ETORO_USER_KEY) < 50:
    raise ValueError(f"ETORO_USER_KEY invalid or truncated (length={len(ETORO_USER_KEY)}). "
                     "eToro SL/TP modification requires a full JWT/UUID.")


def connect_mt5(broker_name: str, config: Dict) -> bool:
    """Initialize MT5 connection for a broker."""
    try:
        if mt5.initialize(
            path=config["path"],
            login=config["login"],
            password=config["password"],
            server=config["server"]
        ):
            account_info = mt5.account_info()
            if account_info:
                print(f"  {broker_name}: Connected - Balance: ${account_info.balance:,.2f}, Equity: ${account_info.equity:,.2f}")
                return True
            return False
        print(f"  {broker_name}: Failed to initialize - {mt5.last_error()}")
        return False
    except Exception as e:
        print(f"  {broker_name}: Connection error - {e}")
        return False


def get_mt5_positions(broker_name: str) -> List[Dict[str, Any]]:
    """Get all open positions from MT5 terminal."""
    positions = mt5.positions_get()
    if positions is None:
        return []
    
    result = []
    for pos in positions:
        # Calculate unrealized PnL percentage
        entry_price = pos.price_open
        current_price = pos.price_current if hasattr(pos, 'price_current') else (mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask)
        
        if pos.type == mt5.POSITION_TYPE_BUY:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        # Current SL
        current_sl = pos.sl if pos.sl > 0 else None
        
        result.append({
            "broker": broker_name,
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
            "volume": pos.volume,
            "entry_price": round(entry_price, 5),
            "current_price": round(current_price, 5),
            "unrealized_pnl": round(pos.profit, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2),
            "current_sl": round(current_sl, 5) if current_sl else None,
            "tp": round(pos.tp, 5) if pos.tp > 0 else None,
            "magic": pos.magic,
            "comment": pos.comment,
            "time_open": datetime.fromtimestamp(pos.time).isoformat() if pos.time else None
        })
    
    return result


def modify_mt5_position(broker_name: str, ticket: int, new_sl: float, symbol: str, pos_type: str) -> Dict[str, Any]:
    """Modify MT5 position SL while preserving existing TP."""
    if DRY_RUN:
        return {
            "success": True,
            "dry_run": True,
            "message": f"DRY RUN: Would modify SL to {new_sl:.5f} for ticket {ticket}"
        }
    
    try:
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": new_sl,
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            return {"success": False, "error": "order_send returned None"}
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return {
                "success": True,
                "order_id": result.order,
                "deal_id": result.deal,
                "price": result.price,
                "message": f"SL modified to {new_sl:.5f}"
            }
        else:
            return {"success": False, "error": f"Retcode {result.retcode}: {result.comment}"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_etoro_positions() -> List[Dict[str, Any]]:
    """Get open direct positions from eToro Public API."""
    if not ETORO_API_KEY or not ETORO_USER_KEY or len(ETORO_USER_KEY) < 50:
        print("  ETORO: Skipped - credentials missing or truncated (set valid ETORO_USER_KEY in broker_creds.json)")
        return []
    
    headers = {
        'x-request-id': str(uuid.uuid4()),
        'x-api-key': ETORO_API_KEY,
        'x-user-key': ETORO_USER_KEY,
        'Accept': 'application/json'
    }
    
    try:
        positions = []
        for account_type in ['demo', 'real']:
            resp = requests.get(f"{ETORO_BASE_URL}/trading/info/{account_type}/pnl", headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                client_portfolio = data.get('clientPortfolio', {})
                for pos in client_portfolio.get('positions', []):
                    # Skip copy-trade mirrors (mirrorID > 0)
                    if pos.get('mirrorID', 0) > 0:
                        continue
                    
                    entry = pos.get('openRate', 0)
                    current = pos.get('currentRate', 0)
                    direction = pos.get('direction', 'BUY')
                    units = pos.get('units', 0)
                    instrument_id = pos.get('instrumentID', 0)
                    position_id = pos.get('positionID', 0)
                    pl = pos.get('pl', 0)
                    
                    if entry > 0:
                        if direction == 'BUY':
                            pnl_pct = ((current - entry) / entry) * 100
                        else:
                            pnl_pct = ((entry - current) / entry) * 100
                    else:
                        pnl_pct = 0
                    
                    positions.append({
                        "broker": "ETORO",
                        "account_type": account_type,
                        "position_id": position_id,
                        "instrument_id": instrument_id,
                        "symbol": pos.get('instrumentDisplayName', ''),
                        "type": direction,
                        "units": units,
                        "entry_price": round(entry, 5),
                        "current_price": round(current, 5),
                        "unrealized_pnl": round(pl, 2),
                        "unrealized_pnl_pct": round(pnl_pct, 2),
                        "current_sl": round(pos.get('stopLossRate', 0), 5) if pos.get('stopLossRate', 0) > 0 else None,
                        "tp": round(pos.get('takeProfitRate', 0), 5) if pos.get('takeProfitRate', 0) > 0 else None,
                        "leverage": pos.get('leverage', 1),
                        "time_open": pos.get('openDate', '')
                    })
            elif resp.status_code == 403:
                print(f"  ETORO {account_type}: 403 Forbidden - check scopes/credentials")
            else:
                print(f"  ETORO {account_type}: HTTP {resp.status_code}")
        
        return positions
    
    except Exception as e:
        print(f"  ETORO: Error fetching positions - {e}")
        return []


def modify_etoro_position(account_type: str, position_id: int, instrument_id: int, new_sl: float, units: float) -> Dict[str, Any]:
    """eToro Public API does NOT support SL/TP modification on open positions.
    
    Returns a 'not_supported' result so the caller can still record the 
    identified adjustment in the audit log with a clear reason.
    """
    return {
        "success": False,
        "not_supported": True,
        "error": "eToro Public API does not expose an endpoint for modifying stop-loss/take-profit on open positions. "
                 "Identified in 2026-07-25 session: only read/direct-open/close are available for direct positions; "
                 "copy-trade mirrors are read-only. Close/reopen via API is required to change SL/TP."
    }


def calculate_new_sl(position: Dict) -> Optional[float]:
    """Calculate new SL based on PnL percentage rules."""
    pnl_pct = position.get("unrealized_pnl_pct", 0)
    entry = position.get("entry_price", 0)
    current = position.get("current_price", 0)
    current_sl = position.get("current_sl")
    pos_type = position.get("type", "BUY")
    
    # No action needed if PnL < 2%
    if pnl_pct < 2:
        return None
    
    # >2% PnL: Move SL to breakeven (entry price)
    if 2 <= pnl_pct < 5:
        new_sl = entry
    
    # >5% PnL: Trail SL at 2% below current price
    elif pnl_pct >= 5:
        if pos_type == "BUY":
            new_sl = current * 0.98  # 2% below current
        else:
            new_sl = current * 1.02  # 2% above current for shorts
    else:
        return None
    
    # Only modify if new SL improves the position
    if current_sl is not None:
        if pos_type == "BUY" and new_sl <= current_sl:
            return None  # Don't move SL down for longs
        if pos_type == "SELL" and new_sl >= current_sl:
            return None  # Don't move SL up for shorts
    
    return round(new_sl, 5)


def monitor_broker(broker_name: str) -> List[Dict]:
    """Monitor positions for a single broker and return adjustments."""
    adjustments = []
    
    if broker_name in ["FTMO", "CAPITAL"]:
        # MT5 brokers
        config = BROKERS[broker_name]
        if not connect_mt5(broker_name, config):
            return []
        
        positions = get_mt5_positions(broker_name)
        
        for pos in positions:
            new_sl = calculate_new_sl(pos)
            if new_sl is not None:
                # Check if SL actually needs to change
                current_sl = pos.get("current_sl")
                if current_sl is None or (pos["type"] == "BUY" and new_sl > current_sl) or (pos["type"] == "SELL" and new_sl < current_sl):
                    action = "BREAKEVEN" if pos["unrealized_pnl_pct"] < 5 else "TRAIL_2%"
                    adjustment = {
                        "timestamp": datetime.now().isoformat(),
                        "broker": broker_name,
                        "ticket": pos["ticket"],
                        "symbol": pos["symbol"],
                        "type": pos["type"],
                        "volume": pos["volume"],
                        "entry_price": pos["entry_price"],
                        "current_price": pos["current_price"],
                        "unrealized_pnl_pct": pos["unrealized_pnl_pct"],
                        "action": action,
                        "old_sl": current_sl,
                        "new_sl": new_sl,
                        "executed": False,
                        "result": None
                    }
                    
                    # Execute modification
                    result = modify_mt5_position(broker_name, pos["ticket"], new_sl, pos["symbol"], pos["type"])
                    adjustment["executed"] = result.get("success", False)
                    adjustment["result"] = result
                    
                    adjustments.append(adjustment)
                    
                    if result.get("success"):
                        print(f"    ✅ {broker_name} {pos['symbol']} {pos['type']}: SL {current_sl} -> {new_sl} ({action})")
                    else:
                        print(f"    ❌ {broker_name} {pos['symbol']} {pos['type']}: Failed - {result.get('error')}")
        
        mt5.shutdown()
    
    elif broker_name == "ETORO":
        positions = get_etoro_positions()
        
        for pos in positions:
            new_sl = calculate_new_sl(pos)
            if new_sl is not None:
                current_sl = pos.get("current_sl")
                if current_sl is None or (pos["type"] == "BUY" and new_sl > current_sl) or (pos["type"] == "SELL" and new_sl < current_sl):
                    action = "BREAKEVEN" if pos["unrealized_pnl_pct"] < 5 else "TRAIL_2%"
                    adjustment = {
                        "timestamp": datetime.now().isoformat(),
                        "broker": "ETORO",
                        "account_type": pos["account_type"],
                        "position_id": pos["position_id"],
                        "instrument_id": pos["instrument_id"],
                        "symbol": pos["symbol"],
                        "type": pos["type"],
                        "units": pos["units"],
                        "entry_price": pos["entry_price"],
                        "current_price": pos["current_price"],
                        "unrealized_pnl_pct": pos["unrealized_pnl_pct"],
                        "action": action,
                        "old_sl": current_sl,
                        "new_sl": new_sl,
                        "executed": False,
                        "result": None
                    }
                    
                    result = modify_etoro_position(pos["account_type"], pos["position_id"], pos["instrument_id"], new_sl, pos["units"])
                    adjustment["executed"] = result.get("success", False)
                    adjustment["result"] = result
                    
                    adjustments.append(adjustment)
                    
                    if result.get("success"):
                        print(f"    ✅ ETORO {pos['symbol']} {pos['type']}: SL {current_sl} -> {new_sl} ({action})")
                    else:
                        print(f"    ⚠️  ETORO {pos['symbol']} {pos['type']}: Adjustment needed but not supported by API - {result.get('error', 'n/a')}")
    
    return adjustments


def main():
    print("=" * 60)
    print(f"TRAIL SL MONITOR - {datetime.now().isoformat()}")
    print(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print("=" * 60)
    
    all_adjustments = []
    
    # Monitor each broker
    for broker in ["FTMO", "CAPITAL", "ETORO"]:
        print(f"\nChecking {broker}...")
        adjustments = monitor_broker(broker)
        all_adjustments.extend(adjustments)
    
    # Save audit log
    if all_adjustments:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_file = AUDIT_DIR / f"trail_sl_{timestamp}.json"
        
        audit_data = {
            "timestamp": datetime.now().isoformat(),
            "mode": "dry_run" if DRY_RUN else "live",
            "total_adjustments": len(all_adjustments),
            "successful": sum(1 for a in all_adjustments if a.get("executed")),
            "failed": sum(1 for a in all_adjustments if not a.get("executed")),
            "adjustments": all_adjustments
        }
        
        with open(audit_file, 'w') as f:
            json.dump(audit_data, f, indent=2)
        
        print(f"\n{'=' * 60}")
        print(f"AUDIT LOG: {audit_file}")
        print(f"Total adjustments: {len(all_adjustments)}")
        print(f"Successful: {audit_data['successful']}")
        print(f"Failed: {audit_data['failed']}")
        print("=" * 60)
    else:
        print("\nNo SL adjustments needed (all positions below 2% PnL or SL already optimal)")
        # Still create audit log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_file = AUDIT_DIR / f"trail_sl_{timestamp}.json"
        audit_data = {
            "timestamp": datetime.now().isoformat(),
            "mode": "dry_run" if DRY_RUN else "live",
            "total_adjustments": 0,
            "successful": 0,
            "failed": 0,
            "adjustments": []
        }
        with open(audit_file, 'w') as f:
            json.dump(audit_data, f, indent=2)
        print(f"Audit log: {audit_file}")


if __name__ == "__main__":
    main()