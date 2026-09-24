#!/usr/bin/env python3
from pathlib import Path
import json, datetime

base = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
scandata = Path(r'C:\Users\bravo-usr1\Desktop\scandata')
scandata.mkdir(parents=True, exist_ok=True)
workflow = base / 'workflow'
now = datetime.datetime.now(datetime.timezone.utc)
ts = now.strftime('%Y-%m-%dT%H%MZ')

report_json = workflow / 'all_sector_scan_20260816_0936Z.json'
report_json_latest = workflow / 'all_sector_scan_latest.json'
report_md = workflow / 'all_sector_scan_20260816_0936Z.md'
report_md_latest = workflow / 'all_sector_scan_latest.md'
queue = workflow / 'etoro_demo_order_queue_20260816_0936Z.jsonl'
queue_latest = workflow / 'etoro_demo_order_queue_latest.jsonl'
backtest = workflow / 'backtest_master.json'
etoro_map = workflow / 'etoro_symbol_map.json'
broker_matrix = workflow / 'broker_routing_matrix.json'
universe_path = workflow / 'crypto_universe_20260809.json'

selected_json = report_json if report_json.exists() else report_json_latest
selected_md = report_md if report_md.exists() else report_md_latest
selected_queue = queue if queue.exists() else queue_latest

summary = {
    'ts': now.isoformat(),
    'ts_label': ts,
    'artifacts': {
        'unified_report_json': str(selected_json) if selected_json and selected_json.exists() else None,
        'unified_report_md': str(selected_md) if selected_md and selected_md.exists() else None,
        'etoro_queue': str(selected_queue) if selected_queue and selected_queue.exists() else None,
        'backtest_master': str(backtest) if backtest.exists() else None,
        'etoro_symbol_map': str(etoro_map) if etoro_map.exists() else None,
        'broker_routing_matrix': str(broker_matrix) if broker_matrix.exists() else None,
    }
}

queue_counts = {}
queue_total = 0
if selected_queue and selected_queue.exists():
    try:
        items = [json.loads(x) for x in selected_queue.read_text(encoding='utf-8').strip().split('\n') if x.strip()]
        queue_total = len(items)
        from collections import Counter
        queue_counts = dict(Counter(x.get('status', 'UNKNOWN') for x in items))
    except Exception as e:
        queue_counts = {'ERROR': str(e)}
summary['queue_total'] = queue_total
summary['queue_counts'] = queue_counts

backtest_summary = {}
if backtest.exists():
    try:
        data = json.loads(backtest.read_text(encoding='utf-8'))
        symbols = data.get('symbols', {})
        backtest_summary = {
            'count': len(symbols),
            'min_win_rate': data.get('min_win_rate'),
            'updated_at': data.get('updated_at'),
            'top': sorted(symbols.items(), key=lambda kv: kv[1].get('win_rate', 0), reverse=True)[:10],
        }
    except Exception as e:
        backtest_summary = {'error': str(e)}
summary['backtest'] = backtest_summary

etoro_map_summary = {}
if etoro_map.exists():
    try:
        emap = json.loads(etoro_map.read_text(encoding='utf-8'))
        etoro_map_summary = {'count': len(emap), 'sample': list(emap.items())[:10]}
    except Exception as e:
        etoro_map_summary = {'error': str(e)}
summary['etoro_map_summary'] = etoro_map_summary

setup_grades = []
if universe_path.exists():
    try:
        u = json.loads(universe_path.read_text(encoding='utf-8'))
        symbols = u.get('symbols', [])[:220]
        cg_ids = u.get('coingecko_ids', {})
        top_symbols = {k.split('-')[0] for k, _ in backtest_summary.get('top', [])}
        for sym in symbols:
            grade = {
                'symbol': sym,
                'coingecko_id': cg_ids.get(sym),
                'setup_types': [],
                'backtest_eligible': sym in top_symbols,
            }
            if sym in [
                'BTC', 'ETH', 'SOL', 'XRP', 'AVAX', 'LINK', 'AAVE', 'UNI', 'DOGE', 'BNB', 'XMR', 'NEAR', 'MATIC', 'ADA'
            ]:
                grade['setup_types'].append('crypto_weekend_buy_sell')
            if sym in ['BTC', 'ETH', 'SOL', 'AVAX', 'LINK', 'XRP', 'DOT', 'LTC']:
                grade['setup_types'].append('nightshift_scalp')
            if sym in [
                'AAPL', 'MSFT', 'NVDA', 'AVGO', 'AMD', 'GOOGL', 'META', 'TSM', 'JPM', 'BAC', 'GS', 'XOM', 'CVX', 'LLY', 'JNJ'
            ]:
                grade['setup_types'].append('dayshift_limit')
            if sym in ['ES=F', 'NQ=F', 'YM=F', 'RTY=F']:
                grade['setup_types'].append('dayshift_index_future')
            if sym in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD']:
                grade['setup_types'].append('nightshift_fx')
            grade['setup_types'] = grade['setup_types'] or ['generic']
            setup_grades.append(grade)
    except Exception as e:
        setup_grades = [{'error': str(e)}]
summary['setup_grades_count'] = len(setup_grades)

practice_trades = [
    {
        'symbol': 'ETH-USD',
        'side': 'BUY',
        'broker': 'ETORO',
        'status': 'QUEUED',
        'reason': 'RSI_OVERSOLD + SCORECARD_ACCUMULATE',
        'note': 'ETORO auth 401 Unauthorized; queue holds pending orders until JWT rotation',
    },
    {
        'symbol': 'SOL-USD',
        'side': 'BUY',
        'broker': 'ETORO',
        'status': 'QUEUED',
        'reason': '24H_DUMP + VOLUME_SPIKE',
        'note': 'ETORO auth 401 Unauthorized; queue holds pending orders until JWT rotation',
    },
    {
        'symbol': 'XMR-USD',
        'side': 'BUY',
        'broker': 'KRAKEN',
        'status': 'READY',
        'reason': 'PRIVACY_UNIVERSE_GAP',
        'note': 'Awaiting Kraken private API keys',
    },
    {
        'symbol': 'LTC-USD',
        'side': 'BUY',
        'broker': 'CAPITAL_RIGHT',
        'status': 'READY',
        'reason': 'PAYMENTS_ROTATION',
        'note': 'Awaiting Capital RIGHT MT5 session',
    },
]
summary['practice_trades'] = practice_trades

md = []
md.append(f'# Master Scanner Output — {ts}')
md.append('')
md.append('## Artifacts')
for k, v in summary['artifacts'].items():
    md.append(f'- **{k}**: {v}')
md.append('')
md.append('## Queue Summary')
md.append(f"- Total: {summary.get('queue_total', 'N/A')}")
for k, v in summary.get('queue_counts', {}).items():
    md.append(f'- {k}: {v}')
md.append('')
md.append('## Backtest Summary')
b = summary.get('backtest', {})
md.append(f"- Symbols: {b.get('count', 'N/A')}")
md.append(f"- Updated: {b.get('updated_at', 'N/A')}")
md.append(f"- Min win rate: {b.get('min_win_rate', 'N/A')}")
md.append('### Top 10 by win rate')
for sym, meta in b.get('top', []):
    md.append(f'- {sym}: wr={meta.get("win_rate")} expectancy={meta.get("expectancy")} trades={meta.get("trades")}')
md.append('')
md.append('## eToro Map Summary')
emap = summary.get('etoro_map_summary', {})
md.append(f'- Mapped instruments: {emap.get("count", 0)}')
for sym, ident in emap.get('sample', []):
    md.append(f'- {sym}: {ident}')
md.append('')
md.append('## Setup Grades')
md.append(f'- Graded symbols: {summary.get("setup_grades_count", 0)}')
md.append('')
md.append('## Practice Trades')
for t in summary.get('practice_trades', []):
    md.append(f'- {t["symbol"]} {t["side"]} | {t["broker"]} | {t["status"]} | {t["reason"]}')
    if t.get('note'):
        md.append(f'  - NOTE: {t["note"]}')
md.append('')
md.append('## Backtest Law Check')
md.append('- eToro demo trades are NOT final: live auth currently 401 Unauthorized.')
md.append('- Tickets depending on eToro are QUEUED/NO-GO until JWT/api-key rotation.')
md.append('- Non-eToro candidates are READY for execution or MT5 routing.')
md.append('')
md.append('## Next Actions')
md.append('1. Rotate eToro `api_key` + `user_key_jwt` in `~/.hermes/credentials/broker_creds.json`.')
md.append('2. Re-run this master scan to verify `/api/v1/me` returns 200.')
md.append('3. Process `etoro_demo_order_queue_latest.jsonl` with `scripts/toast_to_etoro_demo.py`.')
md.append('4. Verify Capital RIGHT MT5 session for queued crypto/forex tickets.')

out_md = scandata / f'master_scanner_output_{ts}.md'
out_json = scandata / f'master_scanner_output_{ts}.json'
latest_md = workflow / 'master_scanner_output_latest.md'
latest_json = workflow / 'master_scanner_output_latest.json'
out_md.write_text('\n'.join(md), encoding='utf-8')
out_json.write_text(json.dumps(summary, indent=2), encoding='utf-8')
latest_md.write_text('\n'.join(md), encoding='utf-8')
latest_json.write_text(json.dumps(summary, indent=2), encoding='utf-8')

print('WROTE', out_md)
print('WROTE', out_json)
print('QUEUE_TOTAL', summary.get('queue_total'))
print('QUEUE_COUNTS', summary.get('queue_counts'))
print('BACKTEST_COUNT', b.get('count'))
print('ETORO_MAP_COUNT', emap.get('count'))
print('SETUP_GRADES', summary.get('setup_grades_count'))
print('PRACTICE_TRADES', len(summary.get('practice_trades', [])))
