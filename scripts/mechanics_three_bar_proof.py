
"""
mechanics_three_bar_proof.py
Shared 3-test-bar proof helper for mechanics-backed edge validation.

Tests applied to the trailing 3 H1 bars ending at bar[-1]:
  1. Rejection wick / reclaim close
  2. Volume confirmation vs recent average
  3. RSI confirmation / non-overbought-or-oversold exhaustion

Rules:
- D1 needs sweep + close back across level on bar[-1].
- D3 needs close back across VWAP on bar[-1] with volume rising.
- D4 needs volume climax at RSI extreme with failure signal on bar[-1].

Output schema:
{
  symbol,
  direction,
  mechanic_type,
  three_bar_pass,
  bar_refs: [index_last, index_m1, index_m2],
  tests: [ {name, pass, detail}, ... ],
  confidence,
  entry_ref,
  sl_ref,
  tp_ref,
  reasons
}
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from scripts.market_mechanics_proof import (
    _rsi,
    _vwap,
    detect_liquidity_grab,
    detect_vwap_reclaim,
    detect_exhaustion,
)


def _volume_rising(volume: pd.Series, window: int = 20, require_last_n: int = 2) -> tuple[bool, float]:
    if len(volume) < window + 1:
        avg = float(volume.mean()) if len(volume) > 0 else 0.0
        last = float(volume.iloc[-1])
        return last > avg, last / avg if avg > 0 else 0.0
    avg = float(volume.iloc[-(window + 1) : -1].mean())
    last_n = [float(v) for v in volume.iloc[-require_last_n:]]
    if avg <= 0:
        return False, 0.0
    ratios = [v / avg for v in last_n]
    return bool(all(r > 1.0 for r in ratios)), float(np.mean(ratios))


def _recent_slope_sign(series: pd.Series, window: int = 3) -> str | None:
    if len(series) < window + 1:
        return None
    seg = series.iloc[-(window + 1) :]
    x = np.arange(len(seg), dtype=float)
    y = seg.values.astype(float)
    xm = x.mean()
    ym = y.mean()
    cov = ((x - xm) * (y - ym)).sum()
    var = ((x - xm) ** 2).sum()
    if var == 0:
        return 'FLAT'
    slope = cov / var
    if slope > 0:
        return 'UP'
    if slope < 0:
        return 'DOWN'
    return 'FLAT'


def three_bar_proof(symbol: str, df: pd.DataFrame, direction: str | None = None, candidate_type: str | None = None) -> dict[str, Any]:
    if df is None or len(df) < 20:
        return {
            'symbol': symbol,
            'direction': direction,
            'mechanic_type': candidate_type or 'NONE',
            'three_bar_pass': False,
            'confidence': 0,
            'tests': [],
            'reasons': ['insufficient bars'],
            'entry_ref': None,
            'sl_ref': None,
            'tp_ref': None,
        }

    direction = (direction or '').upper() or None
    candidate_type = (candidate_type or '').upper() or None

    base = {
        'symbol': symbol,
        'direction': direction,
        'mechanic_type': candidate_type or 'NONE',
        'three_bar_pass': False,
        'confidence': 0,
        'tests': [],
        'reasons': [],
        'bar_refs': [int(pd.Timestamp(df.index[-1]).timestamp()), int(pd.Timestamp(df.index[-2]).timestamp()), int(pd.Timestamp(df.index[-3]).timestamp())],
        'entry_ref': None,
        'sl_ref': None,
        'tp_ref': None,
    }

    close = df['close']
    open_ = df['open']
    high = df['high']
    low = df['low']
    volume = df['tick_volume'].clip(lower=0).fillna(0)
    vwap = _vwap(df, period=20)
    rsi = _rsi(close, period=14)

    last = -1
    m1 = -2
    m2 = -3

    base['entry_ref'] = float(close.iloc[last])
    base['sl_ref'] = float(low.iloc[last]) if direction == 'LONG' else float(high.iloc[last]) if direction == 'SHORT' else None
    base['tp_ref'] = None

    tests: list[dict[str, Any]] = []
    if candidate_type == 'D1_LIQUIDITY_GRAB':
        swing_low = float(low.iloc[-10:].min())
        swing_high = float(high.iloc[-10:].max())
        long_sweep = bool(low.iloc[m2:last + 1].min() < swing_low)
        short_sweep = bool(high.iloc[m2:last + 1].max() > swing_high)
        long_reclaim = bool(close.iloc[last] > swing_low)
        short_reclaim = bool(close.iloc[last] < swing_high)

        tests.append({
            'name': 'reclaim_after_sweep',
            'pass': (direction == 'LONG' and long_sweep and long_reclaim) or (direction == 'SHORT' and short_sweep and short_reclaim),
            'detail': {
                'swing_low': swing_low,
                'swing_high': swing_high,
                'long_sweep': long_sweep,
                'long_reclaim': long_reclaim,
                'short_sweep': short_sweep,
                'short_reclaim': short_reclaim,
            },
        })
        tests.append({'name': 'volume_confirmation', 'pass': False, 'detail': 'pending'})
        if len(volume) >= 20:
            avg20 = float(volume.iloc[-23:-3].mean())
            last3 = [float(volume.iloc[i]) for i in [m2, m1, last]]
            if avg20 > 0:
                ratios = [v / avg20 for v in last3]
                ok = ratios[-1] > 1.0
                tests[-1]['pass'] = ok
                tests[-1]['detail'] = {'avg20': avg20, 'last3_volume': last3, 'ratios': ratios}
            else:
                tests[-1]['detail'] = {'avg20': avg20, 'last3_volume': last3}
        tests.append({'name': 'rsi_confirmation', 'pass': False, 'detail': 'pending'})
        if len(rsi) > last:
            r = float(rsi.iloc[last])
            if direction == 'LONG':
                tests[-1]['pass'] = r < 50
            elif direction == 'SHORT':
                tests[-1]['pass'] = r > 50
            tests[-1]['detail'] = {'rsi_last': r}

    elif candidate_type == 'D3_VWAP_RECLAIM':
        v = float(vwap.iloc[last])
        tests.append({
            'name': 'reclaim_above_or_below_vwap',
            'pass': (direction == 'LONG' and float(close.iloc[last]) > v) or (direction == 'SHORT' and float(close.iloc[last]) < v),
            'detail': {'vwap': v, 'close_last': float(close.iloc[last])},
        })
        tests.append({'name': 'volume_rising', 'pass': False, 'detail': 'pending'})
        rising, ratio = _volume_rising(volume, window=20, require_last_n=2)
        tests[-1]['pass'] = rising
        tests[-1]['detail'] = {'volume_ratio': ratio, 'rising': rising}
        tests.append({'name': 'body_confirmation', 'pass': False, 'detail': 'pending'})
        body_long = float(close.iloc[last]) > float(open_.iloc[last])
        body_short = float(close.iloc[last]) < float(open_.iloc[last])
        body_ok = body_long if direction == 'LONG' else body_short if direction == 'SHORT' else False
        tests[-1]['pass'] = body_ok
        tests[-1]['detail'] = {'open_last': float(open_.iloc[last]), 'close_last': float(close.iloc[last]), 'body_direction': 'LONG' if body_long else 'SHORT' if body_short else 'NONE'}

    elif candidate_type == 'D4_EXHAUSTION':
        r = float(rsi.iloc[last]) if len(rsi) > last else None
        tests.append({'name': 'volume_climax', 'pass': False, 'detail': 'pending'})
        if len(volume) >= 20:
            avg20 = float(volume.iloc[-23:-3].mean())
            vol_now = float(volume.iloc[last])
            ratio = vol_now / avg20 if avg20 > 0 else 0.0
            tests[-1]['pass'] = ratio >= 1.5
            tests[-1]['detail'] = {'avg20': avg20, 'volume_last': vol_now, 'volume_ratio': ratio}
        tests.append({'name': 'rsi_extreme', 'pass': False, 'detail': 'pending'})
        if r is not None:
            if direction == 'LONG':
                tests[-1]['pass'] = r <= 30
            elif direction == 'SHORT':
                tests[-1]['pass'] = r >= 70
            tests[-1]['detail'] = {'rsi_last': r}
        tests.append({'name': 'rejection_failure', 'pass': False, 'detail': 'pending'})
        if r is not None:
            long_rejection = float(low.iloc[last]) < float(low.iloc[m2:last].min()) and float(close.iloc[last]) > float(low.iloc[m1])
            short_rejection = float(high.iloc[last]) > float(high.iloc[m2:last].max()) and float(close.iloc[last]) < float(high.iloc[m1])
            tests[-1]['pass'] = long_rejection if direction == 'LONG' else short_rejection if direction == 'SHORT' else False
            tests[-1]['detail'] = {
                'low_last': float(low.iloc[last]),
                'low_m1': float(low.iloc[m1]),
                'low_m2': float(low.iloc[m2]),
                'high_last': float(high.iloc[last]),
                'high_m1': float(high.iloc[m1]),
                'high_m2': float(high.iloc[m2]),
            }

    confidence = 0
    passed_tests = [t for t in tests if t.get('pass')]
    if len(passed_tests) == len(tests) and tests:
        confidence = 90
        base['three_bar_pass'] = True
        base['reasons'].append('all 3-bar mechanics tests passed')
    elif len(passed_tests) == len(tests) - 1:
        confidence = 65
        base['reasons'].append('2 of 3 mechanics tests passed')
    else:
        base['reasons'].append('insufficient 3-bar proof')

    base['tests'] = tests
    base['confidence'] = int(confidence)
    return base


def mechanics_batch_proof(symbols: list[str], frame_provider, direction: str | None = None, candidate_types: dict[str, str] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sym in symbols:
        df = frame_provider(sym)
        if df is None:
            continue
        ctype = None
        if candidate_types:
            ctype = candidate_types.get(sym)
        base = detect_liquidity_grab(df, direction=direction)
        base.update(three_bar_proof(sym, df, direction=direction, candidate_type=ctype or base.get('mechanic_type')))
        out.append(base)
    return out
