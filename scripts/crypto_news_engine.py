#!/usr/bin/env python3
"""
CRYPTO NEWS ENGINE v1
---------------------
Pulls crypto news via RSS, clusters into themes using anchored regex,
extracts dollar figures, and diffs against previous run.

Output modes:
  normal    -> structured report to stdout
  quiet     -> prints nothing unless there is an alert/change
  json      -> prints full machine-readable JSON to stdout

State is stored in crypto_news_state.json next to this script.
"""

import json, re, sys, sqlite3, hashlib, os
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

try:
    import feedparser
except ImportError:
    raise SystemExit('feedparser required: pip install feedparser')

# ─── Configuration ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / 'crypto_news_state.json'
ARTICLES_DB = BASE_DIR / 'crypto_articles.db'

RSS_FEEDS = [
    ('coindesk', 'https://www.coindesk.com/arc/outboundfeeds/rss/'),
    ('cointelegraph', 'https://cointelegraph.com/rss'),
    ('decrypt', 'https://decrypt.co/feed'),
    ('theblock', 'https://www.theblock.co/rss.xml'),
    ('cryptoslate', 'https://cryptoslate.com/feed/'),
    ('bitcoinmagazine', 'https://bitcoinmagazine.com/feed/'),
]

# Anchored patterns — regex with \b and ^/$ where appropriate
# Format: theme_id -> {impact, action, urgency, patterns: [anchored regexes]}
THEMES = {
    'sanctions_regulatory': {
        'impact': 'BEARISH', 'action': 'REDUCE exposure', 'urgency': 'HIGH',
        'patterns': [
            r'\bsec\s+(?:charges|sues|investigates|actions|settlement)\b',
            r'\bregulatory\s+(?:crackdown|scrutiny|action|approval|rejection)\b',
            r'\bbanned\b',
            r'\bsanction(?:s|ed)?\b',
            r'\bofac\b',
            r'\bcbdc\b',
        ]
    },
    'stablecoin': {
        'impact': 'NEUTRAL', 'action': 'WATCH', 'urgency': 'MEDIUM',
        'patterns': [
            r'\busdt\b',
            r'\busdc\b',
            r'\bdai\b',
            r'\bterra(?:usd|luna)?\b',
            r'\bstablecoin\s+(?:regulation|depeg|issuance|reserve)\b',
        ]
    },
    'coldcard_exploit': {
        'impact': 'BEARISH', 'action': 'EXIT hardware-wallet exposure', 'urgency': 'HIGH',
        'patterns': [
            r'\bcoldcard\b',
            r'\bcoinkite\b',
            r'\bfirmware\s+(?:bug|vulnerability|flaw|issue)\b',
            r'\bhardware\s+wallet\s+(?:exploit|hack|vulnerability|breach)\b',
        ]
    },
    'upgrade_launch': {
        'impact': 'BULLISH', 'action': 'BUY', 'urgency': 'MEDIUM',
        'patterns': [
            r'\bupgrade(?:d|s)?\b',
            r'\blaunch(?:ed|ing)?\b',
            r'\bmainnet\s+(?:launch|live|online)\b',
            r'\bprotocol\s+(?:upgrade|upgrade)\b',
        ]
    },
    'exchange_hack': {
        'impact': 'BEARISH', 'action': 'EXIT exchange tokens', 'urgency': 'HIGH',
        'patterns': [
            r'\bexchange\s+(?:hack|exploit|breach|attack)\b',
            r'\bhacked\b',
            r'\bfunds\s+(?:drained|stolen|lost|compromised)\b',
            r'\bhot\s+wallet\s+(?:compromise|breach)\b',
        ]
    },
    'fed_macro': {
        'impact': 'NEUTRAL', 'action': 'ADJUST exposure', 'urgency': 'HIGH',
        'patterns': [
            r'\bfed\s+(?:rate|decision|meeting|minutes|chair)\b',
            r'\bcpi\s+(?:data|report|release)\b',
            r'\bnfp\b',
            r'\bfomc\b',
            r'\bfederal\s+reserve\s+(?:rate|decision|meeting)\b',
        ]
    },
    'etf_flows': {
        'impact': 'BULLISH', 'action': 'ACCUMULATE BTC/ETH', 'urgency': 'HIGH',
        'patterns': [
            r'\betf\s+(?:approved|launched|inflows|outflows|flows|net)\b',
            r'\bbitcoin\s+etf\b',
            r'\bethereum\s+etf\b',
            r'\bspot\s+etf\b',
        ]
    },
    'institutional_adopt': {
        'impact': 'BULLISH', 'action': 'BUY', 'urgency': 'MEDIUM',
        'patterns': [
            r'\binstitutional\s+(?:adoption|investment|interest|inflow)\b',
            r'\bhedge\s+fund\b',
            r'\bfamily\s+office\b',
            r'\bbank\s+(?:adoption|custody|offers)\b',
        ]
    },
    'quantum_security': {
        'impact': 'BEARISH', 'action': 'REDUCE exposure', 'urgency': 'MEDIUM',
        'patterns': [
            r'\bquantum\s+(?:threat|risk|computing|attack|resistance)\b',
            r'\bcryptography\s+(?:break|vulnerability|quantum)\b',
            r'\brsa\s+(?:break|vulnerable|quantum)\b',
            r'\bquantum\s+computer\s+(?:breaks|cracks|hacks)\b',
        ]
    },
}

# Dollar amount patterns: $1.2M, $800M, $130M, $88 billion, $1,234,567
DOLLAR_RE = re.compile(
    r'\$\s*(\d{1,3}(?:,\d{3})*|\d+\.?\d*)\s*(billion|million|thousand|b|m|k|t)?',
    re.IGNORECASE
)
MULT = {'billion': 1e9, 'b': 1e9, 'million': 1e6, 'm': 1e6, 'thousand': 1e3, 'k': 1e3, 't': 1e12}

# False-positive guardrails — even if regex matches, these are stop-words
NEGATION_RULES = [
    # "drug revenues" should NOT match "rug"
    (re.compile(r'\bdrug\b', re.IGNORECASE), ['sanctions_regulatory', 'stablecoin']),
    # "US Treasury sanctions" is already handled by exact anchored regex; just note
]

# ─── Helpers ─────────────────────────────────────────────────────────────────
def _outlet_from_url(url: str) -> str:
    m = re.match(r'https?://(?:www\.)?([^/]+)', url or '')
    return m.group(1).lower() if m else 'unknown'

def _parse_dollar(text: str):
    """Return list of floats found in text."""
    vals = []
    for m in DOLLAR_RE.finditer(text or ''):
        raw = m.group(1).replace(',', '')
        try:
            v = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or '').lower()
        v *= MULT.get(unit, 1)
        vals.append(round(v, 2))
    return vals

def _safe_max(vals):
    return max(vals) if vals else 0.0

def article_hash(title: str, outlet: str) -> str:
    return hashlib.sha1(f'{outlet}:{title}'.encode()).hexdigest()[:12]

# ─── DB ─────────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(str(ARTICLES_DB))
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            hash TEXT PRIMARY KEY,
            timestamp TEXT, outlet TEXT, title TEXT,
            summary TEXT, url TEXT, theme TEXT, dollars REAL
        )
    ''')
    conn.commit()
    conn.close()

def store_articles(items):
    init_db()
    conn = sqlite3.connect(str(ARTICLES_DB))
    c = conn.cursor()
    inserted = 0
    for it in items:
        try:
            c.execute('INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?,?,?)',
                (it['hash'], it['ts'], it['outlet'], it['title'],
                 it.get('summary',''), it['url'], it.get('theme',''), it.get('dollars',0)))
            inserted += c.rowcount
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted

# ─── Theme Classification ────────────────────────────────────────────────────
def classify(text: str):
    text_lc = text.lower()
    hits = []
    for tid, tdef in THEMES.items():
        for pat in tdef['patterns']:
            if re.search(pat, text_lc):
                hits.append(tid)
                break
    return hits

# ─── Fetch ───────────────────────────────────────────────────────────────────
def fetch_feeds():
    items = []
    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                continue
            for e in feed.entries[:40]:
                title = e.get('title', '')
                summary = e.get('summary', '') or e.get('description', '')
                raw_ts = e.get('published') or e.get('updated') or ''
                try:
                    dt = parsedate_to_datetime(raw_ts)
                    ts = dt.isoformat()
                except Exception:
                    ts = datetime.now(timezone.utc).isoformat()
                outlet = _outlet_from_url(e.get('link', ''))
                if not outlet:
                    outlet = source
                items.append({
                    'ts': ts,
                    'outlet': outlet,
                    'title': title,
                    'summary': summary,
                    'url': e.get('link', ''),
                })
        except Exception as exc:
            print(f'⚠ feed error {source}: {exc}', file=sys.stderr)
    return items

# ─── State ───────────────────────────────────────────────────────────────────
def load_state():
    if not STATE_FILE.exists():
        return {'runs': [], 'theme_history': {}}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {'runs': [], 'theme_history': {}}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ─── Diff Engine ─────────────────────────────────────────────────────────────
def diff_themes(current_counts, current_outlets, current_dollars, prev_state):
    """
    current_counts: {theme: headline_count}
    current_outlets: {theme: set of outlets}
    current_dollars: {theme: max_dollar}
    Returns list of alert dicts for NEW or ESCALATING themes.
    """
    prev = prev_state.get('theme_history', {})
    alerts = []
    for tid, count in current_counts.items():
        outlets = current_outlets.get(tid, set())
        dollars = current_dollars.get(tid, 0)
        entry = prev.get(tid, {})
        prev_count = entry.get('count', 0)
        prev_dollars = entry.get('dollars', 0)
        prev_outlets = set(entry.get('outlets', []))

        is_new = prev_count == 0 and count >= 2 and len(outlets) >= 2
        is_escalating = (
            prev_count > 0 and count >= 2 and len(outlets) >= 2 and
            (count - prev_count) / max(prev_count, 1) > 0.15
        )
        dollar_escalating = (
            prev_dollars > 0 and dollars > 0 and
            dollars / prev_dollars > 1.15
        )

        if is_new or is_escalating or dollar_escalating:
            reasons = []
            if is_new:
                reasons.append('NEW theme crossed threshold')
            if is_escalating:
                reasons.append(f'headlines jumped {prev_count}->{count}')
            if dollar_escalating:
                reasons.append(f'dollar figure grew ${prev_dollars:,.0f}->${dollars:,.0f}')
            alerts.append({
                'theme': tid,
                'impact': THEMES[tid]['impact'],
                'action': THEMES[tid]['action'],
                'urgency': THEMES[tid]['urgency'],
                'count': count,
                'outlets': sorted(outlets),
                'max_dollar': dollars,
                'reasons': reasons,
            })
    return alerts

# ─── Core ────────────────────────────────────────────────────────────────────
def run_pipeline(mode='normal'):
    articles = fetch_feeds()
    if not articles:
        if mode != 'quiet':
            print('No articles fetched.')
        return []

    # Classify
    theme_counts = {}
    theme_outlets = {}
    theme_dollars = {}
    classified = []

    for art in articles:
        text = f"{art['title']} {art.get('summary','')}"
        themes = classify(text)
        dollars = _safe_max(_parse_dollar(text))
        art['theme'] = themes[0] if themes else 'uncategorized'
        art['dollars'] = dollars
        art['hash'] = article_hash(art['title'], art['outlet'])
        classified.append(art)
        for t in themes:
            theme_counts[t] = theme_counts.get(t, 0) + 1
            theme_outlets.setdefault(t, set()).add(art['outlet'])
            theme_dollars[t] = max(theme_dollars.get(t, 0), dollars)

    # Persist raw articles
    store_articles(classified)

    # Diff against previous state
    prev = load_state()
    alerts = diff_themes(theme_counts, theme_outlets, theme_dollars, prev)

    # Build report
    sorted_themes = sorted(theme_counts.items(), key=lambda x: (-x[1], x[0]))
    tone_bear = sum(1 for t, _ in sorted_themes if THEMES.get(t, {}).get('impact') == 'BEARISH')
    tone_bull = sum(1 for t, _ in sorted_themes if THEMES.get(t, {}).get('impact') == 'BULLISH')
    if tone_bear > tone_bull:
        tone = 'RISK-OFF'
    elif tone_bull > tone_bear:
        tone = 'RISK-ON'
    else:
        tone = 'NEUTRAL'

    now_iso = datetime.now(timezone.utc).isoformat()
    report = {
        'generated': now_iso,
        'total_articles': len(classified),
        'unique_themes': len(theme_counts),
        'alerts': alerts,
        'tone': f'{tone} ({tone_bear} bearish vs {tone_bull} bullish)',
        'themes': []
    }
    for tid, count in sorted_themes:
        report['themes'].append({
            'theme': tid,
            'n': count,
            'outlets': len(theme_outlets.get(tid, set())),
            'impact': THEMES.get(tid, {}).get('impact', 'UNKNOWN'),
            'max_dollar': theme_dollars.get(tid, 0),
        })

    # Update state history
    th = prev.get('theme_history', {})
    for tid in theme_counts:
        th[tid] = {
            'count': theme_counts[tid],
            'outlets': sorted(theme_outlets.get(tid, set())),
            'dollars': theme_dollars.get(tid, 0),
            'last_seen': now_iso,
        }
    prev['theme_history'] = th
    prev['runs'].append({'ts': now_iso, 'articles': len(classified)})
    prev['runs'] = prev['runs'][-20:]  # keep last 20 runs
    save_state(prev)

    # Output
    if mode == 'json':
        print(json.dumps(report, indent=2))
    elif alerts or mode != 'quiet':
        _print_report(report)
    return report

def _print_report(r):
    print(f"\nCRYPTO NEWS ENGINE — {r['generated']}")
    print(f"Articles: {r['total_articles']} | Themes: {r['unique_themes']} | {r['tone']}\n")
    if r['alerts']:
        print('ALERTS:')
        for a in r['alerts']:
            print(f"  [{a['urgency']}] {a['theme']} — {', '.join(a['reasons'])}")
            print(f"    Impact: {a['impact']} | Action: {a['action']}")
            print(f"    n={a['count']} | outlets={a['outlets']} | max ${a['max_dollar']:,.0f}")
        print()
    print('CURRENT READ:')
    for t in r['themes']:
        dollar_str = f" ${t['max_dollar']:,.0f}" if t['max_dollar'] else ''
        print(f"  {t['theme']:<22} n={t['n']:>3}  {t['outlets']:>2} outlets  {t['impact']:<8}{dollar_str}")

# ─── Entry ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'normal'
    run_pipeline(mode)
