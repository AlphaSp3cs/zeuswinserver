#!/usr/bin/env python3
"""
zeus_gap_filler.py
Systematic gap filler: ingests high-value sources the bookmark set exposed.
Outputs unified regime/sentiment/event JSON for:
- WorldMonitor geopolitics/focal points
- FinancialJuice economic calendar
- LunarCrush BTC social sentiment
- WhaleWisdom / SEC insider flow
- Polymarket prediction probabilities
"""

import datetime
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
OUT_PATH = BASE_DIR / 'zeus_gap_filler.json'
HEADERS = {'User-Agent': 'Mozilla/5.0'}


def fetch(url, params=None):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        return r.text
    except Exception as e:
        return None


def worldmonitor():
    url = 'https://www.worldmonitor.app/?view=global&timeRange=7d&layers=iranAttacks,conflicts,hormuz'
    html = fetch(url)
    if not html:
        return {'source': 'worldmonitor', 'error': 'fetch_failed'}
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    patterns = [
        r'Strait of Hormuz[^.]{0,120}',
        r'Iran[^.]{0,120}',
        r'U\.S\.-Iran[^.]{0,120}',
        r'Oil prices[^.]{0,120}',
        r'Conflict Zones[^.]{0,120}',
    ]
    snippets = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            snippet = m.group(0).strip()
            if len(snippet) > 20:
                snippets.append(snippet)
    snippets = snippets[:20]
    iran_status = 'elevated'
    if any('pause' in s.lower() or 'talks' in s.lower() for s in snippets):
        iran_status = 'pause_risk'
    return {
        'source': 'worldmonitor',
        'iran_status': iran_status,
        'snippets': snippets,
        'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
    }


def financialjuice():
    url = 'https://www.financialjuice.com/home'
    html = fetch(url)
    if not html:
        return {'source': 'financialjuice', 'error': 'fetch_failed'}
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for tr in soup.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 4:
            time_el = tds[0].get_text(strip=True)
            event_el = tds[1].get_text(strip=True)
            actual_el = tds[2].get_text(strip=True)
            forecast_el = tds[3].get_text(strip=True)
            if any(k in event_el.lower() for k in ['interest rate', 'cpi', 'gdp', 'durable goods', 'fomc', 'fed', 'employment', 'payroll', 'confidence', 'retail', 'trade balance', 'oil', 'gold']):
                rows.append({'time': time_el, 'event': event_el, 'actual': actual_el, 'forecast': forecast_el})
    return {
        'source': 'financialjuice',
        'high_impact_events': rows[:30],
        'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
    }


def lunarcrush_btc():
    url = 'https://api.lunarcrush.com/v2'
    params = {
        'data': 'assets',
        'symbol': 'BTC',
        'key': 'free',
        'fields': 'social_volume,social_dominance,galaxy_score,price',
    }
    text = fetch(url, params=params)
    if not text:
        return {'source': 'lunarcrush', 'error': 'fetch_failed'}
    try:
        data = json.loads(text)
        asset = data.get('data', [{}])[0]
        return {
            'source': 'lunarcrush',
            'symbol': asset.get('symbol'),
            'social_volume': asset.get('social_volume'),
            'social_dominance': asset.get('social_dominance'),
            'galaxy_score': asset.get('galaxy_score'),
            'price': asset.get('price'),
            'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
        }
    except Exception as e:
        return {'source': 'lunarcrush', 'error': str(e)}


def whale_wisdom():
    url = 'https://whalewisdom.com/'
    html = fetch(url)
    if not html:
        return {'source': 'whalewisdom', 'error': 'fetch_failed'}
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    managers = re.findall(r'([A-Z][a-z]+(?: [A-Z][a-z]+)+)[^0-9]{0,60}([A-Z]{2,5})', text)
    return {
        'source': 'whalewisdom',
        'sample_mentions': managers[:20],
        'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
    }


def polymarket():
    url = 'https://polymarket.com/'
    html = fetch(url)
    if not html:
        return {'source': 'polymarket', 'error': 'fetch_failed'}
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    matches = re.findall(r'([A-Z][a-z]+(?: [A-Z][a-z]+)+.*?)(\d{1,3})%', text)
    markets = []
    seen = set()
    for m in matches:
        label = m[0].strip()
        pct = m[1]
        if label and pct and label not in seen and any(k in label.lower() for k in ['iran', 'oil', 'bitcoin', 'btc', 'ethereum', 'eth', 'fed', 'rate', 'gold', 'war', 'ceasefire', 'recession']):
            seen.add(label)
            markets.append({'label': label, 'probability_pct': int(pct)})
    return {
        'source': 'polymarket',
        'markets': markets[:20],
        'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
    }


def main():
    results = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'sources': {
            'worldmonitor': worldmonitor(),
            'financialjuice': financialjuice(),
            'lunarcrush': lunarcrush_btc(),
            'whalewisdom': whale_wisdom(),
            'polymarket': polymarket(),
        },
    }
    OUT_PATH.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
