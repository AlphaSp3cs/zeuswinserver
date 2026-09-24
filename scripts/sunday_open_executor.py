#!/usr/bin/env python3
"""
Sunday Open Trade Executor - 2026-07-26
Executes queued trades from crypto_trade_plan.json after market open validation.

Rules:
- FTMO/Capital MT5: FOK only, omit type_filling
- Alpaca: No brackets, SL/TP separate legs
- IBKR: retry with clientId+1 on timeout
- Weekend guard: queue to pending_trades_<DATE>.json if closed
"""

import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path

PLAN_PATH = Path(r'C:\Users\bravo-usr1\crypto_trade_plan.json')
STATUS_PATH = Path(r'C:\Users\bravo-usr1\crypto_execution_status.json')
PENDING_DIR = Path(r'C:\Users\bravo-usr1\.hermes\data')
PENDING_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_json(path):
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def is_market_open(symbol, broker):
    """Basic market hours check. Crypto: 24/7. Indices: NYSE 9:30-16:00 ET."""
    from pytz import timezone
    et = timezone('America/New_York')
    now_et = datetime.now(et)
    
    # Crypto always open
    crypto_assets = {'BTCUSD', 'ETHUSD', 'SOLUSD', 'ADAUSD', 'DOGEUSD', 
                     'XRPUSD', 'LINKUSD', 'AVAXUSD', 'DOTUSD', 'MATICUSD',
                     'LTCUSD', 'BCHUSD', 'ATOMUSD', 'ALGOUSD', 'SEIUSD', 'STXUSD'}
    if symbol in crypto_assets or 'USD' in symbol:
        return True
    
    # Indices: check weekday and time
    if symbol in {'SPY', 'QQQ', 'IWM', 'DIA'}:
        weekday = now_et.weekday()  # 0=Mon, 6=Sun
        if weekday >= 5:  # Weekend
            return False
        hour = now_et.hour
        minute = now_et.minute
        # NYSE 9:30-16:00 ET
        market_open = (hour > 9 or (hour == 9 and minute >= 30))
        market_close = hour < 16
        return market_open and market_close
    
    # Forex: open 24/5, closed weekend
    if symbol.endswith('USD') and len(symbol) == 6:
        weekday = now_et.weekday()
        if weekday >= 5:
            # Check if Friday evening
            if weekday == 5:  # Saturday
                return False
            if weekday == 6:  # Sunday
                return now_et.hour < 17
        return True
    
    return True

def queue_pending_trades(plan):
    """Queue all trades to pending file if market is closed."""
    today = datetime.now().strftime('%Y-%m-%d')
    pending_path = PENDING_DIR / f'pending_trades_{today}.json'
    existing = load_json(pending_path) if pending_path.exists() else []
    
    new_entries = []
    for trade in plan.get('queue', []):
        if trade.get('status') == 'queued_sunday_open':
            entry = {
                **trade,
                'queued_at': datetime.now(timezone.utc).isoformat(),
                'reason': 'Sunday open window - awaiting market open'
            }
            new_entries.append(entry)
    
    existing.extend(new_entries)
    save_json(pending_path, existing)
    log(f"Queued {len(new_entries)} trades to {pending_path}")
    return pending_path

def validate_trade(trade):
    """Validate trade parameters."""
    required = ['pair', 'direction', 'entry', 'sl', 'tp', 'broker']
    missing = [k for k in required if not trade.get(k)]
    if missing:
        log(f"❌ Missing fields: {missing}")
        return False
    
    # Check SL/TP direction
    entry = float(trade['entry'])
    sl = float(trade['sl'])
    tp = float(trade['tp'])
    
    if trade['direction'] == 'sell':
        if sl <= entry or tp >= entry:
            log(f"❌ Invalid sell SL/TP: entry={entry}, sl={sl}, tp={tp}")
            return False
    elif trade['direction'] == 'buy':
        if sl >= entry or tp <= entry:
            log(f"❌ Invalid buy SL/TP: entry={entry}, sl={sl}, tp={tp}")
            return False
    
    return True

def check_broker_connectivity(broker):
    """Check if broker API is reachable."""
    if broker == 'Alpaca':
        base_url = 'https://paper-api.alpaca.markets'
        try:
            r = requests.get(f'{base_url}/v2/account', timeout=10)
            if r.status_code == 200:
                log(f"✅ Alpaca API connected")
                return True
            else:
                log(f"❌ Alpaca API error: {r.status_code} {r.text[:100]}")
                return False
        except Exception as e:
            log(f"❌ Alpaca connection failed: {e}")
            return False
    
    elif broker == 'FTMO':
        # Check MT5 terminal
        try:
            import MetaTrader5 as mt5
            if mt5.initialize():
                log(f"✅ FTMO MT5 connected")
                mt5.shutdown()
                return True
            else:
                log(f"❌ FTMO MT5 init failed: {mt5.last_error()}")
                return False
        except Exception as e:
            log(f"❌ FTMO MT5 error: {e}")
            return False
    
    elif broker == 'Capital.com':
        try:
            import MetaTrader5 as mt5
            cap_path = r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
            if not mt5.initialize(path=cap_path, login=int(os.environ.get('CAPITAL_MT5_LOGIN', '0')), server=os.environ.get('CAPITAL_MT5_SERVER', 'Capital.ComBah-Demo')):
                log(f"✅ Capital.com MT5 connected")
                mt5.shutdown()
                return True
            else:
                log(f"❌ Capital.com MT5 init failed: {mt5.last_error()}")
                return False
        except Exception as e:
            log(f"❌ Capital.com MT5 error: {e}")
            return False
    
    elif broker == 'IBKR':
        log(f"⚠️ IBKR requires Gateway at 127.0.0.1:7497 - manual check needed")
        return False
    
    return False

def execute_alpaca_trade(trade):
    """Execute trade on Alpaca paper with verified fills."""
    base_url = 'https://paper-api.alpaca.markets'
    api_key = os.environ.get('ALPACA_API_KEY_ID', '')
    secret = os.environ.get('ALPACA_API_SECRET_KEY', '')
    
    # Check if we have secret
    if not secret:
        log(f"❌ Alpaca secret missing")
        return {'status': 'failed', 'reason': 'missing_secret'}
    
    headers = {
        'APCA-API-KEY-ID': api_key,
        'APCA-API-SECRET-KEY': secret,
        'Content-Type': 'application/json'
    }
    
    symbol = trade['pair']
    side = trade['direction']
    qty = 1  # Default to 1 share/unit
    
    # Submit main order
    order_data = {
        'symbol': symbol,
        'qty': qty,
        'side': side,
        'type': 'limit',
        'time_in_force': 'day',
        'limit_price': float(trade['entry'])
    }
    
    try:
        r = requests.post(f'{base_url}/v2/orders', headers=headers, 
                         json=order_data, timeout=10)
        if r.status_code in (200, 201):
            order = r.json()
            log(f"✅ Alpaca {symbol} {side} order submitted: {order['id']}")
            
            # Wait for fill
            time.sleep(5)
            order_id = order['id']
            r2 = requests.get(f'{base_url}/v2/orders/{order_id}', headers=headers, timeout=10)
            if r2.status_code == 200:
                order_status = r2.json()
                if order_status['status'] == 'filled':
                    log(f"✅ Alpaca {symbol} filled @ {order_status.get('filled_avg_price')}")
                    return {'status': 'filled', 'order': order_status}
                else:
                    log(f"⚠️ Alpaca {symbol} status: {order_status['status']}")
                    return {'status': order_status['status'], 'order': order_status}
        else:
            log(f"❌ Alpaca order failed: {r.status_code} {r.text[:200]}")
            return {'status': 'failed', 'error': r.text[:200]}
    except Exception as e:
        log(f"❌ Alpaca execution error: {e}")
        return {'status': 'error', 'error': str(e)}

def execute_ftmo_trade(trade):
    """Execute trade on FTMO MT5 with FOK."""
    try:
        import MetaTrader5 as mt5
        
        if not mt5.initialize():
            log(f"❌ FTMO init failed: {mt5.last_error()}")
            return {'status': 'failed', 'error': str(mt5.last_error())}
        
        symbol = trade['pair']
        if not symbol.endswith('USD'):
            symbol = f"{symbol}USD"
        
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if not tick or not info:
            log(f"❌ FTMO {symbol} not found")
            mt5.shutdown()
            return {'status': 'failed', 'error': 'symbol_not_found'}
        
        entry = float(trade['entry'])
        sl = float(trade['sl'])
        tp = float(trade['tp'])
        
        # Determine order type
        if trade['direction'] == 'buy':
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        
        # FOK only for Capital.com, omit type_filling for FTMO
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': float(info.volume_min),
            'type': order_type,
            'price': price,
            'sl': sl,
            'tp': tp,
            'deviation': 20,
            'magic': 20260726,
            'comment': f"OuroTaurus {symbol} {trade['direction']}",
            'type_time': mt5.ORDER_TIME_GTC,
            # No type_filling for FTMO
        }
        
        result = mt5.order_send(request)
        mt5.shutdown()
        
        if result and result.retcode in (10009, 10008, 10004):
            log(f"✅ FTMO {symbol} {trade['direction']} placed: ticket={result.order}")
            return {
                'status': 'placed',
                'ticket': int(result.order) if result.order else None,
                'deal': int(result.deal) if result.deal else None,
                'retcode': int(result.retcode),
                'price': float(result.price) if result.price else None
            }
        else:
            log(f"❌ FTMO {symbol} failed: retcode={result.retcode if result else 'None'} comment={result.comment if result else 'None'}")
            return {
                'status': 'failed',
                'retcode': int(result.retcode) if result else None,
                'comment': str(result.comment) if result else 'no_response'
            }
    
    except Exception as e:
        log(f"❌ FTMO execution error: {e}")
        return {'status': 'error', 'error': str(e)}

def execute_capital_trade(trade):
    """Execute trade on Capital.com MT5 with FOK."""
    try:
        import MetaTrader5 as mt5
        
        cap_path = r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
        if mt5.initialize(path=cap_path, login=int(os.environ.get('CAPITAL_MT5_LOGIN', '0')), server=os.environ.get('CAPITAL_MT5_SERVER', 'Capital.ComBah-Demo')):
            log(f"❌ Capital init failed: {mt5.last_error()}")
            return {'status': 'failed', 'error': str(mt5.last_error())}
        
        symbol = trade['pair']
        if not symbol.endswith('USD'):
            symbol = f"{symbol}USD"
        
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if not tick or not info:
            log(f"❌ Capital {symbol} not found")
            mt5.shutdown()
            return {'status': 'failed', 'error': 'symbol_not_found'}
        
        entry = float(trade['entry'])
        sl = float(trade['sl'])
        tp = float(trade['tp'])
        
        if trade['direction'] == 'buy':
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        
        # FOK only for Capital.com
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': float(info.volume_min),
            'type': order_type,
            'price': price,
            'sl': sl,
            'tp': tp,
            'deviation': 20,
            'magic': 20260726,
            'comment': f"OuroTaurus {symbol} {trade['direction']}",
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_FOK,  # FOK ONLY for Capital.com
        }
        
        result = mt5.order_send(request)
        mt5.shutdown()
        
        if result and result.retcode in (10009, 10008, 10004):
            log(f"✅ Capital {symbol} {trade['direction']} placed: ticket={result.order}")
            return {
                'status': 'placed',
                'ticket': int(result.order) if result.order else None,
                'deal': int(result.deal) if result.deal else None,
                'retcode': int(result.retcode),
                'price': float(result.price) if result.price else None
            }
        else:
            log(f"❌ Capital {symbol} failed: retcode={result.retcode if result else 'None'} comment={result.comment if result else 'None'}")
            return {
                'status': 'failed',
                'retcode': int(result.retcode) if result else None,
                'comment': str(result.comment) if result else 'no_response'
            }
    
    except Exception as e:
        log(f"❌ Capital execution error: {e}")
        return {'status': 'error', 'error': str(e)}

def update_status_file(execution_results):
    """Update crypto_execution_status.json with results."""
    status = load_json(STATUS_PATH)
    status['last_updated'] = datetime.now(timezone.utc).isoformat()
    
    # Add to filled/pending/blocked based on result
    for result in execution_results:
        pair = result.get('pair', 'UNKNOWN')
        entry_data = next((t for t in result.get('raw_trades', [])), {})
        
        if result.get('status') in ('filled', 'placed'):
            status['filled'].append({
                'broker': result.get('broker'),
                'pair': pair,
                'side': entry_data.get('direction', 'N/A'),
                'status': result.get('status'),
                'placed_at': datetime.now(timezone.utc).isoformat(),
                'details': result
            })
        elif result.get('status') == 'failed':
            # Move from pending to blocked with reason
            status['blocked'].append({
                'pair': pair,
                'reason': result.get('error', result.get('comment', 'unknown'))
            })
    
    save_json(STATUS_PATH, status)
    log(f"Updated {STATUS_PATH}")

def main():
    log("=" * 60)
    log("SUNDAY OPEN TRADE EXECUTOR")
    log("=" * 60)
    
    # Load plan
    plan = load_json(PLAN_PATH)
    if not plan:
        log(f"❌ No trade plan found at {PLAN_PATH}")
        return
    
    queued_trades = [t for t in plan.get('queue', []) 
                     if t.get('status') == 'queued_sunday_open']
    
    if not queued_trades:
        log("No queued_sunday_open trades found")
        return
    
    log(f"Found {len(queued_trades)} queued trades")
    
    # Check market open status
    closed_trades = []
    open_trades = []
    for trade in queued_trades:
        symbol = trade['pair']
        broker = trade.get('broker', 'unknown')
        if is_market_open(symbol, broker):
            open_trades.append(trade)
        else:
            log(f"⏸️ {symbol} market closed - will queue")
            closed_trades.append(trade)
    
    if closed_trades:
        queue_pending_trades({'queue': closed_trades})
    
    if not open_trades:
        log("No open markets to trade - all queued for next open")
        return
    
    # Check broker connectivity
    brokers_needed = set(t.get('broker') for t in open_trades)
    log(f"Checking brokers: {brokers_needed}")
    
    for broker in brokers_needed:
        if not check_broker_connectivity(broker):
            log(f"⚠️ {broker} not available - queuing trades")
            queue_pending_trades({'queue': [t for t in open_trades if t.get('broker') == broker]})
            open_trades = [t for t in open_trades if t.get('broker') != broker]
    
    if not open_trades:
        log("All trades queued - no brokers available")
        return
    
    # Validate and execute
    execution_results = []
    for trade in open_trades:
        log(f"\n--- Executing {trade['pair']} {trade['direction']} ---")
        
        if not validate_trade(trade):
            trade['status'] = 'failed'
            trade['reason'] = 'validation_failed'
            execution_results.append({
                'pair': trade['pair'],
                'status': 'failed',
                'broker': trade.get('broker'),
                'raw_trades': [trade],
                'error': 'validation_failed'
            })
            continue
        
        broker = trade.get('broker')
        result = None
        
        if broker == 'Alpaca':
            result = execute_alpaca_trade(trade)
        elif broker == 'FTMO':
            result = execute_ftmo_trade(trade)
        elif broker == 'Capital.com':
            result = execute_capital_trade(trade)
        elif broker == 'IBKR':
            log(f"⚠️ IBKR auto-execution not implemented - manual review needed")
            result = {'status': 'queued', 'broker': 'IBKR', 'pair': trade['pair']}
        else:
            log(f"❌ Unknown broker: {broker}")
            result = {'status': 'failed', 'error': f'unknown broker {broker}'}
        
        execution_results.append({
            'pair': trade['pair'],
            'status': result.get('status', 'unknown'),
            'broker': broker,
            'raw_trades': [trade],
            **result
        })
        
        time.sleep(2)  # Rate limit
    
    # Update status file
    update_status_file(execution_results)
    
    # Summary
    log("\n" + "=" * 60)
    log("EXECUTION SUMMARY")
    log("=" * 60)
    for r in execution_results:
        status_icon = "✅" if r.get('status') in ('filled', 'placed') else "❌"
        log(f"{status_icon} {r['pair']}: {r.get('status')} via {r.get('broker')}")
    
    placed = len([r for r in execution_results if r.get('status') in ('filled', 'placed')])
    failed = len([r for r in execution_results if r.get('status') in ('failed', 'error')])
    queued = len([r for r in execution_results if r.get('status') == 'queued'])
    
    log(f"\nPlaced: {placed} | Failed: {failed} | Queued: {queued}")
    
    if placed > 0:
        log("\n⚠️  Remember: need live verified fills before counting trades as placed")
    
    log("=" * 60)

if __name__ == '__main__':
    main()