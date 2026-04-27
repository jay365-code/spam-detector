import sys
import os

# backend 경로 추가
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.rule_service import RuleBasedFilter

def test_foreign_logic():
    filter = RuleBasedFilter()
    
    # 1. 오탐지 사례 (인증 코드) — 짧은 영어이므로 Content Agent로 전달
    msg_repro = "New + +@A Code: 623242 aun53."
    result_repro = filter.check(msg_repro)
    print(f"Test 1 (Repro): {msg_repro}")
    print(f"Result: {result_repro['is_spam']}, Classification: {result_repro.get('classification_code')}, Reason: {result_repro['reason']}")
    assert result_repro['is_spam'] is None, f"Expected None (pass to LLM), got {result_repro['is_spam']}"
    print("  ✅ PASS")
    
    # 2. 난독화 사례 (알파벳-숫자 혼용) — 여전히 즉시 SPAM
    msg_obf = "o1o-l234-S67B"
    result_obf = filter.check(msg_obf)
    print(f"\nTest 2 (Obfuscated): {msg_obf}")
    print(f"Result: {result_obf['is_spam']}, Classification: {result_obf.get('classification_code')}, Reason: {result_obf['reason']}")
    assert result_obf['is_spam'] is True, f"Expected True (SPAM), got {result_obf['is_spam']}"
    print("  ✅ PASS")
    
    # 3. 긴 영어 문장 — 이전에는 HAM-5, 이제는 Content Agent로 전달 (is_spam=None)
    msg_long = "Hello, this is a long enough English message that should be considered as a clean foreign language message because it has no Korean and is over forty characters."
    result_long = filter.check(msg_long)
    print(f"\nTest 3 (Long English): {msg_long}")
    print(f"Result: {result_long['is_spam']}, Classification: {result_long.get('classification_code')}, Reason: {result_long['reason']}")
    assert result_long['is_spam'] is None, f"Expected None (pass to LLM), got {result_long['is_spam']}"
    assert result_long.get('classification_code') is None, f"Expected no classification code, got {result_long.get('classification_code')}"
    print("  ✅ PASS")

    # 4. 중국어 메시지 — 이전에는 HAM-5, 이제는 Content Agent로 전달
    msg_chinese = "你好世界这是一个测试消息你好世界朋友们大家好"
    result_chinese = filter.check(msg_chinese)
    print(f"\nTest 4 (Chinese): {msg_chinese}")
    print(f"Result: {result_chinese['is_spam']}, Classification: {result_chinese.get('classification_code')}, Reason: {result_chinese['reason']}")
    assert result_chinese['is_spam'] is None, f"Expected None (pass to LLM), got {result_chinese['is_spam']}"
    print("  ✅ PASS")

    # 5. 한국어 정상 메시지 — 여전히 Content Agent로 전달 (변경 없음)
    msg_korean = "안녕하세요. 정상적인 한국어 메시지입니다."
    result_korean = filter.check(msg_korean)
    print(f"\nTest 5 (Korean): {msg_korean}")
    print(f"Result: {result_korean['is_spam']}, Classification: {result_korean.get('classification_code')}, Reason: {result_korean['reason']}")
    assert result_korean['is_spam'] is None, f"Expected None (pass to LLM), got {result_korean['is_spam']}"
    print("  ✅ PASS")

    print("\n" + "=" * 50)
    print("All tests passed! ✅")

if __name__ == "__main__":
    test_foreign_logic()
