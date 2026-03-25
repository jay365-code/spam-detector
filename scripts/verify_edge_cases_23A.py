import json

def extract_qa_cases():
    report_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260323_A.json"
    with open(report_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    logs = data.get('logs', [])
    
    cases = []
    counts = {"sandwich": 0, "obfuscation": 0, "pure_a": 0, "ibse_url": 0}
    
    for log in logs:
        msg = log.get('message', '')
        res = log.get('result', {})
        is_spam = res.get('is_spam')
        if not is_spam:
            continue
            
        signals = res.get('signals', {})
        ibse_sig = res.get('ibse_signature', '')
        ibse_len = res.get('ibse_len', 0)
        reason = res.get('reason', '')
        
        # 1. Sandwich Spam (is_normal_layout)
        if signals.get('is_normal_layout') and counts["sandwich"] < 3:
            cases.append(f"QA Case: 샌드위치 스팸 방어 (Type B)\n원문: {msg}\n판정 근거: {reason}\n시그널: {signals}\n")
            counts["sandwich"] += 1
            
        # 2. Obfuscation Spam
        if signals.get('is_garbage_obfuscation') and counts["obfuscation"] < 3:
            cases.append(f"QA Case: 극단적 난독화 텍스트 (Type B)\n원문: {msg}\n판정 근거: {reason}\n시그널: {signals}\n")
            counts["obfuscation"] += 1
            
        # 3. Pure Type A
        type_b_signals = {k: v for k, v in signals.items() if k not in ['harm_anchor', 'route_or_cta'] and v is True}
        if len(type_b_signals) == 0 and counts["pure_a"] < 2:
            cases.append(f"QA Case: 순수 고밀도 스팸 (Type A)\n원문: {msg}\n판정 근거: {reason}\n시그널: {signals}\n")
            counts["pure_a"] += 1
            
        # 4. IBSE Safety Extraction (URL in sentence)
        if ibse_sig and ibse_len > 25 and counts["ibse_url"] < 3:
            lower_sig = ibse_sig.lower()
            if any(h in lower_sig for h in ["http", "bit.ly", "me2.do", "youtube"]):
                cases.append(f"QA Case: IBSE URL 도메인 추출 방어 (문장 통째 추출)\n원문: {msg}\n파싱된 시그니처: {ibse_sig}\n시그니처 길이: {ibse_len}\n")
                counts["ibse_url"] += 1
                
        if all(c >= 2 for c in counts.values()):
            break

    with open("scripts/verify_out.txt", "w", encoding="utf-8") as outf:
        outf.write("\n\n".join(cases))

if __name__ == "__main__":
    extract_qa_cases()
