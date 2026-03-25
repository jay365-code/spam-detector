import json

with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260322_B.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for log in data.get("logs", []):
    if log.get("excel_row_number") == 299 or "안전한운전" in log.get("message", ""):
        print(json.dumps(log, indent=2, ensure_ascii=False))
        break
