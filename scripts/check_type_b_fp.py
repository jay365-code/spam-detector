import json
try:
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260321_A.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        candidates = []
        for log in data.get("logs", []):
            res = log.get("result", {})
            if "Type_B" in str(res.get("semantic_class", "")):
                msg = log.get("message", "")
                signals = res.get("signals", {})
                if not signals.get("is_garbage_obfuscation") and not signals.get("is_personal_lure") and not signals.get("is_impersonation"):
                    candidates.append({
                        "signals": [k for k, v in signals.items() if v and k not in ('harm_anchor', 'route_or_cta')],
                        "msg": str(msg).strip().replace('\n', ' ')[:150]
                    })
        with open("scripts/type_b_fp.json", "w", encoding="utf-8") as out:
            json.dump({"total": len(candidates), "samples": candidates[:20]}, out, ensure_ascii=False, indent=2)
except Exception as e:
    print(e)
