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

        b_fp = []
        for b in type_b_list:
            if b['signals'] == ['is_normal_layout'] or b['signals'] == ['is_vague_cta']:
                b_fp.append(b['msg'][:100])

        out = {
            "distribution": dict(classes),
            "type_a_count": len(type_a_list),
            "type_b_count": len(type_b_list),
            "type_a_samples": [a['msg'][:100] for a in type_a_list[:15]],
            "type_b_fp_count": len(b_fp),
            "type_b_fp_samples": b_fp[:10]
        }
        with open("scripts/eval_out.json", "w", encoding="utf-8") as outf:
            json.dump(out, outf, ensure_ascii=False, indent=2)

except Exception as e:
    pass
