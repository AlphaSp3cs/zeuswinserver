"""carry_forward_memory.py

Lightweight workflow memory layer for OuroTaurus.
- Adds durable carry-forward state for scans, setups, and trade outcomes.
- No replacement of existing scanners/backtests; pure upgrade layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any


WORKFLOW_DIR = Path("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/workflow")
TRADE_MEMORY_PATH = WORKFLOW_DIR / "trade_memory.json"
SCAN_STATE_PATH = WORKFLOW_DIR / "scan_state_carry.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_trade_memory() -> dict:
    return _load_json(TRADE_MEMORY_PATH, {
        "updated_at": _now_utc(),
        "entries": [],
        "outcomes": [],
        "current_state": {},
    })


def save_trade_memory(memory: dict) -> None:
    memory["updated_at"] = _now_utc()
    _save_json(TRADE_MEMORY_PATH, memory)


def load_scan_state() -> dict:
    return _load_json(SCAN_STATE_PATH, {
        "updated_at": _now_utc(),
        "last_scan_cycle": None,
        "carried_setups": [],
        "invalidated_setups": [],
        "duplicate_keys": [],
    })


def save_scan_state(state: dict) -> None:
    state["updated_at"] = _now_utc()
    _save_json(SCAN_STATE_PATH, state)


def setup_key(setup: dict) -> str:
    symbol = setup.get("symbol") or setup.get("ticker") or setup.get("asset") or ""
    side = (setup.get("side") or setup.get("direction") or "").upper()
    tf = setup.get("timeframe") or setup.get("tf") or ""
    strategy = setup.get("strategy") or setup.get("signal_tag") or ""
    return "|".join([str(symbol), str(side), str(tf), str(strategy)])


def dedupe_setups(setups: list[dict], prior_keys: list[str]) -> tuple[list[dict], list[str]]:
    new_keys: list[str] = []
    unique: list[dict] = []
    for setup in setups:
        key = setup_key(setup)
        if key in prior_keys or key in new_keys:
            continue
        new_keys.append(key)
        unique.append(setup)
    return unique, new_keys


def append_outcome(memory: dict, outcome: dict) -> None:
    outcomes = memory.setdefault("outcomes", [])
    outcomes.append({
        "recorded_at": _now_utc(),
        "outcome": outcome,
    })
    if len(outcomes) > 500:
        memory["outcomes"] = outcomes[-500:]


def mark_carried(state: dict, setups: list[dict]) -> None:
    state["carried_setups"] = [setup_key(s) for s in setups]


def mark_invalidated(state: dict, setups: list[dict]) -> None:
    keys = [setup_key(s) for s in setups]
    invalidated = state.setdefault("invalidated_setups", [])
    invalidated.extend(keys)
    state["invalidated_setups"] = list(dict.fromkeys(invalidated))


if __name__ == "__main__":
    memory = load_trade_memory()
    state = load_scan_state()
    print(json.dumps({
        "trade_memory_entries": len(memory.get("entries", [])),
        "outcomes": len(memory.get("outcomes", [])),
        "carried_setups": len(state.get("carried_setups", [])),
        "invalidated_setups": len(state.get("invalidated_setups", [])),
    }, indent=2))
