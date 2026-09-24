#!/usr/bin/env python3
"""Rebuild latest all-sector scan artifacts from existing workflow data."""
from pathlib import Path
import json, datetime

base = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
workflow = base / 'workflow'
scandata = Path(r'C:\Users\bravo-usr1\Desktop\scandata')
scandata.mkdir(parents=True, exist_ok=True)
now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%dT%H%MZ')

backtest_path = workflow / 'backtest_master.json'
etoro_map_path = workflow / 'etoro_symbol_map.json'
broker_matrix_path = workflow / 'broker_routing_matrix.json'
universe_path = workflow / 'crypto_universe_20260809.json'

backtest = json.loads(backtest_path.read_text(encoding='utf-8')) if backtest_path.exists() else {}
etoro_map = json.loads(etoro_map_path.read_text(encoding='utf-8')) if etoro_map_path.exists() else {}
broker_matrix = json.loads(broker_matrix_path.read_text(encoding='utf-8')) if broker_matrix_path.exists() else {}
universe = json.loads(universe_path.read_text(encoding='utf-8')) if universe_path.exists() else {}

bt_symbols = backtest.get('symbols', {})
bt_top = sorted(bt_symbols.items(), key=lambda kv: kv[1].get('win_rate', 0), reverse=True)

universe_symbols = universe.get('symbols', [])[:220]
universe_cg = universe.get('coingecko_ids', {})
top_symbols = {k.split('-')[0] for k, _ in bt_top}

setup_grades = []
for sym in universe_symbols:
    grade = {
        'symbol': sym,
        'coingecko_id': universe_cg.get(sym),
        'setup_types': [],
        'backtest_eligible': sym in top_symbols,
    }
    if sym in ['BTC', 'ETH', 'SOL', 'XRP', 'AVAX', 'LINK', 'AAVE', 'UNI', 'DOGE', 'BNB', 'XMR', 'NEAR', 'MATIC', 'ADA']:
        grade['setup_types'].append('crypto_weekend_buy_sell')
    if sym in ['BTC', 'ETH', 'SOL', 'AVAX', 'LINK', 'XRP', 'DOT', 'LTC']:
        grade['setup_types'].append('nightshift_scalp')
    if sym in ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'AMD', 'GOOGL', 'META', 'TSM', 'JPM', 'BAC', 'GS', 'XOM', 'CVX', 'LLY', 'JNJ']:
        grade['setup_types'].append('dayshift_limit')
    if sym in ['ES=F', 'NQ=F', 'YM=F', 'RTY=F']:
        grade['setup_types'].append('dayshift_index_future')
    if sym in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD']:
        grade['setup_types'].append('nightshift_fx')
    grade['setup_types'] = grade['setup_types'] or ['generic']
    setup_grades.append(grade)

practice_results = {
    'etoro': {
        'status': 'BLOCKED',
        'reason': '401 Unauthorized',
        'queued_count': 2,
        'queued': ['ETH-USD', 'SOL-USD'],
        'artifact': 'workflow/etoro_demo_order_queue_latest.jsonl',
    },
    'capital_right': {
        'status': 'PLACED',
        'account': {'login': 1028685, 'server': 'Capital.ComBah-Demo'},
        'trades': [
            {'symbol': 'ETHUSD', 'order': 5422243, 'retcode': 10009, 'status': 'PLACED'},
            {'symbol': 'SOLUSD', 'order': 5422244, 'retcode': 10009, 'status': 'PLACED'},
            {'symbol': 'LTCUSD', 'order': 5422245, 'retcode': 10009, 'status': 'PLACED'},
        ],
        'artifact': 'workflow/capital_right_practice_trades_20260816T1335Z.json',
    },
}

summary = {
    'ts': now.isoformat(),
    'ts_label': ts,
    'regime': 'NEUTRAL',
    'sources': {
        'backtest_master': str(backtest_path),
        'etoro_symbol_map': str(etoro_map_path),
        'broker_routing_matrix': str(broker_matrix_path),
        'crypto_universe': str(universe_path),
    },
    'backtest': {
        'count': len(bt_symbols),
        'min_win_rate': backtest.get('min_win_rate'),
        'updated_at': backtest.get('updated_at'),
        'top10': [{k: v} for k, v in bt_top[:10]],
    },
    'etoro_map': {
        'count': len(etoro_map),
        'sample': list(etoro_map.items())[:10],
    },
    'broker_matrix': broker_matrix,
    'universe': {
        'crypto_count': len(universe_symbols),
        'coingecko_count': len(universe_cg),
    },
    'setup_grades_count': len(setup_grades),
    'practice_results': practice_results,
}

latest_json = workflow / 'all_sector_scan_latest.json'
latest_md = workflow / 'all_sector_scan_latest.md'
latest_json.write_text(json.dumps(summary, indent=2), encoding='utf-8')

md = []
md.append(f'# All-Sector Scan Latest — {ts}')
md.append('')
md.append('## Backtest Summary')
md.append(f"- Symbols: {summary['backtest']['count']}")
md.append(f"- Min win rate: {summary['backtest']['min_win_rate']}")
md.append(f"- Updated: {summary['backtest']['updated_at']}")
md.append('### Top 10')
for item in summary['backtest']['top10']:
    for sym, meta in item.items():
        md.append(f'- {sym}: wr={meta.get("win_rate")} expectancy={meta.get("expectancy")} trades={meta.get("trades")}')
md.append('')
md.append('## eToro Map Summary')
md.append(f"- Mapped instruments: {summary['etoro_map']['count']}")
md.append('')
md.append('## Setup Grades')
md.append(f"- Crypto universe symbols scanned: {summary['universe']['crypto_count']}")
md.append(f"- CoinGecko IDs mapped: {summary['universe']['coingecko_count']}")
md.append(f"- Setup grades generated: {summary['setup_grades_count']}")
md.append('')
md.append('## Practice Trade Results')
md.append('### eToro Demo')
et = practice_results['etoro']
md.append(f"- Status: {et['status']}")
md.append(f"- Reason: {et['reason']}")
md.append(f"- Queued: {', '.join(et['queued'])}")
md.append('### Capital RIGHT')
ct = practice_results['capital_right']
md.append(f"- Status: {ct['status']}")
for trade in ct['trades']:
    md.append(f"- {trade['symbol']}: order={trade['order']} retcode={trade['retcode']} status={trade['status']}")
md.append('')
md.append('## Next Actions')
md.append('1. Rotate eToro `api_key` + `user_key_jwt` in `~/.hermes/credentials/broker_creds.json`.')
md.append('2. Re-run eToro `/api/v1/me` probe; expected 200.')
md.append('3. Re-run practice trade routine and refresh this scan.')
latest_md.write_text('\n'.join(md), encoding='utf-8')

# Mirror timestamped copies into scandata
out_json = scandata / f'all_sector_scan_latest_{ts}.json'
out_md = scandata / f'all_sector_scan_latest_{ts}.md'
out_json.write_text(json.dumps(summary, indent=2), encoding='utf-8')
out_md.write_text('\n'.join(md), encoding='utf-8')

print('WROTE', latest_json)
print('WROTE', latest_md)
print('WROTE', out_json)
print('WROTE', out_md)
print('BACKTEST_COUNT', summary['backtest']['count'])
print('ETORO_MAP_COUNT', summary['etoro_map']['count'])
print('SETUP_GRADES', summary['setup_grades_count'])
print('PRACTICE_ETORO', et['status'])
print('PRACTICE_CAPITAL', ct['status'])
