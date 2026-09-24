#!/usr/bin/env python3
"""
aggregate_and_backtest_trades.py
- Scans for trade result files from light_exec_*.json artifacts (contains FTMO, Capital, eToro results)
- Builds a registry of trades per broker in ~/AppData/Local/hermes/broker_trades/
- Runs a simple backtest using yfinance historical data to compute PnL
- Outputs performance scores that can be used to weight symbols in the next nightshift scan
"""
import json, os, sys, glob, datetime as dt, traceback
from pathlib import Path
import pandas as pd
import yfinance as yf

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
SCANDATA = BASE / 'scandata'
WORKFLOW = BASE / 'workflow'
ARTIFACTS = BASE / 'artifacts'
REGISTRY_DIR = Path(os.path.expanduser('~/AppData/Local/hermes/broker_trades'))
REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

# Helper to normalize symbol for yfinance
def yf_symbol(sym):
    sym = sym.upper()
    # Convert common formats
    if sym.endswith('=X'):
        sym = sym.replace('=X', '')  # e.g., EURUSD
    if '/' in sym:
        # Crypto like BTC-USD -> yfinance uses BTC-USD
        sym = sym.replace('/', '-')
    # For now, return as is; yfinance can handle many formats
    return sym

def fetch_historical_price(sym, start_dt, end_dt=None, interval='5m'):
    """Fetch historical data from yfinance for the symbol between start_dt and end_dt."""
    try:
        ticker = yf.Ticker(yf_symbol(sym))
        if end_dt is None:
            end_dt = start_dt + dt.timedelta(hours=4)
        data = ticker.history(start=start_dt, end=end_dt, interval=interval)
        if data.empty:
            return None
        return data
    except Exception as e:
        print(f"  yfinance error for {sym}: {e}")
        return None

def compute_trade_pnl(trade):
    """
    Given a trade dict with:
      symbol, side ('buy'/'sell'), entry, sl, tp, timestamp (datetime), broker
    Determine if TP or SL hit first using historical 5m bars after timestamp.
    Returns dict with pnl, outcome, etc.
    """
    if 'timestamp' not in trade or trade['timestamp'] is None:
        # Cannot backtest without timestamp
        return None
    sym = trade['symbol']
    side = trade['side']
    entry = float(trade['entry'])
    sl = float(trade['sl'])
    tp = float(trade['tp'])
    broker = trade.get('broker', 'unknown')
    start_dt = trade['timestamp']
    # Look ahead 4 hours
    data = fetch_historical_price(sym, start_dt, start_dt + dt.timedelta(hours=4), interval='5m')
    if data is None or data.empty:
        return None
    # Determine outcome
    hit_sl = False
    hit_tp = False
    sl_time = None
    tp_time = None
    for idx, row in data.iterrows():
        high = float(row['High'])
        low = float(row['Low'])
        if side == 'buy':
            if low <= sl:
                hit_sl = True
                sl_time = idx
                break
            if high >= tp:
                hit_tp = True
                tp_time = idx
                break
        else:  # sell
            if high >= sl:
                hit_sl = True
                sl_time = idx
                break
            if low <= tp:
                hit_tp = True
                tp_time = idx
                break
    if hit_sl and hit_tp:
        # whichever came first
        if sl_time <= tp_time:
            hit_tp = False
        else:
            hit_sl = False
    pnl = 0.0
    outcome = 'unknown'
    if hit_sl:
        pnl = (sl - entry) if side == 'buy' else (entry - sl)
        outcome = 'sl'
    elif hit_tp:
        pnl = (tp - entry) if side == 'buy' else (entry - tp)
        outcome = 'tp'
    else:
        # Neither hit, use close of last bar
        last_close = float(data.iloc[-1]['Close'])
        if side == 'buy':
            pnl = last_close - entry
        else:
            pnl = entry - last_close
        outcome = 'close'
    # Convert to pips or points? We'll keep in price units.
    return {
        'symbol': sym,
        'side': side,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'timestamp': start_dt.isoformat(),
        'broker': broker,
        'pnl': pnl,
        'outcome': outcome,
        'sl_time': sl_time.isoformat() if sl_time else None,
        'tp_time': tp_time.isoformat() if tp_time else None,
        'bars_checked': len(data)
    }

def extract_trades_from_artifacts():
    trades = []
    # Look for light_exec_*.json in artifacts
    for f in glob.glob(str(ARTIFACTS / 'light_exec_*.json')):
        try:
            data = json.loads(Path(f).read_text())
            timestamp_str = data.get('ts')
            if not timestamp_str:
                continue
            # Parse timestamp
            try:
                timestamp = dt.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                # If parsing fails, skip this file
                continue
            # Extract results array
            results = data.get('results', [])
            for r in results:
                symbol = r.get('symbol')
                side = r.get('side')
                price = r.get('price')  # entry price
                sl = r.get('sl')
                tp = r.get('tp')
                status = r.get('status')
                broker = r.get('broker')
                # Only consider executed trades (status == 'executed')
                if status == 'executed' and symbol and side and price is not None and sl is not None and tp is not None:
                    trades.append({
                        'broker': broker,
                        'symbol': symbol,
                        'side': side,
                        'entry': float(price),
                        'sl': float(sl),
                        'tp': float(tp),
                        'timestamp': timestamp,
                        'raw_result': r  # keep for debugging
                    })
        except Exception as e:
            print(f"Error processing {f}: {e}")
            traceback.print_exc()
    return trades

def load_etoro_trades_from_scandata():
    """Load eToro trades from practice_trades_etoro_demo_*.json and executed_light_setups_*.json"""
    trades = []
    # Practice trades (demo)
    for f in glob.glob(str(SCANDATA / 'practice_trades_etoro_demo_*.json')):
        try:
            data = json.loads(Path(f).read_text())
            for r in data.get('results', []):
                if r.get('status') == 'placed':
                    # We don't have entry price from practice trades, skip
                    pass
        except Exception as e:
            print(f"Error reading practice eToro file {f}: {e}")
    # Executed light setups (these have entry, SL, TP)
    for f in glob.glob(str(SCANDATA / 'executed_light_setups_*.json')):
        try:
            data = json.loads(Path(f).read_text())
            for r in data:
                if r.get('broker') == 'etoro' and r.get('status') == 'placed':
                    trades.append({
                        'broker': 'etoro',
                        'symbol': r['symbol'],
                        'side': r['side'],
                        'entry': r['entry'],
                        'sl': r['sl'],
                        'tp': r['tp'],
                        'timestamp': None  # we don't have timestamp in these files
                    })
        except Exception as e:
            print(f"Error reading executed light setups {f}: {e}")
    return trades

def main():
    print("Starting trade aggregation and backtest...")
    all_trades = []
    # Load from artifact files (FTMO, Capital)
    artifact_trades = extract_trades_from_artifacts()
    print(f"Found {len(artifact_trades)} executed trades from artifact files")
    all_trades.extend(artifact_trades)
    # Load from eToro files
    etoro_trades = load_etoro_trades_from_scandata()
    print(f"Found {len(etoro_trades)} eToro trades from scan data")
    all_trades.extend(etoro_trades)
    print(f"Total trades collected: {len(all_trades)}")
    
    # Now backtest each trade (only those with timestamp)
    backtestable_trades = [t for t in all_trades if t.get('timestamp') is not None]
    print(f"{len(backtestable_trades)} trades have timestamps for backtesting")
    results = []
    for t in backtestable_trades:
        pnl_info = compute_trade_pnl(t)
        if pnl_info:
            results.append(pnl_info)
            print(f"  Backtested {t['symbol']} {t['side']}: PnL={pnl_info['pnl']:.2f} ({pnl_info['outcome']})")
        else:
            print(f"  Skipping backtest for {t['symbol']} {t['side']} (no data)")
    print(f"Backtested {len(results)} trades.")
    
    # Aggregate by broker and symbol
    broker_stats = {}
    symbol_stats = {}
    for r in results:
        broker = r.get('broker', 'unknown')
        sym = r['symbol']
        pnl = r['pnl']
        outcome = r['outcome']
        broker_stats.setdefault(broker, {'pnl': 0.0, 'wins': 0, 'losses': 0, 'total': 0})
        broker_stats[broker]['pnl'] += pnl
        broker_stats[broker]['total'] += 1
        if pnl > 0:
            broker_stats[broker]['wins'] += 1
        else:
            broker_stats[broker]['losses'] += 1
        symbol_stats.setdefault(sym, {'pnl': 0.0, 'wins': 0, 'losses': 0, 'total': 0})
        symbol_stats[sym]['pnl'] += pnl
        symbol_stats[sym]['total'] += 1
        if pnl > 0:
            symbol_stats[sym]['wins'] += 1
        else:
            symbol_stats[sym]['losses'] += 1
    # Write registry per broker
    for broker in broker_stats:
        broker_file = REGISTRY_DIR / f'{broker}_trades.json'
        # We need to store the actual trades for this broker (only backtested ones for now)
        broker_trades = [r for r in results if r.get('broker') == broker]
        broker_file.write_text(json.dumps(broker_trades, indent=2, default=str))
        print(f"Wrote {len(broker_trades)} backtested trades for {broker} to {broker_file}")
    # Write summary
    summary = {
        'ts': dt.datetime.now(dt.timezone.utc).isoformat(),
        'broker_stats': {k: {**v, 'win_rate': v['wins']/v['total'] if v['total']>0 else 0} for k, v in broker_stats.items()},
        'symbol_stats': {k: {**v, 'win_rate': v['wins']/v['total'] if v['total']>0 else 0} for k, v in symbol_stats.items()},
        'trades_backtested': len(results),
        'trades_total_with_timestamp': len(backtestable_trades),
        'trades_total': len(all_trades)
    }
    summary_file = REGISTRY_DIR / 'backtest_summary.json'
    summary_file.write_text(json.dumps(summary, indent=2, default=str))
    print(f"Wrote backtest summary to {summary_file}")
    # Output suggested weights for next scan: higher weight for symbols with higher win rate and profit factor
    weights = {}
    for sym, stat in symbol_stats.items():
        if stat['total'] >= 1:  # at least 1 trade
            win_rate = stat['wins'] / stat['total']
            avg_pnl = stat['pnl'] / stat['total']
            # We want to reward symbols with high win rate and positive average PnL.
            # If avg_pnl is negative, we still might want to trade if win rate is high? 
            # Let's use a score that is win_rate * (1 + avg_pnl_normalized) but we need to normalize avg_pnl.
            # Since we don't have a baseline, we can use a simple heuristic: score = win_rate * max(0, avg_pnl) + (1 - win_rate) * 0
            # But that gives zero weight to negative avg_pnl. Instead, let's use win_rate as the primary factor, and adjust by avg_pnl sign.
            # We'll compute a score that is win_rate if avg_pnl > 0, else win_rate * 0.5 (penalize losing avg PnL).
            if avg_pnl > 0:
                score = win_rate
            else:
                score = win_rate * 0.5
            weights[sym] = score
    # Normalize weights to sum to 1 (or max 1)
    if weights:
        max_score = max(weights.values()) if weights else 1
        if max_score > 0:
            weights = {k: v/max_score for k, v in weights.items()}
    weight_file = REGISTRY_DIR / 'symbol_weights.json'
    weight_file.write_text(json.dumps(weights, indent=2, default=str))
    print(f"Wrote symbol weights to {weight_file}")
    # Print summary
    print("\n=== BACKTEST SUMMARY ===")
    for broker, stat in broker_stats.items():
        win_rate = stat['wins']/stat['total'] if stat['total']>0 else 0
        print(f"{broker}: PnL={stat['pnl']:.2f}, Wins={stat['wins']}/{stat['total']} ({win_rate:.1%})")
    print("\n=== SYMBOL STATS ===")
    for sym, stat in symbol_stats.items():
        win_rate = stat['wins']/stat['total'] if stat['total']>0 else 0
        avg_pnl = stat['pnl']/stat['total'] if stat['total']>0 else 0
        print(f"{sym}: PnL={stat['pnl']:.2f}, Wins={stat['wins']}/{stat['total']} ({win_rate:.1%}), Avg PnL={avg_pnl:.2f}")
        if sym in weights:
            print(f"  Weight: {weights[sym]:.3f}")
    print("=== DONE ===")

if __name__ == '__main__':
    main()