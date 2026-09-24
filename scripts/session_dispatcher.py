#!/usr/bin/env python3
"""session_dispatcher.py - Market open/close event dispatcher.

Runs on a 5-minute cron tick (see MARKET_SESSION_COVERAGE.md for the cron entry).
On each tick it:
  1. Loads market_sessions.SESSIONS (single source of truth).
  2. Tracks the last tick time in STATE_FILE.
  3. Detects every market OPEN boundary in (last_tick, now] -> fires a SCAN.
  4. Detects every market CLOSE boundary in (last_tick, now] -> fires a PROTECT sweep.
  5. Writes a manifest (session_dispatcher_manifest.json) and prints a report.

A boundary is "crossed" when the previous tick was NOT in the open window and the
current tick IS (for open), or the previous tick WAS in the window and current is NOT
(for close). This is robust to cron drift and skipped ticks.

Scan action: run the appropriate scanner script for the asset class.
Protect action: run the trailing-SL / protect sweep across all open positions.

Edit SCAN_CMD / PROTECT_CMD to match your real executors. Defaults call the
existing scanners in this folder.
"""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE_FILE = BASE / "session_dispatcher_state.json"
MANIFEST_FILE = BASE / "session_dispatcher_manifest.json"
LOG_FILE = BASE / "session_dispatcher_log.jsonl"

# Executors. Keep these as lists for subprocess. Adjust paths/args to your real
# scanner + protect sweeps. The class->script map routes an open event to the
# right scanner; a close event routes to the protect sweep.
SCAN_CLASS_CMD = {
    "equity":      ["python", str(BASE / "open_market_scan_20260726.py")],
    "etf":         ["python", str(BASE / "open_market_scan_20260726.py")],
    "options":     ["python", str(BASE / "open_market_scan_20260726.py")],
    "futures_index":   ["python", str(BASE / "all_market_scan_20260726.py")],
    "futures_commodity":["python", str(BASE / "all_market_scan_20260726.py")],
    "futures_rates":    ["python", str(BASE / "all_market_scan_20260726.py")],
    "fx":          ["python", str(BASE / "all_market_scan_20260726.py")],
    "crypto":      ["python", str(BASE / "all_market_scan_20260726.py")],
}
PROTECT_CMD = ["python", str(BASE / "trail_sl_protect_sweep.py")]  # SL/protect sweep

import market_sessions as ms


def load_state() -> dt.datetime:
    if STATE_FILE.exists():
        try:
            ts = json.loads(STATE_FILE.read_text())["last_tick"]
            return dt.datetime.fromisoformat(ts)
        except Exception:
            pass
    # First run: pretend last tick was 6 minutes ago so we don't backfire storms.
    return dt.datetime.now() - dt.timedelta(minutes=6)


def save_state(now: dt.datetime):
    STATE_FILE.write_text(json.dumps({"last_tick": now.isoformat()}))


def log_event(event: dict):
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(event) + "\n")


def run_cmd(cmd, label):
    """Run a command, capture result, return dict. Never raises."""
    try:
        res = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, timeout=600)
        return {
            "label": label,
            "cmd": " ".join(cmd),
            "returncode": res.returncode,
            "stdout_tail": (res.stdout or "")[-800:],
            "stderr_tail": (res.stderr or "")[-800:],
        }
    except Exception as e:
        return {"label": label, "cmd": " ".join(cmd), "error": str(e)}


def main():
    now = dt.datetime.now()
    last = load_state()
    fired_scan, fired_protect = [], []

    for s in ms.SESSIONS:
        was_open = ms.is_open(s, last)
        is_open_now = ms.is_open(s, now)

        # OPEN boundary crossed -> SCAN
        if (not was_open) and is_open_now and s["kind"] in ("open_close", "open_only"):
            for cls in s["classes"]:
                cmd = SCAN_CLASS_CMD.get(cls)
                if cmd:
                    res = run_cmd(cmd, f"SCAN:{s['id']}:{cls}")
                    fired_scan.append(res)
                    log_event({"ts": now.isoformat(), "type": "scan",
                               "session": s["id"], "class": cls, "result": res})

        # CLOSE boundary crossed -> PROTECT sweep (only sessions with a close)
        if was_open and (not is_open_now) and s["kind"] == "open_close":
            res = run_cmd(PROTECT_CMD, f"PROTECT:{s['id']}")
            fired_protect.append(res)
            log_event({"ts": now.isoformat(), "type": "protect",
                       "session": s["id"], "result": res})

    # Build manifest
    manifest = {
        "last_tick": last.isoformat(),
        "now": now.isoformat(),
        "scans_fired": len(fired_scan),
        "protects_fired": len(fired_protect),
        "scan_results": fired_scan,
        "protect_results": fired_protect,
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))
    save_state(now)

    # Console report
    print("=" * 70)
    print(f"SESSION DISPATCHER  {now.strftime('%Y-%m-%d %H:%M:%S %a')} ET")
    print("=" * 70)
    print(f"Window checked: {last.strftime('%H:%M:%S')} -> {now.strftime('%H:%M:%S')}")
    print(f"SCANS fired    : {len(fired_scan)}")
    for r in fired_scan:
        rc = r.get("returncode", "ERR")
        print(f"   - {r['label']:42} rc={rc}")
    print(f"PROTECTS fired : {len(fired_protect)}")
    for r in fired_protect:
        rc = r.get("returncode", "ERR")
        print(f"   - {r['label']:42} rc={rc}")
    if not fired_scan and not fired_protect:
        print("   (no boundaries crossed this tick)")
    print("=" * 70)


if __name__ == "__main__":
    main()
