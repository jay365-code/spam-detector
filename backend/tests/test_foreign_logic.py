import sys
import os

# backend 경로 추가
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.rule_service import RuleBasedFilter

def test_foreign_logic():
    filter = RuleBasedFilter()
    
    # 1. 오탐지 사례 (인증 코드)
    msg_repro = "New + +@A Code: 623242 aun53."
    result_repro = filter.check(msg_repro)
    print(f"Test 1 (Repro): {msg_repro}")
    print(f"Result: {result_repro['is_spam']}, Classification: {result_repro.get('classification_code')}, Reason: {result_repro['reason']}")
    
    # 2. 난독화 사례 (알파벳-숫자 혼용)
    msg_obf = "o1o-l234-S67B"
    result_obf = filter.check(msg_obf)
    print(f"\nTest 2 (Obfuscated): {msg_obf}")
    print(f"Result: {result_obf['is_spam']}, Classification: {result_obf.get('classification_code')}, Reason: {result_obf['reason']}")
    
    # 3. 긴 영어 문장 (정상 외국어)
    msg_long = "Hello, this is a long enough English message that should be considered as a clean foreign language message because it has no Korean and is over forty characters."
    result_long = filter.check(msg_long)
    print(f"\nTest 3 (Long English): {msg_long}")
    print(f"Result: {result_long['is_spam']}, Classification: {result_long.get('classification_code')}, Reason: {result_long['reason']}")

if __name__ == "__main__":
    test_foreign_logic()
