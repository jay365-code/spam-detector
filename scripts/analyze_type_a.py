import json
from collections import Counter

type_a_count = 0
category_counts = Counter()
samples = []

try:
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260321_A.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        total_logs = len(data.get("logs", []))
        
        for log in data.get("logs", []):
            res = log.get("result", {})
            semantic_class = res.get("semantic_class", "")
            
            if "Type_A" in str(semantic_class):
                type_a_count += 1
                msg = log.get("message", "")
                code = res.get("classification_code", "")
                reason = res.get("reason", "")
                
                category_counts[str(code)] += 1
                
                # Sample the first 40 examples
                if len(samples) < 40:
                    samples.append({
                        "id": type_a_count,
                        "code": code,
                        "msg": str(msg).strip().replace('\n', ' ')[:150] + "...",
                        "rsn": str(reason).replace('\n', ' ')[:150] + "..."
                    })

    out_data = {
        "Total_Logs": total_logs,
        "Total_Type_A": type_a_count,
        "Category_Distribution": dict(category_counts),
        "Samples": samples
    }
    
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\scripts\type_a_out.json", "w", encoding="utf-8") as outf:
        json.dump(out_data, outf, ensure_ascii=False, indent=2)

except Exception as e:
    print(f"Error: {e}")
