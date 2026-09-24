
"""
market_mechanics_proof.py
Mechanics-based edge detector for MT5-style OHLCV bars.

Patterns:
  D1 Liquidity Grab - sweep of prior swing low/high then rejection
  D3 VWAP Reclaim    - close back above/below VWAP on rising volume
  D4 Exhaustion      - volume climax at extreme RSI

Standardized output:
{
  symbol, direction, mechanic_type, pass, confidence,
  entry_ref, sl_ref, tp_ref, reasons, bar_index
}
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _pivot_lows(low: pd.Series, lookback: int = 5) -> pd.Series:
    swing = pd.Series(False, index=low.index)
    for i in range(lookback, len(low) - lookback):
        window = low.iloc[i - lookback : i + lookback + 1]
        if low.iloc[i] == window.min():
            swing.iloc[i] = True
    return swing


def _pivot_highs(high: pd.Series, lookback: int = 5) -> pd.Series:
    swing = pd.Series(False, index=high.index)
    for i in range(lookback, len(high) - lookback):
        window = high.iloc[i - lookback : i + lookback + 1]
        if high.iloc[i] == window.max():
            swing.iloc[i] = True
    return swing


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0)).abs()
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    typical = (df['high'] + df['low'] + df['close']) / 3.0
    vol = df['tick_volume'].clip(lower=0).fillna(0)
    tpv = typical * vol
    vwap = tpv.rolling(window=period, min_periods=1).sum() / vol.rolling(window=period, min_periods=1).sum()
    return vwap


def _volume_climax(volume: pd.Series, lookback: int = 20) -> pd.Series:
    avg = volume.rolling(window=lookback, min_periods=1).mean()
    return volume / avg.replace(0, np.nan)


def detect_liquidity_grab(df: pd.DataFrame, direction: str | None = None, lookback: int = 25) -> dict[str, Any]:
    if len(df) < lookback * 2 + 1:
        return {'mechanic_type': 'D1_LIQUIDITY_GRAB', 'pass': False, 'confidence': 0, 'reasons': ['insufficient bars']}

    lows = df['low']
    highs = df['high']
    closes = df['close']

    swing_lows = _pivot_lows(lows, lookback=min(5, lookback // 5))
    swing_highs = _pivot_highs(highs, lookback=min(5, lookback // 5))

    last = df.index[-1]
    prev = df.index[-2]
    reasons: list[str] = []

    grab = False
    grab_direction: str | None = None
    confidence = 0
    entry_ref = float(closes.iloc[-1])

    # Long liquidity grab: recent sweep below swing low, then reclaim
    recent_swing_low = None
    if swing_lows.any():
        recent_swing_low_idx = swing_lows[swing_lows].index[-1]
        recent_swing_low = float(lows.loc[recent_swing_low_idx])
    if recent_swing_low is not None:
        swept = float(lows.iloc[-2]) < recent_swing_low
        reclaimed = float(closes.iloc[-1]) > recent_swing_low
        if swept and reclaimed:
            grab = True
            grab_direction = 'LONG'
            confidence = min(100, int(60 + abs(float(closes.iloc[-1]) - recent_swing_low) / float(closes.iloc[-1]) * 1000))
            reasons.append(f'swept swing_low={recent_swing_low:.5f} then closed back above')

    # Short liquidity grab: spike above swing high, then close back below
    recent_swing_high = None
    if swing_highs.any():
        recent_swing_high_idx = swing_highs[swing_highs].index[-1]
        recent_swing_high = float(highs.loc[recent_swing_high_idx])
    if recent_swing_high is not None:
        swept = float(highs.iloc[-2]) > recent_swing_high
        reclaimed = float(closes.iloc[-1]) < recent_swing_high
        if swept and reclaimed:
            grab = True
            grab_direction = 'SHORT'
            confidence = min(100, int(60 + abs(float(closes.iloc[-1]) - recent_swing_high) / float(closes.iloc[-1]) * 1000))
            reasons.append(f'swept swing_high={recent_swing_high:.5f} then closed back below')

    if direction and grab_direction and grab_direction != direction:
        grab = False
        reasons.append(f'direction mismatch: detected={grab_direction} requested={direction}')

    if not reasons:
        reasons.append('no sweep/reclaim detected')

    return {
        'mechanic_type': 'D1_LIQUIDITY_GRAB',
        'pass': bool(grab),
        'confidence': int(confidence),
        'entry_ref': entry_ref,
        'sl_ref': float(lows.iloc[-1]) if grab and grab_direction == 'LONG' else float(highs.iloc[-1]) if grab and grab_direction == 'SHORT' else None,
        'tp_ref': None,
        'direction': grab_direction,
        'reasons': reasons,
        'bar_index': int(pd.Timestamp(df.index[-1]).timestamp()),
    }


def detect_vwap_reclaim(df: pd.DataFrame, direction: str | None = None, vwap_period: int = 20, volume_lookback: int = 20) -> dict[str, Any]:
    if len(df) < max(vwap_period, volume_lookback) + 1:
        return {'mechanic_type': 'D3_VWAP_RECLAIM', 'pass': False, 'confidence': 0, 'reasons': ['insufficient bars']}

    vwap = _vwap(df, period=vwap_period)
    close = df['close']
    volume = df['tick_volume'].clip(lower=0).fillna(0)
    vwap_now = float(vwap.iloc[-1])
    close_now = float(close.iloc[-1])
    reasons: list[str] = []

    if np.isnan(vwap_now) or vwap_now <= 0:
        return {'mechanic_type': 'D3_VWAP_RECLAIM', 'pass': False, 'confidence': 0, 'reasons': ['vwap invalid']}

    prev_below = bool((close.iloc[-(volume_lookback + 1) : -1] < vwap.iloc[-(volume_lookback + 1) : -1]).any())
    prev_above = bool((close.iloc[-(volume_lookback + 1) : -1] > vwap.iloc[-(volume_lookback + 1) : -1]).any())
    above_now = close_now > vwap_now
    below_now = close_now < vwap_now
    avg_vol = float(volume.iloc[-volume_lookback:-1].mean()) if len(volume) > volume_lookback + 1 else float(volume.mean())
    vol_rising = bool(float(volume.iloc[-1]) > avg_vol * 1.1) if avg_vol > 0 else False
    body_ok = bool((close_now - df['open'].iloc[-1]) > 0) if above_now else bool((df['open'].iloc[-1] - close_now) > 0) if below_now else False
    confidence = 0
    pass_reclaim = False
    reclaim_direction: str | None = None

    if prev_below and above_now and vol_rising:
        pass_reclaim = True
        reclaim_direction = 'LONG'
        confidence = 70 if body_ok else 50
        reasons.append('reclaimed vwap above from below with rising volume')
    elif prev_above and below_now and vol_rising:
        pass_reclaim = True
        reclaim_direction = 'SHORT'
        confidence = 70 if body_ok else 50
        reasons.append('reclaimed vwap below from above with rising volume')

    if direction and reclaim_direction and reclaim_direction != direction:
        pass_reclaim = False
        reasons.append(f'direction mismatch: detected={reclaim_direction} requested={direction}')

    if not pass_reclaim:
        reasons.append('no valid vwap reclaim on this bar')

    return {
        'mechanic_type': 'D3_VWAP_RECLAIM',
        'pass': bool(pass_reclaim),
        'confidence': int(confidence),
        'entry_ref': close_now,
        'sl_ref': float(vwap_now) if reclaim_direction == 'LONG' else float(vwap_now) if reclaim_direction == 'SHORT' else None,
        'tp_ref': None,
        'direction': reclaim_direction,
        'reasons': reasons,
        'bar_index': int(pd.Timestamp(df.index[-1]).timestamp()),
    }


def detect_exhaustion(df: pd.DataFrame, direction: str | None = None, rsi_period: int = 14, volume_lookback: int = 20) -> dict[str, Any]:
    if len(df) < max(rsi_period, volume_lookback) + 1:
        return {'mechanic_type': 'D4_EXHAUSTION', 'pass': False, 'confidence': 0, 'reasons': ['insufficient bars']}

    rsi = _rsi(df['close'], period=rsi_period)
    rsi_now = float(rsi.iloc[-1])
    volume = df['tick_volume'].clip(lower=0).fillna(0)
    avg_vol = float(volume.iloc[-volume_lookback:-1].mean()) if len(volume) > volume_lookback + 1 else float(volume.mean())
    vol_ratio = float(volume.iloc[-1] / avg_vol) if avg_vol > 0 else 0.0
    reasons: list[str] = []
    confidence = 0
    is_exhaust = False
    exhaustion_direction: str | None = None
    close_now = float(df['close'].iloc[-1])
    high_now = float(df['high'].iloc[-1])
    low_now = float(df['low'].iloc[-1])

    if direction and direction.upper() == 'SHORT' and rsi_now >= 70 and vol_ratio >= 1.5:
        is_exhaust = True
        exhaustion_direction = 'SHORT'
        confidence = 75 if rsi_now >= 80 else 60
        reasons.append(f'overbought exhaustion rsi={rsi_now:.1f} volume_ratio={vol_ratio:.2f}')
    elif direction and direction.upper() == 'LONG' and rsi_now <= 30 and vol_ratio >= 1.5:
        is_exhaust = True
        exhaustion_direction = 'LONG'
        confidence = 75 if rsi_now <= 20 else 60
        reasons.append(f'oversold exhaustion rsi={rsi_now:.1f} volume_ratio={vol_ratio:.2f}')
    else:
        reasons.append(f'no exhaustion condition rsi={rsi_now:.1f} volume_ratio={vol_ratio:.2f}')

    return {
        'mechanic_type': 'D4_EXHAUSTION',
        'pass': bool(is_exhaust),
        'confidence': int(confidence),
        'entry_ref': close_now,
        'sl_ref': high_now if exhaustion_direction == 'SHORT' else low_now if exhaustion_direction == 'LONG' else None,
        'tp_ref': None,
        'direction': exhaustion_direction,
        'reasons': reasons,
        'rsi': round(rsi_now, 2),
        'volume_ratio': round(vol_ratio, 2),
    }


def run_mechanics_proof(symbol: str, df: pd.DataFrame, direction: str | None = None) -> dict[str, Any]:
    if df is None or len(df) < 30:
        return {'symbol': symbol, 'pass': False, 'mechanic_type': 'NONE', 'confidence': 0, 'reasons': ['insufficient data']}

    direction = (direction or '').upper() or None

    d1 = detect_liquidity_grab(df, direction=direction)
    d3 = detect_vwap_reclaim(df, direction=direction)
    d4 = detect_exhaustion(df, direction=direction)

    results = [d1, d3, d4]
    passed = [r for r in results if r.get('pass')]
    best = max(results, key=lambda r: r.get('confidence', 0)) if results else {'mechanic_type': 'NONE', 'confidence': 0}

    return {
        'symbol': symbol,
        'pass': bool(passed),
        'mechanic_type': best.get('mechanic_type', 'NONE'),
        'confidence': int(best.get('confidence', 0)),
        'entry_ref': best.get('entry_ref'),
        'sl_ref': best.get('sl_ref'),
        'tp_ref': best.get('tp_ref'),
        'direction': best.get('direction') or direction,
        'results': results,
        'reasons': best.get('reasons', []),
        'bar_index': int(pd.Timestamp(best.get('bar_index', df.index[-1])).timestamp()),
    }
