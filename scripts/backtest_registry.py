#!/usr/bin/env python3
"""Backtest registry and gate for execution scripts.

Contract:
- `load_backtest(path)` -> parsed JSON/dict or None
- `require_backtest(symbol, min_win_rate=0.55, min_expectancy=0.0)` -> bool
- `best_backtest(symbol)` -> dict or None

Artifacts expected:
- `workflow/backtest_results/*.json` or a master `workflow/backtest_master.json`
"""
import json
from pathlib import Path

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
BACKTEST_DIR = BASE / 'workflow' / 'backtest_results'
MASTER_FILE = BASE / 'workflow' / 'backtest_master.json'

_cache = {}


def _load_master():
    if not MASTER_FILE.exists():
        return {}
    try:
        data = json.loads(MASTER_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict) and 'symbols' in data:
            return data.get('symbols', {})
        return data
    except Exception:
        return {}


def _normalize_symbol_keys(symbol: str):
    s = symbol.strip().upper()
    candidates = [s]
    if '/' in s:
        candidates.append(s.replace('/', '-'))
        candidates.append(s.replace('/', ''))
    elif '-' in s:
        candidates.append(s.replace('-', '/'))
        candidates.append(s.replace('-', ''))
    elif len(s) == 6 and s.isalpha():
        candidates.append(f"{s[:3]}/{s[3:]}")
        candidates.append(f"{s[:3]}-{s[3:]}")
    elif len(s) >= 3 and s.isalpha():
        if s.endswith('USD') and len(s) > 6:
            candidates.append(f"{s[:-3]}/USD")
            candidates.append(f"{s[:-3]}-USD")
    return list(dict.fromkeys(candidates))


def _lookup_symbol(symbol_map: dict, symbol: str):
    for key in _normalize_symbol_keys(symbol):
        if key in symbol_map:
            return symbol_map[key]
    return None


def load_backtest(path: str | Path):
    p = Path(path)
    if p in _cache:
        return _cache[p]
    data = None
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            data = None
    _cache[p] = data
    return data


def require_backtest(symbol: str, min_win_rate: float = 0.55, min_expectancy: float = 0.0) -> bool:
    entry = _lookup_symbol(_load_master(), symbol)
    if not entry and BACKTEST_DIR.exists():
        entry = load_backtest(BACKTEST_DIR / f"{symbol}.json")
    if not entry:
        return False
    wr = entry.get('win_rate') or entry.get('winrate') or 0
    exp = entry.get('expectancy') or entry.get('edge') or 0
    return float(wr) >= float(min_win_rate) and float(exp) >= float(min_expectancy)


def best_backtest(symbol: str):
    entry = _lookup_symbol(_load_master(), symbol)
    if not entry and BACKTEST_DIR.exists():
        entry = load_backtest(BACKTEST_DIR / f"{symbol}.json")
    return entry
