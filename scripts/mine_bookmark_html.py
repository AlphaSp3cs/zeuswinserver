#!/usr/bin/env python3
"""
Offline mining equation/notes extractor from Hashlabs/NiceHash bookmark pages HTML.
Save a bookmark page HTML under:
  C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/loads/hashlabs.html
  C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/loads/nicehash.html
and this will mine useful snippets for model calibration.
"""
import re, json
from pathlib import Path
OUT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/mining_equation_leads.json')
LEADS = []
for name in ['hashlabs.html','nicehash.html']:
    p = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/loads') / name
    if not p.exists():
        continue
    text = p.read_text(encoding='utf-8', errors='ignore')
    snippets = re.findall(r'(?i)((?:profit|revenue|earn|per\s*(?:th/s|hash|day)|break[- ]even|difficulty|btc\s*(?:price|reward)|kWh|rate|pool)[^<\n]{0,140})', text)
    seen=[]
    for s in snippets:
        s=' '.join(s.split())
        if s not in seen:
            seen.append(s)
    LEADS.append({'source':name,'count':len(seen),'snippets':seen[:200]})
OUT.write_text(json.dumps({'generated_at':__import__('datetime').datetime.now().isoformat(),'leads':LEADS}, indent=2), encoding='utf-8')
print('wrote',OUT,'sources',len(LEAD))
