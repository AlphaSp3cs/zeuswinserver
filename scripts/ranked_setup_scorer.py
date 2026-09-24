#!/usr/bin/env python3
"""
Post-scan highest-probability setup ranker.
Inputs:
  - cerebro_backtest_ranked_setups_YYYY-MM-DD.json  (or any scan JSON with ranked_setups/top)
  - backtest_summary.json                            (per symbol/side win_rate/avg_loss)
  - optional news sentiment JSON                      (sym -> sentiment score 0-1)
Outputs:
  - ranked_setups_composite_YYYY-MM-DD.json
Includes:
  - bst_score: backtest-backed technical score
  - analyst_score / sentiment_score from injected news if available
  - composite_score: weighted fusion used to rank
  - best_buy / best_sell buckets
"""

import json, datetime, math, os
from pathlib import Path

workspace = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
today = datetime.date.today().isoformat()

# ---------- loaders ----------
def load_json(name):
    p = workspace / name
    if not p.exists():
        return None
    return json.loads(p.read_text())

# ---------- backtest stats lookup ----------
bt_stats = {}
bt_raw = load_json('backtest_summary.json')
if bt_raw:
    for row in bt_raw.get('summary', []):
        broker = row.get('broker') or row.get('symbol')  # some versions broker=unknown_fx
        sym = row.get('symbol')
        side = (row.get('side') or '').lower()
        if not sym or not side:
            continue
        key = (sym, side)
        # merge if multiple brokers
        prev = bt_stats.get(key, {})
        bt_stats[key] = {
            'count': prev.get('count', 0) + row.get('count', 0),
            'win_rate': row.get('win_rate') if row.get('win_rate') is not None else prev.get('win_rate'),
            'expectancy': row.get('expectancy') if row.get('expectancy') is not None else prev.get('expectancy'),
            'avg_loss': row.get('avg_loss') if row.get('avg_loss') is not None else prev.get('avg_loss'),
        }

# ---------- optional news sentiment ----------
sentiment_path = workspace / f'news_sentiment_{today}.json'
news_sentiment = {}
if sentiment_path.exists():
    try:
        news_sentiment = json.loads(sentiment_path.read_text())
    except Exception:
        news_sentiment = {}

# ---------- scoring helpers ----------
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

# fixed conviction max weights:
# RSI 30, MACD 30, BB 25, VOL 15 => 100 max
def technical_score(rsi, macd_bias, price, bb_lower, bb_upper, bb_middle, rr=None, atr=None, entry=None, sl=None):
    score = 0
    rp = normalize_rsi_score(rsi)
    score += rp

    # MACD 30 max
    if macd_bias == 'bullish':
        score += 30
    elif macd_bias == 'bearish':
        score += 20
    else:
        score += 0

    # BB 25 max
    if price is not None and bb_lower is not None and bb_upper is not None:
        if price < bb_lower:
            score += 25
        elif bb_upper is not None and bb_middle is not None and (bb_upper - bb_middle) < 0.05 * bb_middle:
            score += 15

    # Volume = unknown in current scan outputs; keep 0
    vol_p = 0

    # backtest modifier for this symbol+side
    side_map = {'bullish': 'buy', 'bearish': 'sell'}
    direction = 'bullish' if sl is not None and entry is not None and sl < entry else 'bearish' if sl is not None and entry is not None and sl > entry else None
    bst_mod = 0.0
    bst_stats = None
    if direction:
        side_norm = side_map.get(direction)

        def sym_alias(sym):
            sym = (sym or '').upper()
            if sym.endswith('USD') and not sym.endswith('USDT'):
                return sym
            if sym.endswith('USDT'):
                return sym[:-1]
            return sym

        base = sym_alias(setup['symbol'])
        candidates = [
            (base, side_norm),
            (base.replace('USD', 'USDT') if 'USD' in base else base, side_norm),
            (base, direction),
            (base, 'buy'),
            (base, 'long'),
            (base, 'sell'),
            (base, 'short'),
        ]
        for try_key in candidates:
            candidate = bt_stats.get(try_key)
            if candidate:
                bst_stats = candidate
                bst_mod = (max(-40.0, min(40.0, (candidate.get('win_rate') or 0.0 - 0.5) * 100)) + max(-25.0, min(25.0, (candidate.get('expectancy') or 0.0) * 5))) * min(1.0, max(0.0, (candidate.get('count', 0) or 0) / 20))
                break

    return max(0, min(100, score + bst_mod)), {'rsi_p': rp, 'macd_p': 30 if macd_bias=='bullish' else 20 if macd_bias=='bearish' else 0, 'bb_p': 25 if price is not None and price < (bb_lower or 9999) else 0, 'vol_p': vol_p}

def backtest_modifier(symbol, side, rr):
    # separate BT lookup since we don't have broker reliably
    key = (symbol, (side or '').lower())
    stats = bt_stats.get(key)
    if not stats:
        key2 = (symbol.upper(), key[1])
        stats = bt_stats.get(key2)
    if not stats:
        return 0, None
    wr = stats.get('win_rate')
    exp = stats.get('expectancy')
    mod = 0
    if wr is not None:
        mod += max(-40, min(40, (wr - 0.5) * 100))  # +/-40 max around 50%
    if exp is not None:
        # clamp contribution
        mod += max(-20, min(20, exp * 4))
        # risk-normalize by rr if present
    rr_norm = max(rr or 1, 1)
    # If BT sample tiny, reduce modifier weight
    count = stats.get('count', 0)
    confidence = min(1.0, max(0.0, count / 20))
    return mod * confidence, stats

# ---------- load ranked setups from multiple sources ----------
candidates = []
sources = [
    'cerebro_backtest_ranked_setups_2026-07-29.json',
    'all_market_ranked_setups_2026-07-29_open.json',
    'all_sector_ranked_setups_2026-07-29.json',
    'pre_market_proposed_setups_2026-07-29.json',
]
for src in sources:
    raw = load_json(src)
    if not raw:
        continue
    setups = raw.get('top', raw.get('ranked_setups', []))
    if not setups:
        continue
    for s in setups:
        # normalize keys
        n = {
            'source_file': src,
            'broker': s.get('broker') or 'unknown',
            'symbol': (s.get('symbol') or s.get('ticker') or '').upper(),
            'bias': s.get('bias') or 'neutral',
            'entry': s.get('entry') or s.get('proposed_entry') or s.get('price'),
            'sl': s.get('sl') or s.get('stop'),
            'tp': s.get('tp') or s.get('target'),
            'rr': s.get('rr'),
            'rsi': s.get('rsi') or s.get('rsi14') or s.get('rsi_14'),
            'atr': s.get('atr') or s.get('atr14') or s.get('atr_14'),
            'route': s.get('route'),
            'timeframe': s.get('timeframe'),
            'execution_status': s.get('execution_status'),
        }
        if not n['symbol']:
            continue
        candidates.append(n)

# deduplicate by strongest route per symbol/bias
best_route = {}
for c in candidates:
    k = (c['symbol'], c['bias'])
    prev = best_route.get(k)
    if not prev or ((c.get('rsi') or 0) > (prev.get('rsi') or 0)):
        best_route[k] = c
unique = list(best_route.values())

# ---------- score each setup ----------
scan_results = []
for setup in unique:
    rsi = setup.get('rsi')
    bias = setup.get('bias')
    rr = setup.get('rr')
    atr = setup.get('atr')
    price = setup.get('entry')
    sl = setup.get('sl')
    tp = setup.get('tp')
    tech, comp = technical_score(rsi, bias, price, None, None, None, rr, atr, price, sl)

    side = 'buy' if bias == 'bullish' else 'sell' if bias == 'bearish' else 'neutral'
    bst_mod, bst_stats = backtest_modifier(setup['symbol'], side, rr)
    bst_score = max(0, min(100, tech + bst_mod))

    # analyst/news sentiment: 0-100 from news, else 50 neutral
    sentiment = news_sentiment.get(setup['symbol'], {})
    sentiment_score = sentiment.get('score') if isinstance(sentiment, dict) else None
    if sentiment_score is None and isinstance(sentiment, (int, float)):
        sentiment_score = sentiment * 100
    if sentiment_score is None:
        sentiment_score = 50.0

    analyst_score = sentiment_score
    freshness = 1.0 if bst_stats and bst_stats.get('count') else 0.5

    composite = round(
        0.35 * bst_score +
        0.35 * tech +
        0.15 * analyst_score +
        0.10 * ((rr or 1) * 20) +
        0.05 * (100 if setup.get('sl') and setup.get('tp') else 40)
    )
    composite = max(0, min(100, composite))

    scan_results.append({
        **setup,
        'technical_score': tech,
        'technical_components': comp,
        'bst_score': round(bst_score, 2),
        'bst_backtest': {
            'symbol': setup['symbol'],
            'side': side,
            'win_rate': bst_stats.get('win_rate') if bst_stats else None,
            'expectancy': bst_stats.get('expectancy') if bst_stats else None,
            'count': bst_stats.get('count') if bst_stats else 0,
        },
        'analyst_score': round(analyst_score, 2),
        'sentiment_score': round(sentiment_score, 2),
        'composite_score': round(composite, 2),
        'meta': {
            'source_count': len(unique),
            'scored_count': len(scan_results),
        }
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
    'meta': {'inputs': sources, 'backtest_rows': len(bt_stats), 'news_sentiment_source': str(sentiment_path) if sentiment_path.exists() else 'none'},
    'top': scan_results[:20],
    'best_buy_setups': best_buys,
    'best_sell_setups': best_sells,
}

out_path = workspace / f'ranked_setups_composite_{today.replace("-", "")}.json'
out_path.write_text(json.dumps(out, indent=2))

print('WROTE', out_path)
print('TOTAL_SCORED', len(scan_results))
print('BEST_BUY')
for b in best_buys[:5]:
    print(b['symbol'], b['bias'], 'composite', b['composite_score'], 'bst', b['bst_score'], 'analyst', b['analyst_score'])
print('BEST_SELL')
for b in best_sells[:5]:
    print(b['symbol'], b['bias'], 'composite', b['composite_score'], 'bst', b['bst_score'], 'analyst', b['analyst_score'])
print('ALL_TOP')
for r in scan_results[:10]:
    print(r['symbol'], r['bias'], 'composite', r['composite_score'], 'bst', r['bst_score'], 'tech', r['technical_score'], 'analyst', r['analyst_score'], 'rr', r['rr'], 'route', r.get('route'))
