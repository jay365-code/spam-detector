import json

try:
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260321_A.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
        candidates = []
        
        for log in data.get("logs", []):
            res = log.get("result", {})
            semantic_class = res.get("semantic_class", "")
            
            if "Type_B" in str(semantic_class):
                msg = log.get("message", "")
                reason = res.get("reason", "")
                signals = res.get("signals", {})
                
                # Check for is_normal_layout or is_vague_cta where it might actually be a pure spam
                # e.g., NO obfuscation, NO personal lure
                if not signals.get("is_garbage_obfuscation") and not signals.get("is_personal_lure"):
                    candidates.append({
                        "signals": [k for k, v in signals.items() if v and k not in ('harm_anchor', 'route_or_cta')],
                        "msg": str(msg).strip().replace('\n', ' '),
                    })
        
        print(f"Total pure-looking Type B candidates: {len(candidates)}")
        print("\n--- Potential Type A lying in Type B ---")
        for i, c in enumerate(candidates[:20]):
            print(f"[{i+1}] Signals: {c['signals']}")
            print(f"Msg: {c['msg'][:150]}")
            print("-" * 60)

except Exception as e:
    print(f"Error: {e}")
