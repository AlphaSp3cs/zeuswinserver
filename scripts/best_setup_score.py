#!/usr/bin/env python3
"""
best_setup_score.py
-------------------
Post-scan highest-probability setup selector.

Workflow:
 1. Load scan outputs and backtest history
 2. Normalize duplicate symbol/bias pairs across all scan files
 3. Build per-setup scores:
    - technical_score: 0-100
    - bst_score: technical + backtest modifier, clamped 0-100
    - analyst_score: news/analyst source, 0-100, neutral 50 if missing
 4. composite_score = weighted fusion
 5. Populate:
    - best_buy_setups[:8]
    - best_sell_setups[:8]
 6. Write dated ranked_setups_composite file and a human summary
"""

import json
import datetime
from pathlib import Path

workspace = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
today = datetime.date.today().isoformat()


def load_json(name):
    p = workspace / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Backtest lookup / BST modifier
# ---------------------------------------------------------------------------
BT = {}
bt_raw = load_json('backtest_summary.json')
if bt_raw:
    for row in bt_raw.get('summary', []):
        sym = row.get('symbol')
        side = (row.get('side') or '').lower()
        if not sym or not side:
            continue
        key = (sym.upper(), side)
        prev = BT.get(key, {})
        BT[key] = {
            'count': prev.get('count', 0) + row.get('count', 0),
            'win_rate': row.get('win_rate') if row.get('win_rate') is not None else prev.get('win_rate'),
            'expectancy': row.get('expectancy') if row.get('expectancy') is not None else prev.get('expectancy'),
            'avg_loss': row.get('avg_loss') if row.get('avg_loss') is not None else prev.get('avg_loss'),
        }


def symbol_aliases(sym):
    sym = (sym or '').upper()
    if sym.endswith('USD') and not sym.endswith('USDT'):
        return [sym, sym + 'T']
    if sym.endswith('USDT'):
        return [sym, sym[:-1]]
    return [sym]


def bst_for(sym, bias, rr):
    side = 'buy' if bias == 'bullish' else 'sell' if bias == 'bearish' else 'neutral'
    stats = None
    for cand in symbol_aliases(sym):
        for s in [side, bias, 'buy', 'long', 'sell', 'short']:
            stats = BT.get((cand, s))
            if stats:
                break
        if stats:
            break
    if not stats:
        return 0.0, None
    count = max(stats.get('count', 0), 1)
    confidence = max(0.0, min(1.0, count / 20))
    wr = stats.get('win_rate') or 0.0
    exp = stats.get('expectancy') or 0.0
    mod = max(-40.0, min(40.0, (wr - 0.5) * 100)) + max(-25.0, min(25.0, exp * 5))
    return float(mod * confidence), stats

# ---------------------------------------------------------------------------
# Technical score / fixed weights: RSI 30 / MACD 30 / BB 25 / Vol 15
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


def technical_score_for(rsi, bias, price, sl, tp):
    rp = normalize_rsi_score(rsi)
    mp = 30 if bias == 'bullish' else 20 if bias == 'bearish' else 0
    bp = 0
    if price is not None and sl is not None and tp is not None:
        if price < sl:
            bp = 25
        elif (tp - sl) and price > tp:
            bp = 0
        else:
            bp = 10
    score = max(0, min(100, rp + mp + bp))
    comp = {'rsi_p': rp, 'macd_p': mp, 'bb_p': bp, 'vol_p': 0}
    return score, comp

# ---------------------------------------------------------------------------
# News/Analyst
# ---------------------------------------------------------------------------
sentiment_path = workspace / f'news_sentiment_{today}.json'
news_sentiment = load_json(sentiment_path) if sentiment_path.exists() else {}


def analyst_score_for(sym):
    sent = news_sentiment.get(sym)
    if isinstance(sent, dict) and 'score' in sent:
        v = sent.get('score')
        if isinstance(v, (int, float)):
            return float(v * 100) if 0 <= float(v) <= 1 else float(v)
    if isinstance(sent, (int, float)):
        return float(sent * 100) if 0 <= float(sent) <= 1 else float(sent)
    return 50.0

# ---------------------------------------------------------------------------
# Load scan candidates
# ---------------------------------------------------------------------------
SURCES = [
    'cerebro_backtest_ranked_setups_2026-07-29.json',
    'all_market_ranked_setups_2026-07-29_open.json',
    'all_sector_ranked_setups_2026-07-29.json',
    'pre_market_proposed_setups_2026-07-29.json',
]


def extract_setups(raw):
    setups = raw.get('top', raw.get('ranked_setups', [])) if raw else []
    out = []
    for s in setups:
        sym = (s.get('symbol') or s.get('ticker') or '').strip().upper()
        if not sym:
            continue
        out.append({
            'source_file': raw.get('_source_file'),
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
    return out


candidates = []
for src in SURCES:
    raw = load_json(src)
    if raw:
        raw['_source_file'] = src  # carrier field for clarity
        candidates.extend(extract_setups(raw))

# Dedupe: best route per (symbol, bias) by RSI strength
best_route = {}
for c in candidates:
    k = (c['symbol'], c['bias'])
    prev = best_route.get(k)
    if prev is None or (c.get('rsi') or 0) > (prev.get('rsi') or 0):
        best_route[k] = c
unique = list(best_route.values())

# ---------------------------------------------------------------------------
# Score + populate lists
# ---------------------------------------------------------------------------
scored = []
for setup in unique:
    rsi = setup.get('rsi')
    bias = setup.get('bias')
    price = setup.get('entry')
    sl = setup.get('sl')
    tp = setup.get('tp')
    rr = float(setup.get('rr') or 2.0)

    tech, comp = technical_score_for(rsi, bias, price, sl, tp)
    bst_delta, bst_stats = bst_for(setup['symbol'], bias, rr)
    bst_score = max(0.0, min(100.0, float(tech) + bst_delta))
    analyst = analyst_score_for(setup['symbol'])
    readiness = 100.0 if sl and tp else 40.0

    # Gated weighting: if technical null or setup incomplete, reduce composite
    effective_tech = tech if rsi is not None else max(0, tech - 20)

    composite = round(
        0.35 * bst_score +
        0.35 * effective_tech +
        0.15 * analyst +
        0.10 * min(rr * 20, 100) +
        0.05 * readiness,
    )
    composite = max(0, min(100, composite))

    scored.append({
        **setup,
        'technical_score': float(effective_tech),
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

scored.sort(key=lambda x: (x['composite_score'], x['bst_score'], x['technical_score']), reverse=True)

best_buys = [s for s in scored if s['bias'] == 'bullish'][:8]
best_sells = [s for s in scored if s['bias'] == 'bearish'][:8]

out = {
    'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
    'method': 'best_setup_score_v1',
    'weights': {
        'bst_score': 0.35,
        'technical_score': 0.35,
        'analyst_news_sentiment': 0.15,
        'rr': 0.10,
        'execution_readiness': 0.05,
    },
    'meta': {
        'inputs': SURCES,
        'backtest_rows': len(BT),
        'news_sentiment_source': str(sentiment_path) if sentiment_path.exists() else 'none',
        'unique_setups_scored': len(scored),
    },
    'top': scored[:20],
    'best_buy_setups': best_buys,
    'best_sell_setups': best_sells,
}

ts = datetime.datetime.utcnow().strftime('%Y%m%d%H%M')
out_path = workspace / f'ranked_setups_composite_{ts}.json'
out_path.write_text(json.dumps(out, indent=2))

# Human summary for terminal / ops use

def fmt_setup(r):
    return (
        f"{r['symbol']:<12} {r['bias']:<8} "
        f"composite={r['composite_score']:<5} bst={r['bst_score']:<6} "
        f"tech={r['technical_score']:<5} analyst={r['analyst_score']:<6} "
        f"rr={r.get('rr')} route={r.get('route')}"
    )

print('WROTE', out_path)
print('UNIQUE_SCORED', len(scored))
print('BEST_BUY_SETUPS')
for b in best_buys[:8]:
    print(fmt_setup(b))
print('BEST_SELL_SETUPS')
for b in best_sells[:8]:
    print(fmt_setup(b))
