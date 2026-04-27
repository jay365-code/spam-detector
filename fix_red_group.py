import json
import sys

def fix_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    fixed_count = 0
    logs = data.get('logs', {})
    for key, log in logs.items():
        result = log.get('result', {})
        reason = result.get('reason', '')
        if reason and '[텍스트 HAM + 악성 URL 분리 감지' in reason and '[수동 Red Group 지정]' not in reason:
            if not result.get('red_group'):
                result['red_group'] = True
                fixed_count += 1
                print(f"Fixed item {key}")
                
    if fixed_count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Fixed {fixed_count} items in {filepath}")
    else:
        print(f"No items needed fixing in {filepath}")

fix_json('/Users/jay/Projects/spam-detector/data/reports/report-20260422_A.json')
