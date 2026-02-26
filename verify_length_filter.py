
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.rule_service import RuleBasedFilter

def test_length_filter():
    print("Testing RuleBasedFilter length check mod...")
    rbf = RuleBasedFilter()
    rbf.min_message_length = 10 # Force min length 10
    
    test_cases = [
        ("123", "SKIP"), # Short, No Korean
        ("abc", "SKIP"), # Short, No Korean
        ("꾸움", "PASS"), # Short, Has Korean (Should PASS now)
        ("카지노", "PASS"), # Short, Has Korean
        ("hello world", "PASS"), # Long, No Korean
        ("안녕하세요 반갑습니다", "PASS"), # Long, Has Korean
        ("!!!", "SKIP"), # Short, Special chars only (No Korean)
    ]
    
    all_passed = True
    
    for msg, expected in test_cases:
        result = rbf.check(msg)
        is_skipped = result.get("classification_code") == "SKIP"
        status = "SKIP" if is_skipped else "PASS"
        
        print(f"Msg: '{msg}' (len={len(msg)}) -> Result: {status} (Expected: {expected})")
        
        if status != expected:
            print(f"FAILED: Expected {expected} but got {status}")
            all_passed = False
            
    if all_passed:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed.")

if __name__ == "__main__":
    test_length_filter()
