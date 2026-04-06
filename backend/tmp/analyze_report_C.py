import json
from collections import Counter
import sys

file_path = "c:/Users/leejo/Project/AI Agent/Spam Detector/data/reports/report-20260326_C.json"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception as e:
    print(f"Error reading file: {e}")
    sys.exit(1)

logs = data.get("logs", [])
total_msgs = len(logs)

# Stats
stats = {
    "total": total_msgs,
    "spam": 0,
    "ham": 0,
    "skip": 0,
    "type_b_overrides": 0,
    "url_agent_spams": 0,
    "covert_domains_extracted": 0,
    "interesting_cases": []
}

for log in logs:
    res = log.get("result", {})
    code = res.get("classification_code")
    is_spam = res.get("is_spam", False)
    
    if code == "SKIP":
        stats["skip"] += 1
        continue
        
    if is_spam:
        stats["spam"] += 1
    else:
        stats["ham"] += 1
        
    # Check Type B Overrides
    if "Override" in res.get("reason", "") or res.get("semantic_class", "").startswith("Type_B"):
        stats["type_b_overrides"] += 1
        
    # Check URL Agent
    url_res = res.get("url_result", {})
    if url_res and url_res.get("is_spam"):
        stats["url_agent_spams"] += 1
        
    # Check covert domains
    urls = res.get("obfuscated_urls", [])
    if urls:
        stats["covert_domains_extracted"] += len(urls)
        
    # Collect some interesting samples
    if urls and is_spam and len(stats["interesting_cases"]) < 10:
        stats["interesting_cases"].append({
            "row": log.get("excel_row_number"),
            "msg": log.get("message")[:60],
            "urls": urls,
            "reason": res.get("reason")[:120]
        })

print(f"Total Processed: {stats['total']}")
print(f"SPAM: {stats['spam']} | HAM: {stats['ham']} | SKIP: {stats['skip']}")
print(f"Type B Overrides (Protected/Isolated): {stats['type_b_overrides']}")
print(f"URL Agent Caught SPAM: {stats['url_agent_spams']}")
print(f"Covert Domains Extracted (# URLs): {stats['covert_domains_extracted']}")
print("\n[Sample Interesting Cases with Covert Domains]")
for case in stats['interesting_cases']:
    print(f"Row {case['row']}: {case['msg']}")
    print(f"  URLs: {case['urls']}")
    print(f"  Reason: {case['reason']}")
