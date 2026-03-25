import json

target_texts = [
    "3월 신규 회원 스페셜",
    "울산 남구 1차2차",
    "주말 두배 드려요",
    "제재X 롤100%",
    "최근 시장은 지수",
    "목요일이네요 십오퍼",
    "상한가 직전 종목",
    "상승률 +",
    "이건 아니지 않습니까",
    "정품비닉스",
    "필요한게 30 정도라면"
]

try:
    with open(r"c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\report-20260321_A.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        for target in target_texts:
            found = False
            for log in data.get("logs", []):
                msg = log.get("message", "")
                if target in msg:
                    res = log.get("result", {})
                    semantic_class = res.get("semantic_class", "")
                    signals = res.get("signals", {})
                    print(f"[{target}]")
                    print(f" Category Code: {res.get('classification_code')}")
                    print(f" Semantic Class: {semantic_class}")
                    
                    true_signals = [k for k, v in signals.items() if v]
                    print(f" Active Signals: {true_signals}")
                    print("-" * 60)
                    found = True
                    break
            if not found:
                print(f"[{target}] -> Not Found")
                print("-" * 60)
except Exception as e:
    print(f"Error: {e}")
