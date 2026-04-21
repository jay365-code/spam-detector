import json

file_path = '/Users/jay/Projects/spam-detector/data/reports/report-20260420_C.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for log in data.get('logs', []):
    res = log.get('result', {})
    if res:
        url_result = res.get('url_result', {})
        reason = (url_result.get('reason', '') or '').lower()
        if not reason:
            reason = (res.get('reason', '') or '').lower()
            
        if '방패막이' in reason or '위장 url' in reason or '정상 도메인 위장' in reason or "safe url injection" in reason:
            if not res.get('drop_url'):
                res['drop_url'] = True
                res['drop_url_reason'] = 'safe_injection'
                # Update the log
                log['result'] = res

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("JSON patch completed!")
