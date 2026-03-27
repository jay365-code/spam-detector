import json

file_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260326_B.json"
out_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\backend\tmp\analysis_result.txt"

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

logs = data.get("logs", [])

total = len(logs)
spam_count = 0
ham_count = 0
skip_count = 0

reading_room_cases = []
post_office_cases = []

for log in logs:
    msg = log.get("message", "")
    res = log.get("result", {})
    is_spam = res.get("is_spam", False)
    code = res.get("classification_code", "")
    reason = res.get("reason", "")
    url_res = res.get("url_result", {})
    url_reason = url_res.get("reason", "")
    
    # Check if URL Agent flipped it
    url_spam = url_res.get("is_spam", False)
    
    if code == "SKIP":
        skip_count += 1
        continue
        
    if is_spam:
        spam_count += 1
    else:
        ham_count += 1
        
    # Check for Reading Room cases (by keywords)
    if "투자의견" in msg or "수익" in msg or "상한가" in msg or "카톡채널" in msg or "문서보기" in msg:
        if "리딩" in reason or "도박" in reason or "VIP" in reason or "제0원칙" in reason or "제0원칙" in url_reason:
            reading_room_cases.append({"msg": msg, "is_spam": is_spam, "reason": reason, "url_reason": url_reason})
            
    # Check for Post Office Courier 010 cases
    if "우체국" in msg and "010" in msg:
        post_office_cases.append({"msg": msg, "is_spam": is_spam, "reason": reason})

with open(out_path, "w", encoding="utf-8") as f:
    f.write(f"Total: {total}, SPAM: {spam_count}, HAM: {ham_count}, SKIP: {skip_count}\n")
    
    f.write(f"\n--- Post Office Cases ({len(post_office_cases)}) ---\n")
    for c in post_office_cases[:5]:
        status = "SPAM" if c["is_spam"] else "HAM"
        f.write(f"[{status}] MSG: {c['msg'][:80]}... \n  REASON: {c['reason']}\n\n")

    f.write(f"\n--- Reading Room Cases ({len(reading_room_cases)}) ---\n")
    ham_reading = [c for c in reading_room_cases if not c["is_spam"]]
    spam_reading = [c for c in reading_room_cases if c["is_spam"]]
    f.write(f"SPAM: {len(spam_reading)}, HAM: {len(ham_reading)}\n")

    f.write("\n[HAM Reading Room Examples (Should be 0 unless official)]\n")
    for c in ham_reading[:3]:
        f.write(f"MSG: {c['msg'][:80]}... \n  REASON: {c['reason']}\n\n")

    f.write("\n[SPAM Reading Room Examples]\n")
    for c in spam_reading[:3]:
        f.write(f"MSG: {c['msg'][:80]}... \n  REASON: {c['reason']}\n  URL REASON: {c['url_reason']}\n\n")
