#!/usr/bin/env python3
"""trail_sl_protect_sweep.py - Read-only SL/TP protect sweep.

Called by session_dispatcher at every market CLOSE (see session_dispatcher.py).
It does NOT place orders. It:
  1. Runs the existing all_market_scan to pull live open positions from every
     reachable broker (Capital MT5, FTMO MT5, Alpaca, eToro).
  2. Flags any position missing SL or TP as "NAKED" (violates no-naked rule).
  3. Writes a protect manifest (protect_sweep_<DATE>.json) + console alert.

For a live re-arm (placing protective orders), wire PROTECT_MODE='live' and
implement the broker-specific SL/TP submit using the credentials already in .env.
Default is REPORT-ONLY to avoid accidental fills.
"""

import json
import subprocess
import sys
import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCAN_SCRIPT = BASE / "all_market_scan_20260726.py"
MANIFEST = BASE / f"protect_sweep_{dt.date.today().isoformat()}.json"

PROTECT_MODE = "report"  # "report" (default, safe) | "live" (would place orders)


def collect_positions() -> dict:
    """Run all_market_scan and parse its JSON results for open positions."""
    res = subprocess.run(
        [sys.executable, str(SCAN_SCRIPT)], cwd=str(BASE),
        capture_output=True, text=True, timeout=600,
    )
    results_path = BASE / "all_market_scan_results_2026-07-26.json"
    # all_market_scan writes a fixed-name file; find latest by mtime if renamed.
    if not results_path.exists():
        candidates = sorted(BASE.glob("all_market_scan_results_*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            results_path = candidates[0]
    if not results_path.exists():
        return {"error": "all_market_scan output not found", "stderr": res.stderr[-500:]}
    data = json.loads(results_path.read_text())
    return data.get("positions", {})


def analyze(positions: dict) -> dict:
    naked, covered = [], []
    for broker, plist in positions.items():
        for p in (plist or []):
            sl = p.get("sl")
            tp = p.get("tp")
            is_naked = (sl in (None, 0)) or (tp in (None, 0))
            row = {
                "broker": broker,
                "symbol": p.get("symbol"),
                "ticket": p.get("ticket"),
                "type": p.get("type"),
                "sl": sl,
                "tp": tp,
                "profit": p.get("profit"),
            }
            (naked if is_naked else covered).append(row)
    return {
        "generated_at": dt.datetime.now().isoformat(),
        "mode": PROTECT_MODE,
        "brokers_checked": list(positions.keys()),
        "total_open": sum(len(v or []) for v in positions.values()),
        "naked_count": len(naked),
        "covered_count": len(covered),
        "naked": naked,
        "covered": covered[:20],  # truncate for manifest size
    }


def main():
    positions = collect_positions()
    if "error" in positions:
        print("PROTECT SWEEP ERROR:", positions["error"])
        print(positions.get("stderr", ""))
        sys.exit(1)
    report = analyze(positions)
    MANIFEST.write_text(json.dumps(report, indent=2, default=str))

    print("=" * 70)
    print(f"PROTECT SWEEP  {report['generated_at']}  mode={report['mode']}")
    print("=" * 70)
    print(f"Brokers checked : {', '.join(report['brokers_checked']) or 'NONE'}")
    print(f"Total open     : {report['total_open']}")
    print(f"Covered (SL+TP): {report['covered_count']}")
    print(f"NAKED          : {report['naked_count']}")
    if report["naked"]:
        print("-" * 70)
        print("NAKED POSITIONS (no SL/TP) => RE-ARM REQUIRED:")
        for n in report["naked"]:
            print(f"   {n['broker']:14} {n['symbol']:10} ticket={n['ticket']} "
                  f"sl={n['sl']} tp={n['tp']}")
    else:
        print("All positions have SL+TP. Pack is protected. Awuuuu!!!!")
    print("=" * 70)
    print(f"Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()