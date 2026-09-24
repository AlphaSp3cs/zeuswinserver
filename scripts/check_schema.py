import sqlite3
p = r'C:/Users/bravo-usr1/.hermes/data/thinktank.db'
con = sqlite3.connect(p)
tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)
for t in tables:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({t[0]})").fetchall()]
    print(t[0], cols)
con.close()
