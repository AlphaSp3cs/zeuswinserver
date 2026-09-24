#!/usr/bin/env python3
"""
master_setup_grader.py
Grade all setup types on all assets from scan outputs.
- Loads all scan JSONs from workspace/reports/backtest_archive
- Normalizes setup records
- Scores: technical / backtest / analyst / rr / execution readiness
- Writes master graded outputs to scandata under the user Desktop folder

Upgrade: backtest-first grading with smoothness guard.
- Backtested setups are promoted, not removed.
- Unbacktested setups are downgraded, not deleted.
- Duplicates keep the highest-conviction version only.
"""
import json, sys, glob
from pathlib import Path
from datetime import datetime, timezone

from master_scanner_writer import SCANDATA, write_json, write_markdown
try:
    from backtest_registry import require_backtest, best_backtest
    REGISTRY_ENABLED = True
except Exception:
    REGISTRY_ENABLED = False

WORKSPACE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
BT_PATH = WORKSPACE / 'backtest_summary.json'
NEWS_PATH = WORKSPACE / f'news_sentiment_{datetime.now().date().isoformat()}.json'


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


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


def _normalize_for_bt(sym: str, side: str):
    for key in _normalize_symbol_keys(sym):
        yield (key, side.lower())


def load_bt():
    raw = load_json(BT_PATH)
    out = {}
    if not raw:
        try:
            raw = load_json(WORKSPACE / 'workflow' / 'backtest_master.json')
        except Exception:
            raw = None
    if raw and isinstance(raw, dict) and 'symbols' in raw:
        symbols = raw.get('symbols', {})
        for sym, entry in symbols.items():
            if not entry or not isinstance(entry, dict):
                continue
            side = 'buy' if float(entry.get('expectancy', 0) or 0) >= 0 else 'sell'
            for key in _normalize_for_bt(sym, side):
                prev = out.get(key, {})
                out[key] = {
                    'count': prev.get('count', 0) + int(entry.get('trades', 0) or 0),
                    'win_rate': entry.get('win_rate') if entry.get('win_rate') is not None else prev.get('win_rate'),
                    'expectancy': entry.get('expectancy') if entry.get('expectancy') is not None else prev.get('expectancy'),
                    'avg_loss': entry.get('avg_loss') if entry.get('avg_loss') is not None else prev.get('avg_loss'),
                }
        return out
    if not raw:
        return out
    rows = raw.get('summary', [])
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        sym = (row.get('symbol') or '').upper()
        side = (row.get('side') or row.get('bias') or '').lower()
        if not sym or not side:
            continue
        key = (sym, side)
        prev = out.get(key, {})
        out[key] = {
            'count': prev.get('count', 0) + row.get('count', row.get('trades', 0)),
            'win_rate': row.get('win_rate') if row.get('win_rate') is not None else prev.get('win_rate'),
            'expectancy': row.get('expectancy') if row.get('expectancy') is not None else prev.get('expectancy'),
            'avg_loss': row.get('avg_loss') if row.get('avg_loss') is not None else prev.get('avg_loss'),
        }
    return out


def load_news():
    raw = load_json(NEWS_PATH)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def norm_rsi(rsi):
    if rsi is None:
        return 0
    if rsi < 30:
        return 30
    if 30 <= rsi < 40:
        return 20
    if 60 <= rsi <= 70:
        return 10
    return 0


def tech_score(rsi, bias, price, sl, tp):
    rp = norm_rsi(rsi)
    mp = 30 if bias == 'bullish' else 20 if bias == 'bearish' else 0
    bp = 0
    if all(v is not None for v in [price, sl, tp]):
        if price < sl:
            bp = 25
        elif (tp - sl) and price > tp:
            bp = 0
        else:
            bp = 10
    score = max(0, min(100, rp + mp + bp))
    return score, {'rsi_p': rp, 'macd_p': mp, 'bb_p': bp, 'vol_p': 0}


def bt_modifier(symbol, side, rr, bt_stats):
    stats = bt_stats.get((symbol.upper(), side.lower()))
    if not stats:
        return 0.0, None
    wr = stats.get('win_rate') or 0.0
    exp = stats.get('expectancy') or 0.0
    mod = max(-40.0, min(40.0, (wr - 0.5) * 100)) + max(-25.0, min(25.0, exp * 5))
    confidence = min(1.0, max(0.0, (stats.get('count', 0) or 0) / 20))
    return float(mod * confidence), stats


def analyst_score(sym, news):
    sent = news.get(sym, news.get(sym.upper(), {}))
    if isinstance(sent, dict) and 'score' in sent:
        v = float(sent['score'])
        return v * 100 if 0 <= v <= 1 else v
    if isinstance(sent, (int, float)):
        v = float(sent)
        return v * 100 if 0 <= v <= 1 else v
    return 50.0


def load_scan_sources(folders):
    patterns = [
        '*setups*.json',
        '*ranked*.json',
        '*composite*.json',
        '*cerebro*.json',
        '*open*.json',
        '*pre_market*.json',
        '*sector*.json',
        '*market*.json',
    ]
    files = []
    for folder in folders:
        for pat in patterns:
            files.extend(folder.glob(pat))
    return sorted(set(files))


def extract_setups(raw: dict, source_file: str):
    setups = []
    blocks = raw.get('top', raw.get('ranked_setups', raw.get('best_buy_setups', []) + raw.get('best_sell_setups', [])))
    if not blocks and isinstance(raw, list):
        blocks = raw
    for s in blocks:
        sym = (s.get('symbol') or s.get('ticker') or '').strip().upper()
        if not sym:
            continue
        setups.append({
            'source_file': source_file,
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
    return setups


def grade_all(scan_folder: Path = WORKSPACE):
    bt = load_bt()
    news = load_news()
    sources = load_scan_sources([WORKSPACE, WORKSPACE / 'reports', WORKSPACE / 'backtest_archive'])
    print(f'Scanning {len(sources)} source files in {scan_folder}')

    candidates = []
    for src in sources:
        raw = load_json(src)
        if not raw:
            continue
        candidates.extend(extract_setups(raw, src.name))

    # dedupe best route per symbol/bias by RSI strength
    best = {}
    for c in candidates:
        k = (c['symbol'], c['bias'])
        prev = best.get(k)
        if prev is None or (c.get('rsi') or 0) > (prev.get('rsi') or 0):
            best[k] = c
    unique = list(best.values())
    print(f'Unique setups: {len(unique)} from {len(candidates)} raw')

    results = []
    seen = {}
    for setup in unique:
        rsi = setup.get('rsi')
        bias = setup.get('bias')
        price = setup.get('entry')
        sl = setup.get('sl')
        tp = setup.get('tp')
        rr = float(setup.get('rr') or 2.0)

        tech, comp = tech_score(rsi, bias, price, sl, tp)
        side = 'buy' if bias == 'bullish' else 'sell' if bias == 'bearish' else 'neutral'
        bst_delta, bst_stats = bt_modifier(setup['symbol'], side, rr, bt)
        bst_score = max(0.0, min(100.0, float(tech) + bst_delta))

        # Upgrade: backtest-first smoothness guard
        bt_pass = False
        bt_entry = None
        if REGISTRY_ENABLED:
            try:
                bt_pass = require_backtest(setup['symbol'], min_win_rate=0.55, min_expectancy=0.0)
                bt_entry = best_backtest(setup['symbol'])
            except Exception:
                bt_pass = False
                bt_entry = None

        if bt_pass:
            bst_score = min(100.0, bst_score + 15)
        else:
            bst_score = max(0.0, bst_score - 10)

        analyst = analyst_score(setup['symbol'], news)
        readiness = 100.0 if sl and tp else 40.0

        # Additive overlay: Trading in the Zone discipline layer
        zone_discipline = 100.0
        if not sl or not tp:
            zone_discipline -= 40.0
        if not bt_pass:
            zone_discipline -= 15.0
        zone_discipline = max(0.0, min(100.0, zone_discipline))

        effective_tech = tech if rsi is not None else max(0, tech - 20)
        composite = round(
            0.35 * bst_score +
            0.35 * effective_tech +
            0.15 * analyst +
            0.10 * min(rr * 20, 100) +
            0.05 * readiness +
            0.05 * zone_discipline,
        )
        composite = max(0, min(100, composite))

        graded = {
            **setup,
            'technical_score': float(effective_tech),
            'technical_components': comp,
            'bst_score': round(bst_score, 2),
            'bst_backtest': {
                'symbol': setup['symbol'],
                'side': side,
                'win_rate': bst_stats.get('win_rate') if bst_stats else None,
                'expectancy': bst_stats.get('expectancy') if bst_stats else None,
                'count': bst_stats.get('count') if bst_stats else 0,
            },
            'analyst_score': round(analyst, 2),
            'composite_score': round(composite, 2),
            'zone_discipline': round(zone_discipline, 2),
            'backtest_pass': bool(bt_pass),
            'backtest_entry': bt_entry,
        }

        # Upgrade: dedupe keeps highest conviction version only
        dk = (setup['symbol'], bias)
        prev = seen.get(dk)
        if prev is None or composite > prev.get('composite_score', 0):
            seen[dk] = graded

    results = list(seen.values())
    results.sort(key=lambda x: (x.get('backtest_pass', False), x['composite_score'], x['bst_score'], x['technical_score']), reverse=True)
    best_buys = [r for r in results if r['bias'] == 'bullish'][:12]
    best_sells = [r for r in results if r['bias'] == 'bearish'][:12]

    out = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'weights': {
            'bst_score': 0.35,
            'technical_score': 0.35,
            'analyst_news_sentiment': 0.15,
            'rr': 0.10,
            'execution_readiness': 0.05,
            'zone_discipline': 0.05,
        },
        'meta': {
            'inputs': [p.name for p in sources],
            'backtest_rows': len(bt),
            'news_sentiment_source': str(NEWS_PATH) if NEWS_PATH.exists() else 'none',
            'unique_setups_scored': len(results),
        },
        'top': results[:50],
        'best_buy_setups': best_buys,
        'best_sell_setups': best_sells,
    }

    json_path = write_json('MASTER_GRADED_SETUPS', out)
    lines = []
    lines.append(f'# Master Graded Setups {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    lines.append(f'Unique setups: {len(results)} | Sources: {len(sources)} | Backtest rows: {len(bt)}')
    lines.append('')
    lines.append('## Best Buys')
    for r in best_buys[:12]:
        lines.append(f"- {r['symbol']} {r['bias']} composite={r['composite_score']} bst={r['bst_score']} tech={r['technical_score']} analyst={r['analyst_score']} rr={r.get('rr')} route={r.get('route')}")
    lines.append('')
    lines.append('## Best Sells')
    for r in best_sells[:12]:
        lines.append(f"- {r['symbol']} {r['bias']} composite={r['composite_score']} bst={r['bst_score']} tech={r['technical_score']} analyst={r['analyst_score']} rr={r.get('rr')} route={r.get('route')}")
    md_path = write_markdown('MASTER_GRADED_SETUPS', '\n'.join(lines))
    print(f'Wrote JSON: {json_path}')
    print(f'Wrote MD: {md_path}')
    return out


if __name__ == '__main__':
    grade_all()
