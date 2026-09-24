#!/usr/bin/env python3
"""
Shift Setup Enrichment — shared core for ALL scan shifts.

Attaches to each candidate:
- Bollinger Bands + regime
- Multi-timeframe trend
- Correlated peers
- Hold-time estimate
- Analyst target status (Finnhub key-gated; never fabricated)
- Scan-to-scan memory via Desktop/scandata/scan_memory_ledger.json
"""
from __future__ import annotations

import json, math, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

SCANDATA = Path(r'C:\Users\bravo-usr1\Desktop\scandata')
LEDGER_PATH = SCANDATA / 'scan_memory_ledger.json'
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)


def _nowz() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _load_ledger() -> Dict[str, Any]:
    if not LEDGER_PATH.exists():
        return {'records': {}, 'meta': {}}
    try:
        return json.loads(LEDGER_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {'records': {}, 'meta': {}}


def _save_ledger(ledger: Dict[str, Any]) -> None:
    try:
        LEDGER_PATH.write_text(json.dumps(ledger, indent=2, default=str), encoding='utf-8')
    except Exception as e:
        print(f'[enrich] ledger write warning: {e}')


def record_seen(symbols: List[str], shift: str, output_file: Optional[str] = None) -> int:
    ledger = _load_ledger()
    now = _nowz()
    meta = ledger.setdefault('meta', {})
    meta['last_shift'] = shift
    meta['last_update'] = now
    meta['last_output'] = output_file or ''
    records = ledger.setdefault('records', {})
    count = 0
    for sym in symbols:
        rec = records.get(sym, {'first_seen': now, 'seen_history': []})
        rec['last_seen'] = now
        rec['last_shift'] = shift
        hist = rec.get('seen_history', [])
        hist.append({'shift': shift, 'ts': now, 'output': output_file or ''})
        rec['seen_history'] = hist[-100:]
        records[sym] = rec
        count += 1
    _save_ledger(ledger)
    return count


def seen_history(symbol: str) -> List[Dict[str, str]]:
    ledger = _load_ledger()
    rec = ledger.get('records', {}).get(symbol, {})
    return rec.get('seen_history', [])


def _bollinger(closes: List[float], period: int = 20, std_dev: float = 2.0) -> Optional[Dict[str, Any]]:
    if not closes or len(closes) < period:
        return None
    arr = np.array(closes, dtype=float)
    sma = float(np.mean(arr[-period:]))
    std = float(np.std(arr[-period:], ddof=0))
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    last = float(arr[-1])
    if sma == 0 or (upper - lower) == 0:
        regime = 'FLAT'
    elif last > upper:
        regime = 'OVERBOUGHT'
    elif last < lower:
        regime = 'OVERSOLD'
    elif last > sma:
        regime = 'BULL_MID'
    else:
        regime = 'BEAR_MID'
    pct_b = (last - lower) / (upper - lower)
    return {
        'upper': round(upper, 6),
        'middle': round(sma, 6),
        'lower': round(lower, 6),
        'pct_b': round(float(pct_b), 4),
        'regime': regime,
    }


def _pairwise_corr_matrix(sym_closes: Dict[str, List[float]]) -> Dict[str, Dict[str, Optional[float]]]:
    symbols = list(sym_closes.keys())
    rets: Dict[str, np.ndarray] = {}
    for sym, closes in sym_closes.items():
        arr = np.array(closes, dtype=float)
        if arr.size < 2:
            continue
        rets[sym] = np.diff(np.log(arr))
    out: Dict[str, Dict[str, Optional[float]]] = {s: {} for s in symbols}
    for i, a in enumerate(symbols):
        for j, b in enumerate(symbols):
            if i == j:
                out[a][b] = 1.0
                continue
            ra, rb = rets.get(a), rets.get(b)
            if ra is None or rb is None:
                out[a][b] = None
                continue
            n = min(ra.size, rb.size)
            if n < 10:
                out[a][b] = None
                continue
            x, y = ra[-n:], rb[-n:]
            if np.std(x) == 0 or np.std(y) == 0:
                out[a][b] = None
                continue
            corr = float(np.corrcoef(x, y)[0, 1])
            out[a][b] = None if (math.isnan(corr) or math.isinf(corr)) else round(corr, 4)
    return out


def correlated_peers(symbol: str, corr_ledger: Dict[str, Dict[str, Optional[float]]], abs_threshold: float = 0.6, limit: int = 5) -> List[Dict[str, Any]]:
    row = corr_ledger.get(symbol, {})
    peers: List[Dict[str, Any]] = []
    for peer, corr in row.items():
        if peer == symbol or corr is None:
            continue
        if abs(float(corr)) >= abs_threshold:
            peers.append({'symbol': peer, 'corr': corr, 'relationship': 'positive' if corr > 0 else 'negative'})
    peers.sort(key=lambda x: abs(x['corr']), reverse=True)
    return peers[:limit]


def mtf_trend_from_closes(mtf_closes: Dict[str, List[float]]) -> Dict[str, Optional[str]]:
    trends: Dict[str, Optional[str]] = {}
    for tf, closes in mtf_closes.items():
        if not closes or len(closes) < 20:
            trends[tf] = None
            continue
        arr = [float(x) for x in closes]
        last, sma20, sma50 = arr[-1], float(np.mean(arr[-20:])), float(np.mean(arr[-50:])) if len(arr) >= 50 else None
        if sma50 and last:
            if last > sma20 > sma50:
                trends[tf] = 'BULL'
            elif last < sma20 < sma50:
                trends[tf] = 'BEAR'
            else:
                trends[tf] = 'MIXED'
        elif sma20 and last:
            trends[tf] = 'BULL' if last > sma20 else 'BEAR' if last < sma20 else 'MIXED'
        else:
            trends[tf] = 'MIXED'
    return trends


def _hold_time_estimate(closes: List[float], atr_pct: Optional[float], trend_count: int, trend_consensus: str) -> Dict[str, Optional[int]]:
    if atr_pct is None:
        base = 7
    elif atr_pct > 2.0:
        base = 3
    elif atr_pct > 1.0:
        base = 7
    else:
        base = 14
    tf_bonus = max(0, trend_count - 1)
    if trend_consensus in ('BULL', 'BEAR'):
        tf_bonus += 1
    return {'conservative': max(1, base - 1), 'expected': base + tf_bonus, 'stretch': base + tf_bonus + 7}


def _load_finnhub_key() -> Optional[str]:
    candidates = [Path(r'D:/apis.txt'), Path(r'C:/Users/bravo-usr1/Desktop/allapi2026.txt')]
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if 'finnhub' in line.lower():
                    if '=' in line:
                        _, val = line.split('=', 1)
                        val = val.strip().strip('"').strip("'")
                        if val:
                            return val
                    return line
        except Exception:
            continue
    return None


def analyst_target(symbol: str) -> Dict[str, Any]:
    key = _load_finnhub_key()
    if not key:
        return {'status': 'UNVERIFIED (no finnhub key)'}
    try:
        import requests
        r = requests.get('https://finnhub.io/api/v1/stock/price-target', params={'symbol': symbol, 'token': key}, timeout=10)
        if r.status_code == 200:
            data = r.json() or {}
            if data.get('targetMean') not in (None, 0):
                return {
                    'status': 'VERIFIED',
                    'source': 'finnhub',
                    'target_mean': data.get('targetMean'),
                    'target_high': data.get('targetHigh'),
                    'target_low': data.get('targetLow'),
                    'target_median': data.get('targetMedian'),
                    'analyst_count': data.get('numberOfAnalysts'),
                }
            return {'status': 'UNVERIFIED (empty payload)'}
        if r.status_code in (401, 403):
            return {'status': f'UNVERIFIED (finnhub {r.status_code} - key expired/blocked)'}
        return {'status': f'UNVERIFIED (finnhub {r.status_code})'}
    except Exception as e:
        return {'status': f'UNVERIFIED ({type(e).__name__}: {e})'}


def build_correlation_ledger(scanned_assets: List[Dict[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    sym_closes: Dict[str, List[float]] = {}
    for asset in scanned_assets:
        closes = asset.get('closes')
        sym = asset.get('symbol')
        if not sym or not closes or len(closes) < 10:
            continue
        sym_closes[sym] = [float(x) for x in closes]
    if len(sym_closes) < 2:
        return {}
    return _pairwise_corr_matrix(sym_closes)


def enrich_candidate(
    t: Dict[str, Any],
    closes_daily: Optional[List[float]],
    closes_by_tf: Optional[Dict[str, List[float]]],
    corr_ledger: Dict[str, Dict[str, Optional[float]]],
    shift: str,
) -> Dict[str, Any]:
    t = dict(t)
    closes = closes_daily or []
    mtf_closes = closes_by_tf or {}
    t['closes'] = closes
    t['mtf_closes'] = mtf_closes

    t['bollinger'] = _bollinger(closes) if closes else None
    t['mtf_trend'] = mtf_trend_from_closes(mtf_closes) if mtf_closes else {}
    t['correlated_peers'] = correlated_peers(t.get('symbol', ''), corr_ledger)

    atr_val = t.get('atr')
    last = t.get('last')
    atr_pct = None
    if atr_val is not None and last not in (None, 0):
        atr_pct = (float(atr_val) / float(last)) * 100.0
    trend_vals = [v for v in (t.get('mtf_trend') or {}).values() if v in ('BULL', 'BEAR')]
    trend_count = len(trend_vals)
    bull = sum(1 for v in trend_vals if v == 'BULL')
    bear = sum(1 for v in trend_vals if v == 'BEAR')
    consensus = 'BULL' if bull > bear else 'BEAR' if bear > bull else 'MIXED'
    t['hold_time_days'] = _hold_time_estimate(closes, atr_pct, trend_count, consensus)

    sector = t.get('sector', '')
    sym = t.get('symbol', '')
    if sector in ('Stocks', 'ETFs') and sym:
        t['analyst_target'] = analyst_target(sym)
    else:
        t['analyst_target'] = {'status': 'N/A - non-equity'}

    t['seen_history'] = seen_history(sym)
    return t


def build_report(populated: List[Dict[str, Any]], shift: str, top_n: int = 20) -> str:
    lines: List[str] = []
    lines.append(f'=== Enrichment Report | shift={shift} | {_nowz()} ===')
    lines.append(f'populated={len(populated)}')
    sectors = sorted({str(x.get('sector')) for x in populated if x.get('sector')})
    lines.append('sectors=' + ','.join(sectors))

    tf_bull = tf_bear = tf_mixed = tf_unknown = 0
    for x in populated:
        trends = x.get('mtf_trend') or {}
        vals = list(trends.values())
        bull_tfs = sum(1 for v in vals if v == 'BULL')
        bear_tfs = sum(1 for v in vals if v == 'BEAR')
        mixed_tfs = sum(1 for v in vals if v == 'MIXED')
        tf_bull += bull_tfs
        tf_bear += bear_tfs
        tf_mixed += mixed_tfs
        if not vals:
            tf_unknown += 1
    lines.append(f'mtf_trends bull={tf_bull} bear={tf_bear} mixed={tf_mixed} unknown={tf_unknown}')

    top = sorted(populated, key=lambda x: float(x.get('conviction') or 0), reverse=True)[:top_n]
    lines.append('top_setups=')
    for x in top:
        sym = x.get('symbol', '')
        conv = x.get('conviction', 0)
        bb = (x.get('bollinger') or {}).get('regime', 'N/A')
        trends = x.get('mtf_trend') or {}
        tf = ','.join(f'{k}:{v}' for k, v in trends.items()) if trends else 'N/A'
        peers = ', '.join(p.get('symbol', '') for p in (x.get('correlated_peers') or [])[:3])
        hold = x.get('hold_time_days') or {}
        at = (x.get('analyst_target') or {}).get('status', 'N/A')
        lines.append(f'  {sym:16} conv={conv:4} bb={bb:12} tf=[{tf}] peers=[{peers}] hold={hold.get("expected")}d at={at}')
    return '\n'.join(lines)
