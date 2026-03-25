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
    
    url_violation_suspects = []
    
    for log in logs:
        msg = log.get('message', '')
        res = log.get('result', {})
        
        is_spam = res.get('is_spam')
        signals = res.get('signals', {})
        ibse_sig = res.get('ibse_signature')
        ibse_len = res.get('ibse_len', 0)
        
        # URL 룰 검증 
        # 추출된 시그니처가 20바이트 이하인데, bit.ly 나 youtube.com 등 도메인만 달랑 잘려있는 경우 탐지
        if is_spam and ibse_sig and ibse_len <= 20:
            lower_sig = ibse_sig.lower()
            if any(domain in lower_sig for domain in ["bit.ly", "me2.do", "youtube.com", "naver.com", "kakao.com", "coupa.ng"]):
                # if the signature is exactly or just slightly larger than the domain alone
                # wait, if they have the path appended (e.g. bit.ly/12345), it's fine, but if it ends inside the path or is just the domain
                url_violation_suspects.append((msg, ibse_sig, ibse_len))
                
        if not is_spam:
            ham_count += 1
            continue
            
        # Is SPAM
        type_b_signals = {k: v for k, v in signals.items() if k not in ['harm_anchor', 'route_or_cta'] and v is True}
        
        if len(type_b_signals) > 0:
            type_b_count += 1
        else:
            type_a_count += 1

    out = []
    out.append(f"Total Logs: {total}")
    out.append(f"HAM Count: {ham_count}")
    out.append(f"SPAM Count: {type_a_count + type_b_count}")
    out.append(f"  - Type A Count: {type_a_count}")
    out.append(f"  - Type B Count: {type_b_count}")
    
    out.append(f"\n--- [IBSE URL Rule Check] Suspected Partial URL Extractions (len <= 20): {len(url_violation_suspects)} ---")
    for s in url_violation_suspects:
        out.append(f"Signature: '{s[1]}' (len={s[2]})\nOriginal Text: {s[0][:100]}...\n")

    with open("scripts/analyze_result_23A.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    
    print("Analysis complete. Saved to scripts/analyze_result_23A.txt")

if __name__ == "__main__":
    report_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260323_A.json"
    analyze_report(report_path)
