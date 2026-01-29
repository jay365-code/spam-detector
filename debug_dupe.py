import sys
import os
import time

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.fn_examples_service import get_fn_examples_service

def test_dupe():
    print("Initializing Service...")
    s = get_fn_examples_service()
    
    # Use a unique message to avoid clashing with existing data
    unique_marker = int(time.time())
    msg = f"중복 테스트 메시지입니다. {unique_marker}"
    
    print(f"\n[Step 1] Adding first message: '{msg}'")
    try:
        res = s.add_example(msg, "SPAM", "1", "테스트", "테스트")
        print(f"Result: {res}")
    except Exception as e:
        print(f"Error adding first: {e}")
        return

    print("\n[Step 2] Searching for the same message...")
    similar = s.search_similar(msg, k=3)
    print(f"Search Results: {similar}")
    if similar:
        print(f"Top 1 Score: {similar[0].get('score')}")
    else:
        print("No similar items found (weird).")

    print("\n[Step 3] Adding DUPLICATE message...")
    try:
        s.add_example(msg, "SPAM", "1", "테스트", "테스트")
        print("❌ FAIL: Duplicate was NOT caught! (It was saved again)")
    except ValueError as e:
        print(f"✅ PASS: Caught duplicate error: {e}")
    except Exception as e:
        print(f"❓ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_dupe()
