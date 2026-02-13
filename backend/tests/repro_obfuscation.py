
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
        },
        # 5. User reported: Garbled text + obfuscated URL (should bypass Foreign Language Auto HAM)
        {
            "msg": "????? ?????????????????????????????https://v????.im/flrvl2...",
            "expected_bypass": True,
            "expected_not_ham5": True,
            "desc": "Garbled + obfuscated URL spam"
        },
        # 6. Normal English with URL (should stay HAM-5, no garbled pattern)
        {
            "msg": "Check out this link https://example.com/page",
            "expected_bypass": False,
            "expected_code": "HAM-5",
            "desc": "Normal English with clean URL"
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
            # Bypass = not Auto HAM-5 (passed to analysis)
            passed_to_analysis = result.get("is_spam") is None
            if "expected_not_ham5" in case and case["expected_not_ham5"]:
                ok = passed_to_analysis and result.get("classification_code") != "HAM-5"
            else:
                ok = is_bypass or passed_to_analysis
            if ok:
                print("  ✅ PASS (Correctly bypassed to analysis / detected obfuscation)")
            else:
                print("  ❌ FAIL (Failed to bypass - got Auto HAM or wrong path)")
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
