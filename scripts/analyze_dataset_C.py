import json
import os

def analyze_report(file_path):
    print(f"=== Analyzing {file_path} ===")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    logs = data.get('logs', [])
    
    total = len(logs)
    ham_count = 0
    type_a_count = 0
    type_b_count = 0
    
    type_b_normal_layout_samples = []
    type_b_obfuscation_samples = []
    type_a_samples = []
    hybrid_ham_samples = []
    
    for log in logs:
        msg = log.get('message', '')
        res = log.get('result', {})
        
        is_spam = res.get('is_spam')
        signals = res.get('signals', {})
        
        if not is_spam:
            ham_count += 1
            if len(hybrid_ham_samples) < 2 and msg and "광고" in msg: 
                hybrid_ham_samples.append(msg)
            continue
            
        # Is SPAM
        # Exclude harm_anchor and route_or_cta which are spam determinants, not Type B triggers
        type_b_signals = {k: v for k, v in signals.items() if k not in ['harm_anchor', 'route_or_cta'] and v is True}
        
        if len(type_b_signals) > 0:
            type_b_count += 1
            if signals.get('is_normal_layout', False) and len(type_b_normal_layout_samples) < 3:
                type_b_normal_layout_samples.append((msg, list(type_b_signals.keys()), res.get('reason')))
            if signals.get('is_garbage_obfuscation', False) and len(type_b_obfuscation_samples) < 3:
                type_b_obfuscation_samples.append((msg, list(type_b_signals.keys()), res.get('reason')))
        else:
            type_a_count += 1
            if len(type_a_samples) < 3:
                type_a_samples.append((msg, res.get('reason')))

    out = []
    out.append(f"Total Logs: {total}")
    out.append(f"HAM Count: {ham_count}")
    out.append(f"SPAM Count: {type_a_count + type_b_count}")
    out.append(f"  - Type A Count: {type_a_count}")
    out.append(f"  - Type B Count: {type_b_count}")
    
    out.append("\n--- [Rule 1: Sandwich Defense] Type B (is_normal_layout) Samples ---")
    for s in type_b_normal_layout_samples:
        out.append(f"Text: {s[0][:100]}...\nSignals: {s[1]}\nReason: {s[2]}\n")

    out.append("\n--- [Rule 3: Obfuscation Defense] Type B (is_garbage_obfuscation) Samples ---")
    for s in type_b_obfuscation_samples:
        out.append(f"Text: {s[0][:100]}...\nSignals: {s[1]}\nReason: {s[2]}\n")
        
    out.append("\n--- [Rule 2,4: Pure Spams] Type A Samples ---")
    for s in type_a_samples:
        out.append(f"Text: {s[0][:100]}...\nReason: {s[1]}\n")

    with open("scripts/analyze_result_22C.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))

if __name__ == "__main__":
    report_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260322_C.json"
    analyze_report(report_path)
