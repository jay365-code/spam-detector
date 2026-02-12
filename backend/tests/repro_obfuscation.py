
import sys
import os

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.rule_service import RuleBasedFilter

def test_obfuscation():
    rule_filter = RuleBasedFilter()
    
    # Test cases
    cases = [
        # 1. User reported example (should trigger obfuscation check)
        {
            "msg": "(ca) :OO/ O:OO o% 1 O BK74O",
            "expected_bypass": True,
            "desc": "User Example (Obfuscated)"
        },
        # 2. Normal English (should be Foreign Language HAM)
        {
            "msg": "Hello World, this is a test message with some numbers 123.",
            "expected_bypass": False, 
            "expected_code": "HAM-5",
            "desc": "Normal English"
        },
        # 3. Normal Korean (should be None or Korean Analysis)
        {
            "msg": "안녕하세요. 정상적인 한국어 메시지입니다.",
            "expected_bypass": False,
            "desc": "Normal Korean"
        },
         # 4. Heavy Obfuscation
        {
            "msg": "0l0l 8282 O1O1",
            "expected_bypass": True,
            "desc": "Heavy Obfuscation"
        }
    ]

    print(f"Threshold: {rule_filter.alphanumeric_obfuscation_threshold}")
    print("-" * 50)

    for case in cases:
        msg = case["msg"]
        ratio = rule_filter.get_obfuscation_ratio(msg)
        result = rule_filter.check(msg)
        
        is_bypass = result.get("detected_pattern") == "alphanumeric_obfuscation"
        
        print(f"Message: {msg[:30]}...")
        print(f"  Ratio: {ratio:.2f}")
        print(f"  Result Reason: {result.get('reason')}")
        print(f"  Result Code: {result.get('classification_code')}")
        print(f"  Bypassed HAM-5: {is_bypass}")
        
        if case["expected_bypass"]:
            if is_bypass:
                print("  ✅ PASS (Correctly detected obfuscation)")
            else:
                print("  ❌ FAIL (Failed to detect obfuscation)")
        else:
            if not is_bypass:
                 if "expected_code" in case:
                     if result.get("classification_code") == case["expected_code"]:
                         print(f"  ✅ PASS (Correctly classified as {case['expected_code']})")
                     else:
                         print(f"  ❌ FAIL (Expected {case['expected_code']}, got {result.get('classification_code')})")
                 else:
                     print("  ✅ PASS (Correctly proceeded without obfuscation trigger)")
            else:
                print("  ❌ FAIL (False Positive: Detected obfuscation incorrectly)")
        print("-" * 50)

if __name__ == "__main__":
    test_obfuscation()
