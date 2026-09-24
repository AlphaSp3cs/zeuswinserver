"""
valuation_rail.py
- Equity-only fundamental/valuation validation rail.
- Designed to be called BEFORE trade gate for any equity candidate.
- Percent-field normalization to avoid fraction/percent bugs.
- ETF-aware: does not mark pure ETFs as AVOID just because company fundamentals are absent.
"""
import json, math
from pathlib import Path

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')

# Percent fields that yfinance sometimes returns as fractions (0.147 = 14.7%)
PERCENT_FRACTION_FIELDS = {
    'pctHeld','pctInsiders','pctInstitutions',
    'dividendYield','payoutRatio','profitMargins','returnOnEquity',
    'revenueGrowth','earningsGrowth','insiderPercent','institutionPercent',
}

def normalize_percent_fields(info: dict) -> dict:
    if not info:
        return {}
    out = {}
    for k, v in info.items():
        if k in PERCENT_FRACTION_FIELDS and isinstance(v, (int, float)) and v is not None:
            out[k] = v * 100.0 if abs(v) <= 1.0 else v
        else:
            out[k] = v
    return out

def is_etf(info: dict, ticker: str) -> bool:
    if not info:
        return False
    hints = ['exchangeTradedFund','etf','fundFamily','category']
    text = ' '.join(str(info.get(k,'')) for k in hints).lower()
    etf_tickers = {'SCHD','VYM','VOO','VTI','SPY','QQQ','IWM','DIA','XLK','XLF','XLE','XLV','XLI','XLY','XLP','XLU','XLB','XLRE','XLC','XBI','SMH','SOXX'}
    return any(x in text for x in ['exchange traded fund',' etf']) or ticker.upper() in etf_tickers

def equity_fundamental_grade(ticker: str, info: dict | None = None):
    """
    Returns dict:
      grade: A/B/C/D/ETF/N/A
      score: 0-6
      pe/pg/rev/roe/pf: fields
      etf: bool
      flags: list[str]
    """
    flags = []
    if info is None:
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
        except Exception as e:
            return {'grade':'N/A','score':0,'pe':None,'peg':None,'rev':None,'roe':None,'pf':None,'etf':False,'flags':[f'fetch_failed:{e}']}
    info = normalize_percent_fields(info)
    etf = is_etf(info, ticker)
    if etf:
        return {'grade':'ETF','score':None,'pe':info.get('trailingPE'),'peg':info.get('pegRatio'),
                'rev':info.get('revenueGrowth'),'roe':info.get('returnOnEquity'),
                'pf':info.get('priceToBook'),'etf':True,'flags':['no_company_fundamentals']}

    pe = info.get('trailingPE'); peg = info.get('pegRatio')
    rev = info.get('revenueGrowth'); roe = info.get('returnOnEquity')
    pf = info.get('priceToBook')
    score = 0.0
    if isinstance(rev,(int,float)) and rev > 0.20: score += 2.0
    elif isinstance(rev,(int,float)) and rev > 0.10: score += 1.0
    if isinstance(roe,(int,float)) and roe > 0.15: score += 1.0
    if isinstance(peg,(int,float)) and peg < 1.5: score += 1.0
    if isinstance(pf,(int,float)) and pf < 3.0: score += 1.0
    if isinstance(pe,(int,float)) and pe < 80: score += 0.5
    grade = 'A' if score >= 4.5 else 'B' if score >= 3.0 else 'C' if score >= 1.5 else 'D'
    if score < 2.0: flags.append('weak_fundamentals')
    return {'grade':grade,'score':score,'pe':pe,'peg':peg,'rev':rev,'roe':roe,'pf':pf,'etf':False,'flags':flags}

def pass_fail(grade_obj: dict) -> dict:
    if grade_obj.get('etf'):
        return {'pass': True, 'reason':'ETF — exempt from company fundamental grading', 'block':False}
    score = grade_obj.get('score') or 0.0
    grade = grade_obj.get('grade','N/A')
    if grade == 'A':
        return {'pass':True,'reason':f'Accumulate grade A score={score:.1f}','block':False}
    if grade == 'B':
        return {'pass':True,'reason':f'Mixed/Add grade B score={score:.1f}','block':False}
    if grade == 'C':
        return {'pass':False,'reason':f'Reduce/Monitor grade C score={score:.1f}','block':False}
    return {'pass':False,'reason':f'Avoid grade {grade} score={score:.1f}','block':True}

if __name__ == '__main__':
    samples = ['SCHD','VYM','NVDA','AAPL','BTC-USD','ETH-USD']
    for t in samples:
        g = equity_fundamental_grade(t)
        print(t, g['grade'], 'score=',g['score'], 'etf=',g['etf'], 'flags=',g['flags'], pass_fail(g))
