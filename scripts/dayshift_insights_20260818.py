#!/usr/bin/env python3
"""
Dayshift insights + broker routing + premarket filter over a fresh scan JSON.
Usage: python dayshift_insights_20260818.py <scan_json_path>
"""
import json, sys, datetime
from pathlib import Path
from datetime import timezone

if len(sys.argv) < 2:
    print('Usage: python dayshift_insights_20260818.py <scan_json_path>')
    sys.exit(1)
scan_path = Path(sys.argv[1])
if not scan_path.exists():
    print(f'Missing scan JSON: {scan_path}')
    sys.exit(1)
scan = json.loads(scan_path.read_text(encoding='utf-8'))
NOW = datetime.datetime.now(timezone.utc)
STAMP = NOW.strftime('%Y%m%dT%H%M%SZ')
OUT_DIR = Path('C:/Users/bravo-usr1/Desktop/scandata')
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / f'DAYSHIFT_2026-08-18_INSIGHTS_{STAMP}.json'
OUT_MD = OUT_DIR / f'DAYSHIFT_2026-08-18_INSIGHTS_{STAMP}.md'

qualified = scan.get('qualified_setups', [])
watchlist = scan.get('watchlist', [])
sector_summary = scan.get('sector_summary', {})

# Simple insight rules
USD_STRONG_SYMBOLS = {'JPM','V','MA','COST','HD','PG','AXP','SPGI','MCO','NEE'}
HIGH_BETA_SMALL = {'IOVA','EVH'}
CAD_CATALYST_SYMBOLS = {'USDCAD=X','EURCAD=X','AUDCAD=X','GBPCAD=X','NZDCAD=X'}

correlation_clusters = {
    'INDICES': {'^GSPC','^IXIC','^DJI','^RUT','ES=F','NQ=F','YM=F','RTY=F','SPY','QQQ','IWM','DIA','VOO','VTI'},
    'FOREX': {'EURUSD=X','GBPUSD=X','AUDUSD=X','NZDUSD=X','USDCAD=X','USDCHF=X','EURJPY=X','EURGBP=X','GBPJPY=X','AUDJPY=X'},
    'METALS': {'GC=F','SI=F','HG=F','PL=F','GLD','SLV'},
    'ENERGY': {'CL=F','NG=F','BRENT=F','XLE','XLI','XME','OIH'},
    'CRYPTO': {'BTC-USD','ETH-USD','SOL-USD','XRP-USD','AVAX-USD','LINK-USD','ADA-USD','DOGE-USD','DOT-USD','MATIC-USD','UNI-USD','AAVE-USD'},
    'BONDS': {'^TNX','^TYX','TLT','IEF','SHY','ZB=F','ZN=F','ZF=F'}
}

insights = {
    'scan_meta': scan.get('scan_metadata', {}),
    'market_regime': 'UNKNOWN',
    'usd_strength_bias': 'NEUTRAL',
    'insight_lines': [],
    'executable_tickets': [],
    'watchlist_tickets': [],
    'correlation_flags': [],
    'broker_routing': []
}

# Market regime heuristic from top setups / index trends
longs = [s for s in qualified if s.get('direction') == 'LONG']
shorts = [s for s in qualified if s.get('direction') == 'SHORT']
if len(longs) > len(shorts):
    insights['market_regime'] = 'RISK_ON'
elif len(shorts) > len(longs):
    insights['market_regime'] = 'RISK_OFF'
else:
    insights['market_regime'] = 'MIXED'

# USD strength heuristic
usd_long_fx = [s for s in qualified if s.get('asset_class') == 'Forex' and s.get('direction') == 'LONG' and str(s.get('symbol','')).startswith('USD')]
if len(usd_long_fx) >= 2:
    insights['usd_strength_bias'] = 'STRONG'
insights['insight_lines'].append(f"Market regime: {insights['market_regime']}")
insights['insight_lines'].append(f"USD strength bias: {insights['usd_strength_bias']}")
insights['insight_lines'].append(f"Qualified setups: {len(qualified)} | Watchlist: {len(watchlist)}")
insights['insight_lines'].append(f"Sectors with coverage: {len(sector_summary)}")

# Broker routing
broker_routes = {
    'Equities': 'ALPACA -> IBKR',
    'ETFs': 'ALPACA -> IBKR',
    'Indices': 'FTMO_LEFT -> CAPITAL_RIGHT -> IBKR',
    'Forex': 'FTMO_LEFT -> CAPITAL_RIGHT -> IBKR',
    'Precious_Metals': 'FTMO_LEFT -> CAPITAL_RIGHT -> IBKR',
    'Metals': 'FTMO_LEFT -> CAPITAL_RIGHT -> IBKR',
    'Energy': 'FTMO_LEFT -> CAPITAL_RIGHT -> IBKR',
    'Crypto': 'KRAKEN -> ALPACA -> FTMO_LEFT -> CAPITAL_RIGHT',
    'Prediction_Markets': 'KALSHI -> POLYMARKET',
    'Commodities': 'FTMO_LEFT -> CAPITAL_RIGHT -> IBKR',
    'Bonds': 'IBKR -> ALPACA'
}

def boost_for_symbol(sym):
    name = str(sym)
    boost = 0.0
    if name in USD_STRONG_SYMBOLS and insights['usd_strength_bias'] == 'STRONG':
        boost += 3.0
    if name in HIGH_BETA_SMALL and insights['usd_strength_bias'] == 'STRONG':
        boost -= 2.0
    if name in CAD_CATALYST_SYMBOLS:
        boost -= 0.5
    return boost

for s in qualified:
    sym = str(s.get('symbol', ''))
    asset = str(s.get('asset_class', ''))
    route = broker_routes.get(asset, 'UNKNOWN')
    s['broker_route'] = route
    s['conviction_insight'] = round(s.get('conviction', 0) + boost_for_symbol(sym), 1)
    insights['executable_tickets'].append({
        'symbol': sym,
        'asset_class': asset,
        'direction': s.get('direction'),
        'entry': s.get('entry'),
        'stop_loss': s.get('stop_loss'),
        'take_profit': s.get('take_profit'),
        'risk_reward': s.get('risk_reward'),
        'conviction': s.get('conviction'),
        'conviction_insight': s['conviction_insight'],
        'backtest': s.get('backtest'),
        'broker_route': route,
        'rsi': s.get('rsi'),
        'trend': s.get('trend')
    })

for s in watchlist:
    sym = str(s.get('symbol', ''))
    asset = str(s.get('asset_class', ''))
    route = broker_routes.get(asset, 'UNKNOWN')
    s['broker_route'] = route
    insights['watchlist_tickets'].append({
        'symbol': sym,
        'asset_class': asset,
        'direction': s.get('direction'),
        'entry': s.get('entry'),
        'stop_loss': s.get('stop_loss'),
        'take_profit': s.get('take_profit'),
        'risk_reward': s.get('risk_reward'),
        'conviction': s.get('conviction'),
        'backtest': s.get('backtest'),
        'broker_route': route,
        'qualified_reason': s.get('qualified_reason')
    })

# Correlation flags
cluster_counts = {name: {'LONG': 0, 'SHORT': 0} for name in correlation_clusters}
for ticket in insights['executable_tickets']:
    sym = str(ticket.get('symbol', ''))
    for name, members in correlation_clusters.items():
        if sym in members:
            cluster_counts[name][str(ticket.get('direction','')[:4]).upper()] += 1
for name, counts in cluster_counts.items():
    if counts['LONG'] > 1 or counts['SHORT'] > 1:
        insights['correlation_flags'].append({'cluster': name, 'long': counts['LONG'], 'short': counts['SHORT']})

# Insight lines from sector summary
for cls, stats in sorted(sector_summary.items()):
    if stats.get('qualified'):
        insights['insight_lines'].append(f"{cls}: {stats['qualified']} qualified / {stats['total']} scanned")

insights['executable_tickets'].sort(key=lambda x: (-x.get('conviction_insight', x.get('conviction', 0)), -x.get('backtest', {}).get('win_rate', 0)))
insights['watchlist_tickets'].sort(key=lambda x: (-x.get('conviction', 0), -x.get('backtest', {}).get('win_rate', 0)))

OUT_JSON.write_text(json.dumps(insights, indent=2, default=str))

md = []
md.append(f"# Dayshift All-Sector Scan Insights — {NOW.strftime('%Y-%m-%d %H:%M:%S %Z')}")
md.append("")
md.append("## Market Context")
for line in insights['insight_lines']:
    md.append(f"- {line}")
md.append("")
md.append("## Top 10 Tradeable Setups")
for i, t in enumerate(insights['executable_tickets'][:10], 1):
    md.append(f"{i}. {t['symbol']} {t['asset_class']} {t['direction']} conv={t['conviction']} insight={t['conviction_insight']} RSI={t['rsi']} RR={t['risk_reward']} WR={t['backtest']['win_rate']} PF={t['backtest']['profit_factor']} trades={t['backtest']['trades']} entry={t['entry']} SL={t['stop_loss']} TP={t['take_profit']} route={t['broker_route']}")
md.append("")
md.append("## Correlation Flags")
for flag in insights['correlation_flags']:
    md.append(f"- {flag['cluster']}: LONG={flag['long']} SHORT={flag['short']}")
md.append("")
md.append("## Watchlist")
for i, t in enumerate(insights['watchlist_tickets'][:20], 1):
    md.append(f"{i}. {t['symbol']} {t['asset_class']} {t['direction']} conv={t['conviction']} WR={t['backtest']['win_rate']} PF={t['backtest']['profit_factor']} reason={t['qualified_reason']} route={t['broker_route']}")
OUT_MD.write_text("\n".join(md))
print(f"[INSIGHTS] Saved {OUT_JSON}")
print(f"[INSIGHTS] Saved {OUT_MD}")
print(f"[INSIGHTS] Executable tickets: {len(insights['executable_tickets'])}")
print(f"[INSIGHTS] Watchlist tickets: {len(insights['watchlist_tickets'])}")
