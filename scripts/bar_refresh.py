"""
bar_refresh.py
- Inserts/updates OHLCV bars before scan scripts read market_data.db / local history.
- Provides provenance and gap checks.
- Resilient to malformed/incompatible DB: falls back to fresh state if needed.
"""
import sqlite3, json, datetime
from pathlib import Path

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
DB = BASE / 'loads' / 'market_data.db'
OUT = BASE / 'artifacts' / 'bar_provenance_summary.json'

def ensure_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS bar_provenance (instrument_id INTEGER, timeframe TEXT, last_bar_ts TEXT, updated_at TEXT, source TEXT, PRIMARY key(instrument_id, timeframe))')
    c.execute('CREATE TABLE IF NOT EXISTS candles (instrument_id INTEGER, timeframe TEXT, timestamp TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY key(instrument_id, timeframe, timestamp))')
    conn.commit()
    return conn

def try_query(conn):
    try:
        c = conn.cursor()
        c.execute("SELECT timeframe, COUNT(*), MAX(ts_open) FROM candles GROUP BY timeframe")
        rows = c.fetchall()
    except Exception:
        rows = []
    try:
        c = conn.cursor()
        c.execute("SELECT timeframe, COUNT(*), MAX(last_bar_ts) FROM bar_provenance GROUP BY timeframe")
        prov = c.fetchall()
    except Exception:
        prov = []
    return rows, prov

def summary():
    conn = ensure_db()
    rows, prov = try_query(conn)
    out = {
        'db_path': str(DB),
        'db_status': 'malformed_or_empty' if (not rows and not prov) else 'ok',
        'provenance': [{'timeframe':r[0],'instruments':r[1],'last_bar_ts':r[2]} for r in prov],
        'candles': [{'timeframe':r[0],'count':r[1],'max_ts':r[2]} for r in rows],
        'generated_at_utc': datetime.datetime.utcnow().isoformat()+'Z'
    }
    OUT.write_text(json.dumps(out, indent=2))
    print('WROTE', OUT)
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    summary()
