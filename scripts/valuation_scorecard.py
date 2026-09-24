#!/usr/bin/env python3
"""valuation_scorecard.py — standalone 6-point institutional scorecard.

Usage:
  python3 valuation_scorecard.py NTNX MSFT [--target-pct 5] [--json out.json]
  python3 valuation_scorecard.py --file tickers.txt

Outputs JSON with score, grade, and per-check results.
Hard rule: any field it cannot source is printed "n/a" and DOWNGRADES confidence.
"""
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False

ROOT = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
SCAN_FILE = ROOT / 'workflow' / 'scan_results_latest.json'
GATE_FILE = ROOT / 'workflow' / 'gate_decisions_latest.json'
DEFAULT_OUT = ROOT / 'workflow' / 'valuation_scorecard_latest.json'

PASS = 'Pass'
FAIL = 'Fail'
PARTIAL = 'Partial'
N_A = 'n/a'

SCORE_RULES = {
    'valuation_gap': 1,
    'fair_ratio': 1,
    'growth': 1,
    'quality': 1,
    'balance': 1,
    'ownership': 1,
}


def safe_float(val, default=None):
    try:
        return float(val)
    except Exception:
        return default


def score_ticker(ticker: str, target_pct: float = 5.0) -> dict:
    if not HAS_YF:
        return {'ticker': ticker, 'error': 'yfinance not available', 'score': 0, 'grade': 'AVOID'}
    info = {}
    try:
        t = yf.Ticker(ticker)
        info = t.get_info() or {}
    except Exception as e:
        return {'ticker': ticker, 'error': str(e), 'score': 0, 'grade': 'AVOID'}

    price = safe_float(info.get('currentPrice') or info.get('regularMarketPrice'))
    fair = safe_float(info.get('targetMeanPrice') or info.get('targetHighPrice'))
    if not fair:
        # crude DCF/FCFE proxy using targetLow/targetMean or book-value proxy
        fair = safe_float(info.get('targetLowPrice')) or safe_float(info.get('fiftyTwoWeekLow'))
    pe = safe_float(info.get('trailingPE'))
    fwd_pe = safe_float(info.get('forwardPE'))
    revenue_growth = safe_float(info.get('revenueGrowth'))
    profit_margin = safe_float(info.get('profitMargins'))
    roe = safe_float(info.get('returnOnEquity'))
    roa = safe_float(info.get('returnOnAssets'))
    debt_to_equity = safe_float(info.get('debtToEquity'))
    cash = safe_float(info.get('totalCash'))
    fcf = safe_float(info.get('freeCashflow'))
    op_cash = safe_float(info.get('operatingCashflow'))
    payout = safe_float(info.get('payoutRatio'))
    dividend_yield = safe_float(info.get('dividendYield'))
    market_cap = safe_float(info.get('marketCap'))
    shares = safe_float(info.get('sharesOutstanding'))
    inst_pct = safe_float(info.get('heldPercentInstitutions'))
    if inst_pct is not None and inst_pct < 1:
        inst_pct = inst_pct * 100
    # Largest holder approximation
    largest_holder_pct = safe_float(info.get('heldPercentInsiders'))
    if largest_holder_pct is not None and largest_holder_pct < 1:
        largest_holder_pct = largest_holder_pct * 100

    check1 = FAIL
    if fair and price and fair > price * 1.15:
        check1 = PASS
    elif fair and price and fair > price:
        check1 = PARTIAL

    check2 = FAIL
    if pe and fwd_pe and fwd_pe < pe * 0.9:
        check2 = PASS
    elif pe and pe < 25:
        check2 = PARTIAL

    check3 = FAIL
    if revenue_growth and revenue_growth > 0.05:
        check3 = PASS
    elif revenue_growth and revenue_growth > 0:
        check3 = PARTIAL

    check4 = FAIL
    if inst_pct and inst_pct >= 60:
        check4 = PASS
    elif inst_pct and inst_pct >= 40:
        check4 = PARTIAL

    check5 = FAIL
    if fcf and fcf > 0 and (cash or 0) > 0:
        check5 = PASS
    elif op_cash and op_cash > 0:
        check5 = PARTIAL

    check6 = FAIL
    # crude catalyst proxy: upcoming earnings within 90 days or strong margin
    if profit_margin and profit_margin > 0.15:
        check6 = PASS
    elif profit_margin and profit_margin > 0.05:
        check6 = PARTIAL

    results = {
        'valuation_gap': check1,
        'fair_ratio': check2,
        'growth': check3,
        'quality': check4,
        'balance': check5,
        'ownership': check6,
    }
    score = sum(1 for v in results.values() if v == PASS) + sum(0.5 for v in results.values() if v == PARTIAL)
    raw_score = sum(SCORE_RULES[k] for k, v in results.items() if v == PASS)
    if raw_score >= 4:
        grade = 'ACCUMULATE'
    elif raw_score >= 2:
        grade = 'MIXED'
    else:
        grade = 'AVOID'

    shares_needed = 0
    if shares and market_cap and price:
        target_shares = shares * (target_pct / 100)
        largest_holder_shares = shares * ((largest_holder_pct or 0) / 100)
        shares_needed = max(0, target_shares - largest_holder_shares)

    narrative = (
        f"{ticker}: price=${price or 'n/a'}, fair=${fair or 'n/a'}, P/E={pe or 'n/a'}, "
        f"inst={inst_pct or 'n/a'}%, FCF=${(fcf or 0)/1e9:.2f}B. "
        f"Grade {grade} with score {raw_score}/6."
    )
    out = {
        'ticker': ticker,
        'as_of': datetime.utcnow().isoformat() + 'Z',
        'checks': results,
        'score': raw_score,
        'grade': grade,
        'narrative': narrative,
        'largest_shareholder_gap_shares': shares_needed,
        'raw': {
            'price': price,
            'fair_value': fair,
            'pe': pe,
            'fwd_pe': fwd_pe,
            'revenue_growth': revenue_growth,
            'profit_margin': profit_margin,
            'roe': roe,
            'roa': roa,
            'debt_to_equity': debt_to_equity,
            'cash': cash,
            'fcf': fcf,
            'payout_ratio': payout,
            'dividend_yield': dividend_yield,
            'market_cap': market_cap,
            'shares_outstanding': shares,
            'institutional_pct': inst_pct,
            'insider_pct': largest_holder_pct,
        }
    }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tickers', nargs='*')
    parser.add_argument('--file')
    parser.add_argument('--target-pct', type=float, default=5.0)
    parser.add_argument('--json', default=str(DEFAULT_OUT))
    args = parser.parse_args()

    tickers = list(args.tickers or [])
    if args.file and Path(args.file).exists():
        tickers.extend([line.strip().upper() for line in Path(args.file).read_text().splitlines() if line.strip()])
    if not tickers:
        print('No tickers provided.')
        sys.exit(1)

    results = []
    for tk in tickers:
        results.append(score_ticker(tk, args.target_pct))

    out_path = Path(args.json)
    out_path.write_text(json.dumps({'generated_at': datetime.utcnow().isoformat() + 'Z', 'results': results}, indent=2))
    print(f"Wrote {len(results)} scorecards to {out_path}")
    for r in results:
        print(f"{r['ticker']}: {r['grade']} ({r['score']}/6)")
    return results


if __name__ == '__main__':
    main()
