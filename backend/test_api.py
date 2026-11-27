# -*- coding: utf-8 -*-
import sys, io, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def q(body):
    req = urllib.request.Request('http://127.0.0.1:8000/api/query',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req).read())

base = {'year': 2025, 'score': 560, 'first': '物理', 'reselect': ['化学', '生物'], 'limit': 100}

for name, ov in [
    ('均衡冲稳保 ±15', {'band': 'all', 'margin': 15}),
    ('分差 ±30', {'band': 'all', 'margin': 30}),
    ('排除中外合作', {'band': 'all', 'margin': 15, 'exclude_coop': True}),
]:
    b = dict(base); b.update(ov)
    r = q(b)
    items = r['items']
    from collections import Counter
    shown = Counter(i['band'] for i in items)
    coop = sum(1 for i in items if i['is_coop'])
    print(f'--- {name} ---')
    print(f"  total={r['total']} returned={r['returned']} 全量档位={r['band_count']} 本次展示档位={dict(shown)} 其中中外合作={coop}")
    for it in items[:3]:
        print(f"    [{it['band']}] {it['school']} {it['major']} {it['min_score']}分/分差{it['diff']} coop={it['is_coop']}")
    print('    ... 末尾:')
    for it in items[-3:]:
        print(f"    [{it['band']}] {it['school']} {it['major']} {it['min_score']}分/分差{it['diff']} coop={it['is_coop']}")
