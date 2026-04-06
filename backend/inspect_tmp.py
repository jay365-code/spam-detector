import json

def inspect_json():
    with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260101_A.json', 'r', encoding='utf-8') as f:
        d = json.load(f)
        logs = d.get('logs', [])
    
    with open('inspect_all.txt', 'w', encoding='utf-8') as out:
        out.write(f'Total Len: {len(logs)}\n')
        for i in range(len(logs)):
            if logs[i] is None:
                out.write(f'[{i}] NULL\n')
                continue
            
            msg = logs[i].get("message", "")[:20].replace('\n', ' ')
            is_trap = logs[i].get("is_trap")
            row = logs[i].get("excel_row_number")
            typ = "TRAP" if is_trap else "KISA"
            out.write(f'[{i}] row={row} type={typ} msg={msg}\n')

if __name__ == '__main__':
    inspect_json()
