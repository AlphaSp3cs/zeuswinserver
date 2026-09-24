#!/usr/bin/env python3
"""
Build live broker-ready execution plan for 2026-08-17.
Connects to FTMO LEFT and Capital RIGHT, probes symbols, gets live quotes,
filters executable symbols, and builds pre-open reroute plan.
"""
import json
import sys
import os
import math
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\scripts')
from mt5_connect import connect as mt5_connect, KNOWN_BROKERS, shutdown as mt5_shutdown

ROOT = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
SCAN_PATH = ROOT / 'workflow' / 'comprehensive_scan_20260817T014320Z.json'
OUT_PATH = ROOT / 'workflow' / 'preopen_reroute_plan_20260817.json'

# Symbol name normalization: scan name -> MT5 symbol candidates
SYMBOL_ALIASES = {
    'LINK-USD': ['LINKUSD', 'LINK/USD', 'LINK'],
    'USDMXN': ['USDMXN', 'USD/MXN', 'USD MXN'],
    'USDTRY': ['USDTRY', 'USD/TRY', 'USD TRY'],
    'GBPCHF': ['GBPCHF', 'GBP/CHF', 'GBP CHF'],
    'USDSGD': ['USDSGD', 'USD/SGD', 'USD SGD'],
    'AUDUSD': ['AUDUSD', 'AUD/USD', 'AUD USD'],
    'GBPUSD': ['GBPUSD', 'GBP/USD', 'GBP USD'],
    'USDNOK': ['USDNOK', 'USD/NOK', 'USD NOK'],
    'EURCHF': ['EURCHF', 'EUR/CHF', 'EUR CHF'],
    'USDCAD': ['USDCAD', 'USD/CAD', 'USD CAD'],
    'NZDJPY': ['NZDJPY', 'NZD/JPY', 'NZD JPY'],
}


def side_from_reasons(reasons):
    if not reasons:
        return None
    # Priority: explicit directional signals
    bullish = sum(1 for r in reasons if r in ('RSI_OVERSOLD', 'ALL_TF_BULL'))
    bearish = sum(1 for r in reasons if r in ('RSI_OVERBOUGHT', 'ALL_TF_BEAR'))
    if bullish > bearish:
        return 'LONG'
    if bearish > bullish:
        return 'SHORT'
    # Mixed -> infer from first directional reason
    for r in reasons:
        if r in ('RSI_OVERSOLD', 'ALL_TF_BULL'):
            return 'LONG'
        if r in ('RSI_OVERBOUGHT', 'ALL_TF_BEAR'):
            return 'SHORT'
    return None


def round_price(sym, price):
    s = sym.upper()
    if any(k in s for k in ['JPY', 'JP225']):
        return round(float(price), 3)
    if any(k in s for k in ['XAU', 'XAG', 'XPT', 'XPD']):
        return round(float(price), 2)
    if any(k in s for k in ['BTC', 'ETH', 'LINK']):
        return round(float(price), 2)
    if any(k in s for k in ['US30', 'US500', 'NAS100', 'UK100', 'GER40', 'HK50', 'ES', 'NQ', 'YM']):
        return round(float(price), 1)
    return round(float(price), 5)


def probe_symbol(mt5_conn, candidates):
    for sym in candidates:
        info = mt5_conn.symbol_info(sym)
        if info is None:
            continue
        mt5_conn.symbol_select(sym, True)
        tick = mt5_conn.symbol_info_tick(sym)
        if tick and tick.bid > 0 and tick.ask > 0:
            return sym, tick, info
    return None, None, None


def get_account_info(mt5_conn):
    info = mt5_conn.account_info()
    if info is None:
        return None
    return {
        'login': info.login,
        'server': info.server,
        'equity': float(info.equity),
        'balance': float(info.balance),
        'leverage': info.leverage,
    }


def build_plan():
    # Load scan data
    with open(SCAN_PATH, 'r', encoding='utf-8') as f:
        scan = json.load(f)

    sectors = scan.get('sectors', {})
    viable = []
    for symbol, info in sectors.items():
        if info.get('viable'):
            viable.append({
                'symbol': symbol,
                'broker_routing': info.get('broker_routing', []),
                'conviction': info.get('conviction'),
                'rsi': info.get('rsi'),
                'last': info.get('last'),
                'atr': info.get('atr'),
                'reason': info.get('reason', []),
                'sector': info.get('sector'),
            })
    viable.sort(key=lambda x: x.get('conviction') or 0, reverse=True)

    # Account equity placeholders - will fetch live
    ftmo_equity = None
    capital_equity = None

    plan = []

    # Connect to FTMO LEFT
    print("[*] Connecting to FTMO LEFT...")
    try:
        mt5_ftmo = mt5_connect('ftmo')
        ftmo_acct = get_account_info(mt5_ftmo)
        print(f"    FTMO account: {ftmo_acct}")
        if ftmo_acct:
            ftmo_equity = ftmo_acct['equity']
    except Exception as e:
        print(f"    FTMO connect failed: {e}")
        mt5_ftmo = None
        ftmo_acct = None

    # Connect to Capital RIGHT
    print("[*] Connecting to Capital RIGHT...")
    try:
        mt5_cap = mt5_connect('capital')
        cap_acct = get_account_info(mt5_cap)
        print(f"    Capital account: {cap_acct}")
        if cap_acct:
            capital_equity = cap_acct['equity']
    except Exception as e:
        print(f"    Capital connect failed: {e}")
        mt5_cap = None
        cap_acct = None

    if not mt5_ftmo and not mt5_cap:
        print("[!] No brokers connected. Cannot build plan.")
        return []

    # Determine routing priority: FTMO LEFT first, then Capital RIGHT
    # Only route to a broker if symbol is in its routing list
    BROKER_ORDER = ['FTMO_LEFT', 'CAPITAL_RIGHT']

    for item in viable:
        scan_sym = item['symbol']
        routing = item.get('broker_routing', [])
        side = side_from_reasons(item.get('reason', []))
        if side is None:
            continue

        atr = item.get('atr')
        if not atr or atr <= 0:
            continue

        # Determine target broker
        target_broker = None
        for brk in BROKER_ORDER:
            if brk in routing:
                target_broker = brk
                break

        if target_broker is None:
            continue

        # Select MT5 connection and equity
        if target_broker == 'FTMO_LEFT':
            mt5_conn = mt5_ftmo
            equity = ftmo_equity
        else:
            mt5_conn = mt5_cap
            equity = capital_equity

        if mt5_conn is None or equity is None or equity <= 0:
            continue

        # Probe symbol availability on this broker
        candidates = SYMBOL_ALIASES.get(scan_sym, [scan_sym])
        mt5_sym, tick, sym_info = probe_symbol(mt5_conn, candidates)
        if mt5_sym is None:
            print(f"    [SKIP] {scan_sym} not executable on {target_broker}")
            continue

        # Use live mid-price as entry
        bid = float(tick.bid)
        ask = float(tick.ask)
        mid = round((bid + ask) / 2.0, 5)

        # Round to symbol digits
        digits = getattr(sym_info, 'digits', 5)
        entry = round(mid, digits)

        # ATR-based SL/TP with 1:2 RR
        atr = float(atr)
        if side == 'LONG':
            sl = round(entry - 1.0 * atr, digits)
            tp = round(entry + 2.0 * atr, digits)
        else:
            sl = round(entry + 1.0 * atr, digits)
            tp = round(entry - 2.0 * atr, digits)

        risk_per_unit = abs(entry - sl)
        if risk_per_unit <= 0:
            print(f"    [SKIP] {scan_sym} zero risk per unit")
            continue

        # Contract size and volume constraints
        contract_size = float(getattr(sym_info, 'trade_contract_size', 1.0))
        volume_min = float(getattr(sym_info, 'volume_min', 0.01))
        volume_max = float(getattr(sym_info, 'volume_max', 100.0))
        volume_step = float(getattr(sym_info, 'volume_step', 0.01))

        # Max 1% equity risk per ticket
        max_risk_usd = equity * 0.01
        # volume = risk_usd / (risk_per_unit * contract_size)
        raw_volume = max_risk_usd / (risk_per_unit * contract_size)
        # Round to step
        steps = math.floor(raw_volume / volume_step)
        volume = round(steps * volume_step, 8)
        volume = max(volume_min, min(volume, volume_max))

        # Crypto volume cap on Capital RIGHT: 0.1 lot
        if target_broker == 'CAPITAL_RIGHT' and item.get('sector', '').lower() == 'crypto':
            volume = min(volume, 0.1)

        actual_risk_usd = volume * risk_per_unit * contract_size
        rr = abs(tp - entry) / risk_per_unit if risk_per_unit > 0 else 0
        risk_pct = (actual_risk_usd / equity) * 100.0 if equity > 0 else 0.0

        plan.append({
            'symbol': scan_sym,
            'broker': target_broker,
            'side': side,
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'rr': round(rr, 2),
            'risk_pct': round(risk_pct, 2),
            'reason': ', '.join(item.get('reason', [])),
            'meta': {
                'mt5_symbol': mt5_sym,
                'bid': bid,
                'ask': ask,
                'atr': round(atr, 5),
                'volume': round(volume, 4),
                'contract_size': contract_size,
                'risk_usd': round(actual_risk_usd, 2),
                'conviction': item.get('conviction'),
                'equity': round(equity, 2),
            }
        })
        print(f"    [OK] {scan_sym} -> {target_broker} {side} entry={entry} sl={sl} tp={tp} vol={volume} risk=${actual_risk_usd:.2f}")

    # Sort by broker priority then conviction
    plan.sort(key=lambda x: (
        0 if x['broker'] == 'FTMO_LEFT' else 1,
        -(x['meta']['conviction'] or 0)
    ))

    # Compact output per user spec
    compact = []
    for p in plan:
        compact.append({
            'symbol': p['symbol'],
            'broker': p['broker'],
            'side': p['side'],
            'entry': p['entry'],
            'sl': p['sl'],
            'tp': p['tp'],
            'rr': p['rr'],
            'risk_pct': p['risk_pct'],
            'reason': p['reason'],
        })

    # Ensure output directory exists
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(compact, f, indent=2)

    print(f"\n[+] Plan written to {OUT_PATH}")
    print(f"    Total setups: {len(compact)}")
    for c in compact:
        print(f"    {c['broker']} | {c['symbol']} | {c['side']} | entry={c['entry']} sl={c['sl']} tp={c['tp']} rr={c['rr']} risk={c['risk_pct']}%")

    # Cleanup
    if mt5_ftmo:
        mt5_shutdown()
    if mt5_cap:
        mt5_shutdown()

    return compact


if __name__ == '__main__':
    build_plan()
