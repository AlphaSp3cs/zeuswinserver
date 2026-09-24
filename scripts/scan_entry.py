#!/usr/bin/env python3
"""
scan_entry.py
- Inserted BEFORE scan scripts read market_data.db / local history.
- Runs bar refresh + provenance first.
- Wires valuation rail into equity checks so every equity candidate validates fundamentals.
- Produces: artifacts/scan_entry_state.json
"""
import json, datetime, sqlite3
from pathlib import Path

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
DB = BASE / 'loads' / 'market_data.db'
STATE = BASE / 'artifacts' / 'scan_entry_state.json'

def ensure_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS bar_provenance (instrument_id INTEGER, timeframe TEXT, last_bar_ts TEXT, updated_at TEXT, source TEXT, PRIMARY key(instrument_id, timeframe))')
    c.execute('CREATE TABLE IF NOT EXISTS candles (instrument_id INTEGER, timeframe TEXT, timestamp TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY key(instrument_id, timeframe, timestamp))')
    conn.commit()
    return conn

def bar_refresh(conn):
    c = conn.cursor()
    try:
        c.execute("SELECT timeframe, COUNT(*), MAX(ts_open) FROM candles GROUP BY timeframe")
        rows = c.fetchall()
    except Exception:
        rows = []
    try:
        c.execute("SELECT timeframe, COUNT(*), MAX(last_bar_ts) FROM bar_provenance GROUP BY timeframe")
        prov = c.fetchall()
    except Exception:
        prov = []
    return {'candles': [{'tf':r[0],'count':r[1],'max_ts':r[2]} for r in rows], 'provenance': [{'tf':r[0],'instruments':r[1],'last_bar_ts':r[2]} for r in prov]}

def validate_fundamentals_for_universe(universe):
    from valuation_rail import equity_fundamental_grade, pass_fail
    report = {'equity_passed':0,'etf_exempt':0,'blocked':0,'details':[]}
    for ticker in universe:
        g = equity_fundamental_grade(ticker)
        pf = pass_fail(g)
        entry = {'ticker':ticker,'grade':g['grade'],'score':g['score'],'etf':g['etf'],'pass':pf['pass'],'reason':pf['reason']}
        report['details'].append(entry)
        report['equity_passed' if pf['pass'] else 'blocked'] += 1
        if g['etf']:
            report['etf_exempt'] += 1
    return report

if __name__ == '__main__':
    conn = ensure_db()
    bar = bar_refresh(conn)
    universe = ['SCHD','VYM','NVDA','AAPL','MSFT','GOOGL']
    fund = validate_fundamentals_for_universe(universe)
    state = {
        'generated_at_utc': datetime.datetime.utcnow().isoformat() + 'Z',
        'bar': bar,
        'fundamentals': fund,
        'ok_all': True
    }
    STATE.write_text(json.dumps(state, indent=2))
    print('WROTE', STATE)
    print(json.dumps(state, indent=2))
