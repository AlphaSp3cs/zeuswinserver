#!/usr/bin/env python3
"""
Force-refresh universe bars up to today for HTF + market_data.db.
Robust yfinance MultiIndex handling.
"""
import sys, sqlite3, time
from pathlib import Path
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd

FIRM = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm")
sys.path.insert(0, str(FIRM / "htf"))
import universe as U

HTF_DB = FIRM / "htf" / "htf_scan.db"
MKT_DB = FIRM / "loads" / "market_data.db"
UNIVERSE = U.UNIVERSE


def ensure_schema(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS htf_candles(
      symbol TEXT, sector TEXT, timeframe TEXT, ts TEXT,
      open REAL, high REAL, low REAL, close REAL, volume REAL,
      PRIMARY KEY(symbol,timeframe,ts));
    """)


def latest_bar_ts(con, symbol):
    cur = con.cursor()
    cur.execute("SELECT MAX(ts) FROM htf_candles WHERE symbol=?", (symbol,))
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def normalize_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        level0 = df.columns.get_level_values(0).unique().tolist()
        level1 = df.columns.get_level_values(1).unique().tolist()
        if symbol in level1:
            try:
                df = df.xs(symbol, level=1, axis=1)
                if isinstance(df, pd.Series):
                    df = df.to_frame()
            except Exception:
                pass
        elif len(level1) == 1:
            df = df.droplevel(1, axis=1)
        elif len(level0) == 1:
            df = df.droplevel(0, axis=1)
        else:
            try:
                df = df[symbol]
                if isinstance(df, pd.Series):
                    df = df.to_frame()
            except Exception:
                return pd.DataFrame()
    cols = {c: c.lower() for c in df.columns}
    df = df.rename(columns=cols)
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(set(df.columns)):
        return pd.DataFrame()
    df = df[["open", "high", "low", "close", "volume"]] if "volume" in df.columns else df[["open", "high", "low", "close"]]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.dropna(subset=["close"])
    return df


def fetch_yf_daily(symbol, period="30d", interval="1d"):
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
        return normalize_frame(df, symbol)
    except Exception:
        return pd.DataFrame()


def upsert_candles(con, symbol, sector, df: pd.DataFrame):
    rows = []
    for ts, r in df.iterrows():
        rows.append((
            symbol,
            sector,
            "D1",
            ts.strftime("%Y-%m-%d"),
            float(r["open"]) if pd.notna(r["open"]) else None,
            float(r["high"]) if pd.notna(r["high"]) else None,
            float(r["low"]) if pd.notna(r["low"]) else None,
            float(r["close"]) if pd.notna(r["close"]) else None,
            float(r["volume"]) if "volume" in r and pd.notna(r["volume"]) else 0.0,
        ))
    con.executemany(
        "INSERT OR REPLACE INTO htf_candles VALUES(?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f"Starting forced universe bar refresh: universe={len(UNIVERSE)}", flush=True)

    con = sqlite3.connect(str(HTF_DB))
    ensure_schema(con)
    updated = 0
    failed = []
    symbols = list(UNIVERSE.keys())

    for i, sym in enumerate(symbols, 1):
        sector = UNIVERSE[sym]
        last = latest_bar_ts(con, sym)
        df = fetch_yf_daily(sym, period="30d", interval="1d")
        if df.empty:
            failed.append(sym)
            continue
        if last is not None:
            try:
                last_dt = pd.Timestamp(last)
                df = df[df.index > last_dt]
            except Exception:
                pass
        if df.empty:
            continue
        try:
            updated += upsert_candles(con, sym, sector, df)
        except Exception as e:
            failed.append(f"{sym}:{e}")
        if i % 20 == 0 or i == len(symbols):
            print(f"  {i}/{len(symbols)} updated_rows={updated} failed={len(failed)}", flush=True)
        time.sleep(0.05)

    con.commit()
    con.close()

    mkt_updated = 0
    if MKT_DB.exists():
        try:
            con = sqlite3.connect(str(MKT_DB))
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('candles','instruments')")
            tables = {r[0] for r in cur.fetchall()}
            if {"candles", "instruments"} <= tables:
                for sym in symbols:
                    sector = UNIVERSE[sym]
                    df = fetch_yf_daily(sym, period="30d", interval="1d")
                    if df.empty:
                        continue
                    rows = []
                    for ts, r in df.iterrows():
                        rows.append((
                            sym,
                            sector,
                            "D1",
                            ts.strftime("%Y-%m-%d"),
                            float(r["open"]) if pd.notna(r["open"]) else None,
                            float(r["high"]) if pd.notna(r["high"]) else None,
                            float(r["low"]) if pd.notna(r["low"]) else None,
                            float(r["close"]) if pd.notna(r["close"]) else None,
                            float(r["volume"]) if "volume" in r and pd.notna(r["volume"]) else 0.0,
                        ))
                    try:
                        cur.executemany(
                            "INSERT OR REPLACE INTO candles(symbol,market,timeframe,ts_open,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?,?,?)",
                            rows,
                        )
                        mkt_updated += len(rows)
                    except Exception:
                        pass
                con.commit()
            con.close()
        except Exception as e:
            print("market_data.db backfill skipped:", e)

    finished = datetime.now(timezone.utc).isoformat()
    print("\n=== FORCED UNIVERSE BAR REFRESH SUMMARY ===")
    print(f"HTF DB rows upserted : {updated}")
    print(f"Market data DB rows  : {mkt_updated}")
    print(f"Failed symbols       : {len(failed)}")
    if failed:
        print("  " + ", ".join(str(x) for x in failed[:20]))
    print(f"Started              : {started}")
    print(f"Finished             : {finished}")


if __name__ == "__main__":
    main()
