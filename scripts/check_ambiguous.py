import json

with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260322_B.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# If data is a list, use it directly.
logs = data if isinstance(data, list) else data.get("logs", [])

ambiguous_samples = []

for log in logs:
    msg = log.get("message", "").replace("\n", " ")
    res = log.get("result", log) # Fallback to log if result not present
    
    is_spam = res.get("is_spam")
    prob = res.get("spam_probability", 0.0)
    reason = res.get("reason", "")
    semantic_class = str(res.get("semantic_class", ""))
    
    # 1. Ambiguous 1: Spam but prob < 0.85
    if is_spam and prob < 0.85:
        ambiguous_samples.append((msg, reason, prob, semantic_class, "Low Confidence SPAM"))
        
    # 2. Ambiguous 2: Ham but prob >= 0.5 and NOT an Override
    if not is_spam and prob >= 0.5 and "Override" not in reason:
        ambiguous_samples.append((msg, reason, prob, semantic_class, "High Confidence HAM (No Override)"))
        
    # 3. Explicit Uncertainty in reason, but ONLY if it's Type A (Type B we don't care as much)
    if is_spam and semantic_class == "Type_A" and ("애매" in reason or "판단하기 어렵" in reason or "불확실" in reason):
        ambiguous_samples.append((msg, reason, prob, semantic_class, "Uncertainty in Reason for Type A"))
        
    # 4. Type A but very short or no keywords
    # If the message is < 30 chars and it's Type A
    if is_spam and semantic_class == "Type_A" and len(msg) < 40:
        ambiguous_samples.append((msg, reason, prob, semantic_class, "Short Type A"))

with open("out.txt", "w", encoding="utf-8") as out:
    out.write(f"Total Ambiguous Cases Found: {len(ambiguous_samples)}\n")
    for i, (m, r, p, s, t) in enumerate(ambiguous_samples):
        out.write(f"[{i+1}. {t}] (Class: {s}, Prob: {p})\nMsg: {m}\nReason: {r}\n\n")

