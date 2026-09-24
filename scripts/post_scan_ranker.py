#!/usr/bin/env python3
"""
post_scan_ranker.py
-------------------
Post-scan highest-probability setup ranker.

Inputs:
  - cerebro_backtest_ranked_setups_YYYY-MM-DD.json  (or any scan JSON with ranked_setups/top)
  - all_market_ranked_setups_YYYY-MM-DD_open.json
  - all_sector_ranked_setups_YYYY-MM-DD.json
  - pre_market_proposed_setups_YYYY-MM-DD.json
  - backtest_summary.json                            (per symbol/side win_rate/avg_loss/expectancy)
  - optional news_sentiment_YYYY-MM-DD.json          (sym -> score 0-100 or 0-1 sigmoid)

Outputs:
  - ranked_setups_composite_YYYYMMDD.json
    * top 20 unified setups
    * best_buy_setups[:8]
    * best_sell_setups[:8]
"""

import json
import datetime
import math
from pathlib import Path

workspace = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
today = datetime.date.today().isoformat()

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_json(name):
    p = workspace / name
    if not p.exists():
        return None
    return json.loads(p.read_text())

# ---------------------------------------------------------------------------
# Backtest stats / BST
# ---------------------------------------------------------------------------
bt_stats = {}
bt_raw = load_json('backtest_summary.json')
if bt_raw:
    for row in bt_raw.get('summary', []):
        sym = row.get('symbol')
        side = (row.get('side') or '').lower()
        if not sym or not side:
            continue
        key = (sym.upper(), side)
        prev = bt_stats.get(key, {})
        bt_stats[key] = {
            'count': prev.get('count', 0) + row.get('count', 0),
            'win_rate': row.get('win_rate') if row.get('win_rate') is not None else prev.get('win_rate'),
            'expectancy': row.get('expectancy') if row.get('expectancy') is not None else prev.get('expectancy'),
            'avg_loss': row.get('avg_loss') if row.get('avg_loss') is not None else prev.get('avg_loss'),
        }

def bst_modifier(symbol, bias, rr):
    side = 'buy' if bias == 'bullish' else 'sell' if bias == 'bearish' else 'neutral'
    candidates = [
        (symbol.upper(), side),
        (symbol.upper().replace('USD', 'USDT') if symbol.upper().endswith('USD') else symbol.upper(), side),
        (symbol.upper(), bias),
        (symbol.upper(), 'buy'),
        (symbol.upper(), 'long'),
        (symbol.upper(), 'sell'),
        (symbol.upper(), 'short'),
    ]
    stats = None
    for key in candidates:
        stats = bt_stats.get(key)
        if stats:
            break
    if not stats:
        return 0.0, None
    count = stats.get('count', 0)
    confidence = max(0.0, min(1.0, count / 20))
    wr = stats.get('win_rate') or 0.5
    exp = stats.get('expectancy') or 0.0
    mod = max(-40.0, min(40.0, (wr - 0.5) * 100)) + max(-20.0, min(20.0, exp * 4))
    return float(mod * confidence), stats

# ---------------------------------------------------------------------------
# Technical score / fixed weights
# ---------------------------------------------------------------------------
def normalize_rsi_score(rsi):
    if rsi is None:
        return 0
    if rsi < 30:
        return 30
    if 30 <= rsi < 40:
        return 20
    if 60 <= rsi <= 70:
        return 10
    return 0

def technical_score(rsi, bias, price, entry, sl, tp):
    score = 0
    rp = normalize_rsi_score(rsi)
    score += rp

    # MACD proxy via bias
    if bias == 'bullish':
        mp = 30
    elif bias == 'bearish':
        mp = 20
    else:
        mp = 0
    score += mp

    # BB proxy from sl/tp spread/price if available
    bp = 0
    if price is not None and sl is not None and tp is not None:
        risk = abs(entry - sl) if entry else None
        reward = abs(tp - entry) if entry else None
        # crude band width: if RR fixed at 2.0 and risk small-ish, treat as tight band
        if risk is not None and price < sl:
            bp = 25
        elif risk is not None:
            bp = max(0, min(25, reward * 5 if reward else 0))
    score += bp

    vol_p = 0

    components = {
        'rsi_p': rp,
        'macd_p': mp,
        'bb_p': bp,
        'vol_p': vol_p,
    }
    return max(0, min(100, score)), components

# ---------------------------------------------------------------------------
# News sentiment
# ---------------------------------------------------------------------------
sentiment_path = workspace / f'news_sentiment_{today}.json'
news_sentiment = {}
if sentiment_path.exists():
    try:
        news_sentiment = json.loads(sentiment_path.read_text())
    except Exception:
        news_sentiment = {}

def analyst_score(symbol):
    data = news_sentiment.get(symbol)
    if isinstance(data, dict) and 'score' in data:
        v = data.get('score')
        if isinstance(v, (int, float)):
            if 0 <= v <= 1:
                return float(v * 100)
            return float(v)
    if isinstance(data, (int, float)):
        if 0 <= data <= 1:
            return float(data * 100)
        return float(data)
    return 50.0

# ---------------------------------------------------------------------------
# Load all ranked setups
# ---------------------------------------------------------------------------
sources = [
    'cerebro_backtest_ranked_setups_2026-07-29.json',
    'all_market_ranked_setups_2026-07-29_open.json',
    'all_sector_ranked_setups_2026-07-29.json',
    'pre_market_proposed_setups_2026-07-29.json',
]

candidates = []
for src in sources:
    raw = load_json(src)
    if not raw:
        continue
    setups = raw.get('top', raw.get('ranked_setups', []))
    if not setups:
        continue
    for s in setups:
        sym = (s.get('symbol') or s.get('ticker') or '').strip().upper()
        if not sym:
            continue
        candidates.append({
            'source_file': src,
            'broker': s.get('broker') or 'unknown',
            'symbol': sym,
            'bias': s.get('bias') or s.get('side') or 'neutral',
            'entry': s.get('entry') or s.get('proposed_entry') or s.get('price'),
            'sl': s.get('sl') or s.get('stop'),
            'tp': s.get('tp') or s.get('target'),
            'rr': s.get('rr'),
            'rsi': s.get('rsi') or s.get('rsi14') or s.get('rsi_14'),
            'atr': s.get('atr') or s.get('atr14') or s.get('atr_14'),
            'route': s.get('route'),
            'timeframe': s.get('timeframe'),
            'execution_status': s.get('execution_status'),
        })

# dedupe by symbol+bias, keep best
best_route = {}
for c in candidates:
    k = (c['symbol'], c['bias'])
    prev = best_route.get(k)
    if not prev or (c.get('rsi') or 0) > (prev.get('rsi') or 0):
        best_route[k] = c
unique = list(best_route.values())

# ---------------------------------------------------------------------------
# Score each setup
# ---------------------------------------------------------------------------
scan_results = []
for setup in unique:
    rsi = setup.get('rsi')
    bias = setup.get('bias')
    rr = setup.get('rr') or 2.0
    price = setup.get('entry')
    sl = setup.get('sl')
    tp = setup.get('tp')

    tech, comp = technical_score(rsi, bias, price, price, sl, tp)
    bst, bst_stats = bst_modifier(setup['symbol'], bias, rr)
    bst_score = max(0.0, min(100.0, float(tech) + bst))
    analyst = analyst_score(setup['symbol'])
    readiness = 100.0 if sl and tp else 40.0

    composite = round(
        0.35 * bst_score +
        0.35 * tech +
        0.15 * analyst +
        0.10 * (rr * 20) +
        0.05 * readiness
    )
    composite = max(0, min(100, composite))

    scan_results.append({
        **setup,
        'technical_score': tech,
        'technical_components': comp,
        'bst_score': round(bst_score, 2),
        'bst_backtest': {
            'symbol': setup['symbol'],
            'bias': bias,
            'win_rate': bst_stats.get('win_rate') if bst_stats else None,
            'expectancy': bst_stats.get('expectancy') if bst_stats else None,
            'count': bst_stats.get('count') if bst_stats else 0,
        },
        'analyst_score': round(analyst, 2),
        'composite_score': round(composite, 2),
    })

scan_results.sort(key=lambda x: (x['composite_score'], x['bst_score'], x['technical_score']), reverse=True)

best_buys = [r for r in scan_results if r['bias'] == 'bullish'][:8]
best_sells = [r for r in scan_results if r['bias'] == 'bearish'][:8]

out = {
    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    'weights': {
        'bst_score': 0.35,
        'technical_score': 0.35,
        'analyst_news_sentiment': 0.15,
        'rr': 0.10,
        'execution_readiness': 0.05,
    },
    'meta': {
        'inputs': sources,
        'backtest_rows': len(bt_stats),
        'news_sentiment_source': str(sentiment_path) if sentiment_path.exists() else 'none',
    },
    'top': scan_results[:20],
    'best_buy_setups': best_buys,
    'best_sell_setups': best_sells,
}

out_path = workspace / f'ranked_setups_composite_{today.replace("-", "")}.json'
out_path.write_text(json.dumps(out, indent=2))
print('WROTE', out_path)
print('TOTAL_SCORED', len(scan_results))
print('BEST_BUY')
for b in best_buys[:8]:
    print(f"{b['symbol']} | {b['bias']} | composite={b['composite_score']} bst={b['bst_score']} tech={b['technical_score']} analyst={b['analyst_score']} rr={b.get('rr')} route={b.get('route')}")
print('BEST_SELL')
for b in best_sells[:8]:
    print(f"{b['symbol']} | {b['bias']} | composite={b['composite_score']} bst={b['bst_score']} tech={b['technical_score']} analyst={b['analyst_score']} rr={b.get('rr')} route={b.get('route')}")
