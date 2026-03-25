import json
from collections import Counter

type_b_count = 0
signal_counts = Counter()
samples = []
total_logs = 0

try:
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260321_A.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        logs = data.get("logs", [])
        total_logs = len(logs)
        
        for log in logs:
            res = log.get("result", {})
            semantic_class = res.get("semantic_class", "")
            
            if "Type_B" in str(semantic_class):
                type_b_count += 1
                msg = log.get("message", "")
                reason = res.get("reason", "")
                
                signals = res.get("signals", {})
                active_signals = [k for k, v in signals.items() if v and k not in ('harm_anchor', 'route_or_cta')]
                
                for s in active_signals:
                    signal_counts[s] += 1
                
                if len(samples) < 20:
                    samples.append({
                        "id": type_b_count,
                        "signals": active_signals,
                        "msg": str(msg).strip().replace('\n', ' ')[:100],
                        "rsn": str(reason).replace('\n', ' ')[:100]
                    })

    out_data = {
        "Total_Logs": total_logs,
        "Total_Type_B": type_b_count,
        "Signals_Distribution": dict(signal_counts),
        "Samples": samples
    }
    
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\scripts\type_b_out.json", "w", encoding="utf-8") as outf:
        json.dump(out_data, outf, ensure_ascii=False, indent=2)

except Exception as e:
    print(f"Error: {e}")
