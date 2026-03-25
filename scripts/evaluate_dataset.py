import json
from collections import Counter

target_file = r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260320_C.json"

try:
    with open(target_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
        type_a_list = []
        type_b_list = []
        classes = Counter()
        
        for log in data.get("logs", []):
            res = log.get("result", {})
            semantic_class = res.get("semantic_class", "MISSING")
            classes[semantic_class] += 1
            
            msg = log.get("message", "")
            signals = res.get("signals", {})
            active_signals = [k for k, v in signals.items() if v and k not in ('harm_anchor', 'route_or_cta')]
            
            if "Type_A" in str(semantic_class):
                type_a_list.append({"msg": str(msg).strip().replace('\n', ' ')})
            elif "Type_B" in str(semantic_class):
                type_b_list.append({
                    "msg": str(msg).strip().replace('\n', ' '),
                    "signals": active_signals
                })

        print("=== [데이터셋 요약] ===")
        print(f"분포: {dict(classes)}")
        print(f"총 Type A: {len(type_a_list)}건 / 총 Type B: {len(type_b_list)}건\n")
        
        print("=== [1] Type A 내 오분류(샌드위치/난독화) 의심 샘플 ===")
        for i, a in enumerate(type_a_list[:10]):
            print(f"[{i+1}] {a['msg'][:80]}...")
            
        print("\n=== [2] Type B 내 퓨어 스팸(Type A로 가야할) 유실 의심 샘플 ===")
        b_fp_count = 0
        for b in type_b_list:
            # 순수 스팸(도박/주식)인데 레이아웃이나 모호성 때문에 격리된 경우
            if b['signals'] == ['is_normal_layout'] or b['signals'] == ['is_vague_cta']:
                b_fp_count += 1
                if b_fp_count <= 10:
                    print(f"[유실-{b_fp_count}] {b['msg'][:80]}...")

        print("\n=== [종합 검증 결과 요약] ===")
        print(f"* 100% Type A에 오염 텍스트가 섞여있는지 확인: (위 Type A 샘플들 눈으로 확인 필요)")
        print(f"* Type A로 갔어야 할 고순도 스팸이 Type B에 격리된 낭비 건수: {b_fp_count}건")

except Exception as e:
    print(f"Error: {e}")
