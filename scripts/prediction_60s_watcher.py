#!/usr/bin/env python3
"""
60s Prediction-Market Watcher — polls Kalshi/Polymarket at 60s intervals when armed.
Records discrepancy events to the falsification ledger for Zeus post-trade review.
"""
import json, time, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE = Path(r"C:\Users\bravo-usr1\.hermes\data\prediction_market_state.json")
ARMED = Path(r"C:\Users\bravo-usr1\ARMED_STATUS.json")
OUT = Path(r"C:\Users\bravo-usr1\.hermes\data\prediction_market_60s.json")


def armed():
    if ARMED.exists():
        try:
            return json.loads(ARMED.read_text(encoding="utf-8")).get("armed", False)
        except Exception:
            return False
    return False


def fake_poll():
    # Placeholder: replace with authenticated Kalshi/Polymarket client calls.
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kalshi_p": 0.62,
        "polymarket_p": 0.57,
        "abs_diff": abs(0.62 - 0.57),
        "threshold": 0.20,
        "regime_change_watch": abs(0.62 - 0.57) > 0.20,
        "note": "demo poll values; wire real endpoints here",
    }


def run_once():
    if not armed():
        return {"status": "disarmed", "timestamp": datetime.now(timezone.utc).isoformat()}
    snap = fake_poll()
    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    events = prev.get("events", [])
    if snap.get("regime_change_watch"):
        events.append({
            "timestamp": snap["timestamp"],
            "event": "regime_change_watch",
            "detail": "prediction-market discrepancy > threshold",
        })
    out = {
        "timestamp": snap["timestamp"],
        "armed": True,
        "snap": snap,
        "events": events[-20:],
    }
    STATE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    if OUT.parent.exists():
        OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    res = run_once()
    print(json.dumps(res, indent=2))
