import json

with open('../data/reports/report-20260420_A.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

logs = data.get('logs', {})
target_logs = []
for key, log in logs.items():
    msg = log.get('message', '')
    if '꽃처럼 환한 미소가' in msg:
        target_logs.append((key, log))

print(f"Found {len(target_logs)} logs with the target text.")
for i, (key, log) in enumerate(target_logs[:5]):
    res = log.get('result', {})
    is_spam = res.get('is_spam')
    ibse = res.get('ibse_signature')
    print(f"[{i}] ID: {key}")
    print(f"  - is_spam: {is_spam}")
    print(f"  - ibse_signature: {ibse}")
    print(f"  - categories: {res.get('ibse_category', '')}")
