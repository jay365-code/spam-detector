import json
from collections import Counter

try:
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260321_A.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        classes = Counter()
        for log in data.get("logs", []):
            cls = log.get("result", {}).get("semantic_class", "MISSING")
            classes[cls] += 1
        print(classes)
except Exception as e:
    print(e)
