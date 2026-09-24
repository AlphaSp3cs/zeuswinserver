#!/usr/bin/env python3
"""
Toast-to-eToro Demo Bridge
- Reads toast trade signals from scanner log or a queue file
- Maps scanner symbols to eToro instrument IDs
- Places demo orders on eToro
- Logs results for profitability tracking
"""
import json, time, uuid, re, sys
from pathlib import Path
from datetime import datetime, timezone

import requests

# Paths
BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE_FIRM / 'workflow'
SYMBOL_MAP = WORKFLOW / 'etoro_symbol_map.json'
SCANNER_LOG = WORKFLOW / 'crypto_weekend_log.jsonl'
TRADE_LOG = WORKFLOW / 'etoro_demo_trades.jsonl'
QUEUE_FILE = WORKFLOW / 'etoro_demo_order_queue.jsonl'
PROFIT_LOG = WORKFLOW / 'etoro_demo_profit.jsonl'

# eToro config
ETORO_BASE = 'https://public-api.etoro.com'
ETORO_API_KEY = 'sdgdskldFPLGfjHn1421dgnlxdGTbngdflg6290bRjslfihsjhSDsdgGHH25hjf'
ETORO_USER_KEY = 'eyJjaSI6IjYwY2FiYjBiLTU1OTctNDQ4NS04ZjYzLTdlOWUwNTZlMGJiOCIsImVhbiI6IlVucmVnaXN0ZXJlZEFwcGxpY2F0aW9uIiwiZWsiOiIuVjZ3S2xJOEpTajlrbHRySndMeHMzNEMwMXkuMDFrNG8tWjBScGllYzBCUHBSc1JrR3JocUQ3RHh2Q01wY3QtRURQSlFMTE1UalJiQ0VBNkxUYklhSklULnJkVnFGYjdGcjJSYjZpakhnUV8ifQ__'

def etoro_headers():
    return {
        'x-api-key': ETORO_API_KEY,
        'x-user-key': ETORO_USER_KEY,
        'x-request-id': str(uuid.uuid4()),
        'Accept': 'application/json',
    }

def load_symbol_map():
    if SYMBOL_MAP.exists():
        return json.loads(SYMBOL_MAP.read_text(encoding='utf-8'))
    return {}

def normalize_symbol(symbol: str) -> str:
    """BTC-USD -> BTC, ETH-USD -> ETH, etc."""
    s = symbol.upper().replace('-USD', '').replace('USD', '')
    return s.strip()

def find_eToro_instrument_id(symbol: str, symbol_map: dict):
    norm = normalize_symbol(symbol)
    if norm in symbol_map:
        return symbol_map[norm].get('id')
    if symbol.upper() in symbol_map:
        return symbol_map[symbol.upper()].get('id')
    if f'{norm}-USD' in symbol_map:
        return symbol_map[f'{norm}-USD'].get('id')
    return None

def place_demo_order(instrument_id, action, amount, leverage=1, stop_loss=None, take_profit=None):
    url = f'{ETORO_BASE}/api/v2/trading/execution/demo/orders'
    payload = {
        'action': 'open',
        'transaction': action.lower(),
        'instrumentID': int(instrument_id) if str(instrument_id).isdigit() else instrument_id,
        'orderType': 'mkt',
        'leverage': leverage,
        'amount': amount,
        'orderCurrency': 'usd',
    }
    if stop_loss:
        payload['stopLossRate'] = stop_loss
    if take_profit:
        payload['takeProfitRate'] = take_profit

    time.sleep(0.35)
    r = requests.post(url, headers=etoro_headers(), json=payload, timeout=15)
    result = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'instrument_id': instrument_id,
        'action': action,
        'amount': amount,
        'leverage': leverage,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'status_code': r.status_code,
        'response': r.text[:500],
    }
    with TRADE_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(result) + '\n')
    return result

def enqueue_signal(sig, ticket):
    entry = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'symbol': sig.get('symbol'),
        'side': sig.get('direction', sig.get('side', 'BUY')),
        'entry': sig.get('price', ticket.get('entry')),
        'sl': ticket.get('sl'),
        'tp1': ticket.get('tp1'),
        'tp2': ticket.get('tp2'),
        'size': ticket.get('size'),
        'broker': sig.get('broker'),
        'urgency': sig.get('urgency'),
        'reason': sig.get('reason'),
        'status': 'QUEUED',
    }
    with QUEUE_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')
    return entry

def process_queue():
    symbol_map = load_symbol_map()
    if not QUEUE_FILE.exists():
        return 0, 0
    lines = QUEUE_FILE.read_text(encoding='utf-8').strip().split('\n')
    pending = [json.loads(x) for x in lines if x.strip()]
    remaining = []
    placed = 0
    failed = 0
    for order in pending:
        if order.get('status') != 'QUEUED':
            remaining.append(order)
            continue
        symbol = order.get('symbol', '')
        instr_id = find_eToro_instrument_id(symbol, symbol_map)
        if not instr_id:
            broker = order.get('broker', 'ETORO').upper()
            order['status'] = 'ROUTED_' + broker
            order['error'] = f'no eToro instrument for {symbol}, routed to {broker}'
            remaining.append(order)
            continue
        result = place_demo_order(
            instrument_id=instr_id,
            action=order.get('side', 'buy'),
            amount=order.get('size', 1.0),
            leverage=1,
            stop_loss=order.get('sl'),
            take_profit=order.get('tp1'),
        )
        order['status'] = 'PLACED' if result.get('status_code') == 200 else 'FAILED'
        order['etoro_response'] = result.get('response', '')[:200]
        order['orderId'] = None
        if result.get('status_code') == 200:
            try:
                order['orderId'] = json.loads(result['response']).get('orderId')
                placed += 1
            except Exception:
                failed += 1
        else:
            failed += 1
        remaining.append(order)
    QUEUE_FILE.write_text(''.join(json.dumps(x) + '\n' for x in remaining), encoding='utf-8')
    return placed, failed

def process_queue_loop(poll_seconds=5):
    print(f'Starting eToro demo queue processor: {QUEUE_FILE}')
    while True:
        try:
            placed, failed = process_queue()
            if placed or failed:
                print(f'Queue run: placed={placed} failed={failed} @ {datetime.now(timezone.utc).isoformat()}')
        except Exception as e:
            print(f'Queue error: {e}')
        time.sleep(poll_seconds)

def mark_to_market():
    """Lightweight profitability check from queued orders using scanner cycle prices as mark."""
    if not QUEUE_FILE.exists():
        return
    try:
        queue = [json.loads(x) for x in QUEUE_FILE.read_text(encoding='utf-8').strip().split('\n') if x.strip()]
    except Exception:
        return
    for order in queue:
        if order.get('status') != 'PLACED' or not order.get('entry'):
            continue
        entry = float(order['entry'])
        sl = float(order.get('sl') or 0)
        tp1 = float(order.get('tp1') or 0)
        side = order.get('side', 'BUY').upper()
        # Use latest scanner cycle price if available
        mark = entry
        cycle_price = order.get('mark_price')
        if cycle_price:
            mark = float(cycle_price)
        if side == 'BUY':
            pnl_pct = (mark - entry) / entry * 100.0
        else:
            pnl_pct = (entry - mark) / entry * 100.0
        profit_entry = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'orderId': order.get('orderId'),
            'symbol': order.get('symbol'),
            'side': side,
            'entry': entry,
            'mark': mark,
            'sl': sl,
            'tp1': tp1,
            'pnl_pct': round(pnl_pct, 4),
        }
        with PROFIT_LOG.open('a', encoding='utf-8') as f:
            f.write(json.dumps(profit_entry) + '\n')

def scan_latest_signals(limit=20):
    signals = []
    if not SCANNER_LOG.exists():
        return signals
    lines = SCANNER_LOG.read_text(encoding='utf-8').strip().split('\n')
    for line in lines[-limit:]:
        try:
            entry = json.loads(line)
            if entry.get('event') in ('TICKET_PLACED', 'TICKET_FAIL'):
                signals.append(entry)
        except Exception:
            continue
    return signals

def main():
    print('=== Toast-to-eToro Demo Bridge ===')
    print(f'Time: {datetime.now(timezone.utc).isoformat()}')
    symbol_map = load_symbol_map()
    print(f'Loaded {len(symbol_map)} eToro instrument mappings')
    signals = scan_latest_signals(limit=20)
    print(f'Found {len(signals)} recent scanner signals')
    placed = failed = 0
    for sig in signals:
        event = sig.get('event')
        symbol = sig.get('symbol', '')
        side = sig.get('side', '').upper()
        entry = sig.get('entry')
        sl = sig.get('sl')
        tp = sig.get('tp')
        profile = sig.get('profile', '')
        if not symbol.endswith('-USD'):
            continue
        instr_id = find_eToro_instrument_id(symbol, symbol_map)
        if not instr_id:
            print(f'SKIP {symbol}: no eToro instrument ID found')
            failed += 1
            continue
        action = side if side in ('BUY', 'SELL') else ('buy' if side == 'LONG' else 'sell')
        amount = round(100.0 / entry, 6) if entry and entry > 0 else 1.0
        ticket = {
            'ticket_id': f'etoro-demo-{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}-{symbol}',
            'symbol': symbol,
            'entry': entry,
            'sl': sl,
            'tp1': tp,
            'tp2': tp,
            'size': amount,
        }
        enqueue_signal(sig, ticket)
        print(f'QUEUED {symbol} -> eToro ID {instr_id}: {action.upper()} {amount:.6f}')
    p, f = process_queue()
    placed += p
    failed += f
    mark_to_market()
    print(f'\n=== Bridge Run Summary ===')
    print(f'Demo orders placed: {placed}')
    print(f'Failed: {failed}')
    print(f'Trade log: {TRADE_LOG}')
    print(f'Queue: {QUEUE_FILE}')

if __name__ == '__main__':
    if '--loop' in sys.argv:
        process_queue_loop()
    else:
        main()
