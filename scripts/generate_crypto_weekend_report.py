#!/usr/bin/env python3
"""
Generate the official unified crypto weekend scan report.
- 8-section format per CRYPTO_WEEKEND_SCAN_SPEC.md
- Reads: ALL_SECTOR_QUANT_CONVICTION_*.json, workflow/crypto_data.db,
         workflow/backtest_master.json, workflow/whale_investor_tracker.json,
         scripts/crypto_news_engine.py, correlation/gap/bar artifacts
- Outputs: WEEKEND_CRYPTO_SCAN_<YYYY-MM-DD>.md and .json
"""
import json, sqlite3, sys, os, re
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'
SCRIPTS = BASE / 'scripts'

# ── helpers ──────────────────────────────────────────────────────────────────
def latest(pattern_func):
    candidates = sorted(WORKFLOW.glob(pattern_func()), reverse=True)
    if not candidates:
        candidates = sorted(BASE.glob(pattern_func()), reverse=True)
    return candidates[0] if candidates else None

def load_json(path):
    if path and path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}

def db_row(sql, params=()):
    db = WORKFLOW / 'crypto_data.db'
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []

def pct(num, digits=2):
    if num is None:
        return 'N/A'
    try:
        return f"{float(num):.{digits}%}"
    except Exception:
        return 'N/A'

def grade_from_score(score):
    try:
        s = float(score)
    except Exception:
        return 'AVOID'
    if s >= 4:
        return 'ACCUMULATE'
    if s >= 2:
        return 'MIXED'
    return 'AVOID'

# ── load sources ──────────────────────────────────────────────────────────────
all_sector_path = latest(lambda: 'ALL_SECTOR_QUANT_CONVICTION_*.json')
all_sector = load_json(all_sector_path) or {}
all_setups = all_sector.get('setups', [])
regime = all_sector.get('regime', 'NEUTRAL')

broker_state = all_sector.get('broker_state', {})

backtest_master = load_json(WORKFLOW / 'backtest_master.json') or {}
bt_symbols = backtest_master.get('symbols', {})

whale = load_json(WORKFLOW / 'whale_investor_tracker.json') or {}
whale_matrix = whale.get('matrix', {})

# weekend scanner latest results
scanner_rows = db_row('''
    SELECT symbol, price_usd, change_24h_pct, change_7d_pct, rsi_14,
           volume_24h, volume_7d_avg, score_grade, buy_setup, signal_type, urgency, timestamp
    FROM crypto_scan_results
    ORDER BY timestamp DESC LIMIT 200
''')
# dedupe to latest per symbol
scanner_latest = {}
for row in scanner_rows:
    sym = row.get('symbol')
    if sym and sym not in scanner_latest:
        scanner_latest[sym] = row

# tickets
tickets = db_row("SELECT * FROM dca_tickets WHERE status='READY' ORDER BY created_at DESC")

# whale overlap helper
def whale_overlaps(symbol):
    hits = []
    for whale_name, info in whale_matrix.items():
        if symbol in (info.get('watchlist_overlap') or []):
            hits.append(whale_name)
    return hits

# correlation / bar / gap
corr_path = latest(lambda: 'correlation_validation_*.json')
corr = load_json(corr_path) or {}
bar_path = latest(lambda: 'bar_quality_*.json')
bar = load_json(bar_path) or {}
gap_path = latest(lambda: 'gap_register_*.json')
gap = load_json(gap_path) or {}

# metals / commodities / stocks from all-sector for linkage
materials = [s for s in all_setups if s.get('sector') == 'Materials']
energy = [s for s in all_setups if s.get('sector') == 'Energy']
financials = [s for s in all_setups if s.get('sector') == 'Financials']

# crypto setups from all-sector
crypto_setups = [s for s in all_setups if 'Crypto' in s.get('sector', '') or s.get('symbol') in [
    'BTC','ETH','SOL','AVAX','AAVE','LINK','DOGE','XMR','UNI','DOT','LTC','ATOM','NEAR','ARB','OP','FET','AGIX','WLD','MKR','CRV'
]]

# ── backtest metrics ──────────────────────────────────────────────────────────
def backtest_metrics(symbol):
    # try multiple ticker formats
    for key in [symbol, symbol.upper(), symbol.lower(), f"{symbol}-USD", f"{symbol}USD", f"{symbol.upper()}-USD", f"{symbol.upper()}USD"]:
        entry = bt_symbols.get(key)
        if entry:
            return entry
    return {}

def fmt_bt(symbol):
    m = backtest_metrics(symbol)
    if not m:
        return 'NO_BACKTEST'
    wr = m.get('win_rate')
    exp = m.get('expectancy')
    trades = m.get('trades')
    med = m.get('median_r')
    worst = m.get('worst_r')
    parts = []
    if wr is not None:
        parts.append(f"WR={pct(wr)}")
    if exp is not None:
        parts.append(f"exp={exp:.3f}R")
    if trades is not None:
        parts.append(f"n={trades}")
    if med is not None:
        parts.append(f"median={med:.2f}R")
    if worst is not None:
        parts.append(f"worst={worst:.2f}R")
    return ', '.join(parts) if parts else 'NO_BACKTEST'

# ── news engine integration ───────────────────────────────────────────────────
news_report = None
try:
    sys.path.insert(0, str(SCRIPTS))
    import crypto_news_engine as cne
    news_report = cne.run_pipeline(mode='json')
except Exception:
    news_report = None

news_alerts = []
news_tone = 'NEUTRAL'
news_themes = []
if isinstance(news_report, dict):
    news_alerts = news_report.get('alerts', [])
    news_tone = news_report.get('tone', 'NEUTRAL')
    news_themes = news_report.get('themes', [])

# ── regime-aware sizing ───────────────────────────────────────────────────────
def regime_size(base_pct, score):
    try:
        s = float(score)
    except Exception:
        return base_pct
    if regime in ('RISK-OFF', 'BEARISH'):
        if s >= 6:
            return base_pct
        return base_pct * 0.5
    return base_pct

# ── build report ──────────────────────────────────────────────────────────────
now_utc = datetime.now(timezone.utc)
ts = now_utc.strftime('%Y-%m-%dT%H%M%SZ')
out_md = BASE / f'WEEKEND_CRYPTO_SCAN_{now_utc:%Y-%m-%d}.md'
out_json = BASE / f'WEEKEND_CRYPTO_SCAN_{now_utc:%Y-%m-%d}.json'

# top gaps
top_gap_up = sorted(gap.get('top_gap_up', []), key=lambda x: x.get('pct', 0), reverse=True)[:5]
top_gap_down = sorted(gap.get('top_gap_down', []), key=lambda x: x.get('pct', 0))[:5]

lines = []
lines.append('# WEEKEND CRYPTO SCAN — OFFICIAL')
lines.append(f'**Generated:** {now_utc.isoformat()}')
lines.append(f'**Source:** {all_sector_path.name if all_sector_path else "N/A"}')
lines.append(f'**Scanner DB:** {WORKFLOW / "crypto_data.db"}')
lines.append(f'**Backtest Registry:** {WORKFLOW / "backtest_master.json"}')
lines.append(f'**Regime:** {regime}')
lines.append('')

# SECTION 1: Macro / News Guidance
lines.append('## 1) World Events / Finance / Banking / War Impact on Crypto')
lines.append('')
lines.append('### News Tone')
lines.append(f'- **{news_tone}**')
if news_alerts:
    lines.append('')
    lines.append('### Active News Alerts')
    for a in news_alerts[:8]:
        lines.append(f"- [{a.get('urgency','MEDIUM')}] {a.get('theme')}: {', '.join(a.get('reasons',[]))}")
if news_themes:
    lines.append('')
    lines.append('### Theme Summary')
    for t in news_themes[:10]:
        dollar = f" ${t.get('max_dollar',0):,.0f}" if t.get('max_dollar') else ''
        lines.append(f"- {t.get('theme')}: n={t.get('n')} | {t.get('outlets')} outlets | {t.get('impact')}{dollar}")
lines.append('')

# SECTION 2: Correlation with All-Sector Scan
lines.append('## 2) Correlation with All-Sector Scan')
lines.append('')
lines.append('| Symbol | Sector | Side | Price | RSI | Score | Broker | Backtested | Correlation |')
lines.append('|--------|--------|------|-------|-----|-------|--------|------------|-------------|')
for s in crypto_setups[:20]:
    whale_hits = whale_overlaps(s.get('symbol',''))
    whale_note = f"Whale overlap: {', '.join(whale_hits)}" if whale_hits else 'No whale overlap'
    bt_note = 'YES' if s.get('backtested') else 'NO'
    corr_note = ''
    sym = s.get('symbol','')
    if sym == 'ETH':
        corr_note = 'ETH/Equities correlation weakening; yield-bearing tech asset'
    elif sym == 'SOL':
        corr_note = 'Competes for stablecoin/DEX settlement; correlation to ETH may invert'
    elif sym == 'AAVE':
        corr_note = 'DeFi blue chips correlate with ETH; 2x ETH beta typical'
    elif sym == 'DOGE':
        corr_note = 'High-beta to risk sentiment; avoid until funding/vol stabilizes'
    elif sym == 'XMR':
        corr_note = 'Privacy coins correlate to regulatory tone'
    elif sym == 'LINK':
        corr_note = 'Oracles correlate to DeFi activity; tracks ETH with amplification'
    else:
        corr_note = whale_note
    row = f"| {sym} | {s.get('sector','')} | {s.get('side','')} | {s.get('price','')} | {s.get('rsi','')} | {s.get('score','')} | {s.get('broker','')} | {bt_note} | {corr_note} |"
    lines.append(row)
lines.append('')

# SECTION 3: Weekend Scanner Results
lines.append('## 3) Weekend Scanner Results')
lines.append('')
universe_size = len(scanner_latest)
buy_count = sum(1 for r in scanner_latest.values() if r.get('buy_setup') or (r.get('score_grade') in ('ACCUMULATE','MIXED')))
sell_count = len(tickets)  # approximate from tickets
lines.append(f'- **Universe:** {universe_size} assets with data')
lines.append(f'- **Buy setups:** {buy_count}')
lines.append(f'- **Tickets ready:** {sell_count}')
lines.append('')
buy_sorted = sorted([r for r in scanner_latest.values() if r.get('buy_setup') or r.get('score_grade') in ('ACCUMULATE','MIXED')], key=lambda x: x.get('score_grade',''), reverse=True)[:10]
if buy_sorted:
    lines.append('### Top BUY Setups')
    for r in buy_sorted:
        lines.append(f"- {r.get('symbol')}: RSI={r.get('rsi_14')}, 24h={r.get('change_24h_pct')}, Grade={r.get('score_grade')}, Score={r.get('score_grade')}")
lines.append('')

# SECTION 4: High-Conviction Setups
lines.append('## 4) High-Conviction Setups with Backtest and News')
lines.append('')
high = [s for s in crypto_setups if s.get('score', 0) >= 45 and s.get('backtested')]
high.sort(key=lambda x: x.get('score', 0), reverse=True)
for s in high[:8]:
    sym = s.get('symbol')
    bt = backtest_metrics(sym)
    bt_str = fmt_bt(sym)
    whale_hits = whale_overlaps(sym)
    whale_boost = f" | **Whale overlap:** {', '.join(whale_hits)}" if whale_hits else ''
    entry = s.get('entry', s.get('price'))
    sl = s.get('sl')
    tp = s.get('tp')
    rr = s.get('rr', 2.0)
    size = regime_size(0.01, s.get('score'))
    tp2 = entry * (1 + rr * size) if s.get('side') == 'LONG' and entry else 0
    lines.append(f"### {sym} — {s.get('side','')}")
    lines.append(f"- **Current zone:** ~${s.get('price')}")
    lines.append(f"- **All-sector score:** {s.get('score')}, RSI {s.get('rsi')}, ADX {s.get('adx')}, RR {rr}")
    lines.append(f"- **Backtest:** {bt_str}{whale_boost}")
    # news proxy from scanner reasons or whale notes
    reason_note = ''
    slatest = scanner_latest.get(sym) or {}
    if slatest.get('signal_type'):
        reason_note = slatest.get('signal_type')
    if whale_hits:
        reason_note += (' | ' if reason_note else '') + f"Whale holders: {', '.join(whale_hits)}"
    lines.append(f"- **Signal reasons:** {reason_note or 'See all-sector scan'}")
    lines.append(f"- **Risk events:** Below SL={sl}; 10Y yield spike; ETF flow reversal")
    lines.append(f"- **Trade plan:**")
    lines.append(f"  - Entry: {entry}")
    lines.append(f"  - SL: {sl}")
    lines.append(f"  - TP1: {tp}")
    lines.append(f"  - TP2: {tp2}")
    lines.append(f"  - Size: {pct(size*100, digits=1)} equity")
    lines.append(f"  - Broker: {s.get('broker','KRAKEN') if s.get('executable') else 'QUEUED'}")
    grade = grade_from_score(s.get('score'))
    lines.append(f"- **Conviction:** {grade}")
    lines.append('')
lines.append('')

# SECTION 5: Breakout / Breakdown Watchlist
lines.append('## 5) Breakout / Breakdown Watchlist')
lines.append('')
bullish = [s for s in crypto_setups if s.get('side') == 'LONG' and s.get('score', 0) >= 40]
bearish = [s for s in crypto_setups if s.get('side') == 'SHORT' and s.get('score', 0) >= 10]
lines.append('### Bullish breakout candidates')
for s in bullish[:5]:
    lines.append(f"- **{s.get('symbol')} > ${s.get('tp')}**: score={s.get('score')}, RSI={s.get('rsi')}, catalyst={s.get('sector')}")
lines.append('')
lines.append('### Bearish breakdown risks')
for s in bearish[:5]:
    lines.append(f"- **{s.get('symbol')} < ${s.get('sl')}**: score={s.get('score')}, RSI={s.get('rsi')}, catalyst={s.get('sector')}")
lines.append('')

# SECTION 6: Swing Setups
lines.append('## 6) Swing Setups')
lines.append('')
swing = [s for s in crypto_setups if s.get('score', 0) >= 35 and s.get('backtested')]
swing.sort(key=lambda x: x.get('score', 0), reverse=True)
for s in swing[:6]:
    entry = s.get('entry', s.get('price'))
    sl = s.get('sl')
    tp = s.get('tp')
    bt = fmt_bt(s.get('symbol'))
    lines.append(f"### {s.get('symbol')} — {s.get('side','')} swing")
    lines.append(f"- Entry trigger: {entry} | Invalidation: {sl} | Target: {tp}")
    lines.append(f"- Backtest: {bt}")
    lines.append(f"- Timeframe: 3d–4w | Size: {regime_size(0.01, s.get('score'))*100:.1f}% equity")
    lines.append('')
if not swing:
    lines.append('No swing setups this cycle.')
    lines.append('')

# SECTION 7: Historically Bottomed-Out
lines.append('## 7) Historically Bottomed-Out')
lines.append('')
# RSI deep oversold with large drawdown assumption
deep_oversold = sorted([s for s in crypto_setups if s.get('rsi') is not None and float(s.get('rsi', 99)) < 30], key=lambda x: float(x.get('rsi', 99)))
if deep_oversold:
    for s in deep_oversold[:6]:
        rsi = s.get('rsi')
        lines.append(f"- **{s.get('symbol')}**: RSI {rsi}, score={s.get('score')}, grade={grade_from_score(s.get('score'))}")
        lines.append(f"  - Backtest: {fmt_bt(s.get('symbol'))}")
        lines.append(f"  - Broker: {s.get('broker') if s.get('executable') else 'QUEUED'}")
else:
    lines.append('No historically bottomed-out assets this cycle.')
lines.append('')

# SECTION 8: Metals / Commodities / Stock Correlation
lines.append('## 8) Metals / Commodities / Stock Correlation')
lines.append('')
lines.append('### Materials / Metals')
if materials:
    for s in materials[:4]:
        lines.append(f"- **{s.get('symbol')}** ({s.get('sector')}): {s.get('side')} score={s.get('score')} RSI={s.get('rsi')}")
        if s.get('symbol') == 'NUE':
            lines.append('  - NUE/steel demand correlates to construction; if NUE rallies, infrastructure crypto plays may follow.')
        if s.get('symbol') == 'CLF':
            lines.append('  - CLF/iron ore correlates to China demand; risk-on for commodities benefits crypto risk assets.')
else:
    lines.append('- No materials signals this cycle.')
lines.append('')
lines.append('### Energy')
if energy:
    for s in energy[:4]:
        lines.append(f"- **{s.get('symbol')}** ({s.get('sector')}): {s.get('side')} score={s.get('score')} RSI={s.get('rsi')}")
        if s.get('symbol') == 'XOM':
            lines.append('  - XOM/oil correlation: higher oil = inflation = higher rates = pressure on BTC/ETH.')
        if s.get('symbol') == 'CVX':
            lines.append('  - CVX/oil correlation: energy strength often supports risk assets via CPI expectations.')
else:
    lines.append('- No energy signals this cycle.')
lines.append('')
lines.append('### Financials / Banking')
if financials:
    for s in financials[:4]:
        lines.append(f"- **{s.get('symbol')}** ({s.get('sector')}): {s.get('side')} score={s.get('score')} RSI={s.get('rsi')}")
        if s.get('symbol') == 'JPM':
            lines.append('  - JPM/banks: credit expansion supports crypto liquidity; bank stress = deleverage = crypto risk-off.')
        if s.get('symbol') == 'BAC':
            lines.append('  - BAC correlates to consumer credit; strong BAC = consumer strength = risk-on.')
else:
    lines.append('- No financial signals this cycle.')
lines.append('')

# footer
lines.append('---')
lines.append(f'*Report generated: {now_utc.isoformat()}*')
lines.append(f'*Spec: references/CRYPTO_WEEKEND_SCAN_SPEC.md*')

report_md = '\n'.join(lines)
out_md.write_text(report_md, encoding='utf-8')

# JSON artifact
artifact = {
    'generated': now_utc.isoformat(),
    'spec': 'CRYPTO_WEEKEND_SCAN_SPEC.md',
    'regime': regime,
    'sources': {
        'all_sector': all_sector_path.name if all_sector_path else None,
        'backtest_master': str(WORKFLOW / 'backtest_master.json'),
        'whale_tracker': str(WORKFLOW / 'whale_investor_tracker.json'),
        'news_tone': news_tone,
    },
    'crypto_setups_count': len(crypto_setups),
    'high_conviction_count': len(high),
    'swing_count': len(swing),
    'deep_oversold_count': len(deep_oversold) if deep_oversold else 0,
}
out_json.write_text(json.dumps(artifact, indent=2), encoding='utf-8')

print('WROTE', out_md)
print('WROTE', out_json)
print(f'Crypto setups: {len(crypto_setups)} | High conviction: {len(high)} | Swing: {len(swing)}')
print(f'Regime: {regime} | News tone: {news_tone}')
print('DONE')
