import json
import sys

file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260327_A.json'
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception as e:
    print(e)
    sys.exit(1)

logs = data.get('logs', [])
lines = []

for item in logs:
    if not isinstance(item, dict): continue
    res = item.get('result') or {}
    reason = res.get('reason', '')
    if '강제격리' in reason or '분리 감지' in reason:
        lines.append('==================')
        lines.append('Row: ' + str(item.get('excel_row_number')))
        lines.append('Text: ' + repr(item.get('message', '')[:100]))
        
        c_res = res.get('content_result') or {}
        lines.append('C_is_spam: ' + str(c_res.get('is_spam')))
        lines.append('C_Reason: ' + repr(c_res.get('reason')))
        lines.append('Signals: ' + str(c_res.get('signals')))
        
        u_res = res.get('url_result', {})
        if u_res is None:
            u_res = {}
        lines.append('url_is_spam: ' + str(u_res.get('is_spam')))
        lines.append('Final Reason: ' + repr(reason))

with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\tmp_red_group.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
