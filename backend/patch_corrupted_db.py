import os
from app.services.spam_rag_service import get_spam_rag_service

# Load env before using service
from dotenv import load_dotenv
load_dotenv(override=True)

def patch_corrupted_message():
    service = get_spam_rag_service()
    
    # 1. We know the corrupted original_message was empty or garbled, and it had a specific code
    examples = service.get_all_examples()
    
    target_example_id = None
    target_intent = None
    
    print(f"Total examples: {len(examples)}")
    for ex in examples:
        # Based on previous dump, the intent contained "ä 迡" and reason contained "지속적인 연락두절"
        reason = ex.get('reason', '')
        if "지속적인" in reason and "연락두절" in reason:
            target_example_id = ex['id']
            target_intent = ex['intent_summary']
            print(f"Found target example: {target_example_id}")
            print(f"Current reason: {reason}")
            print(f"Current message: {ex.get('message', '')}")
            print(f"Current intent: {target_intent}")
            break
            
    if not target_example_id:
        print("Could not find the target example based on reason.")
        return
        
    print(f"\nTarget ID to patch: {target_example_id}")
    
    # 2. Update with the correct Korean message
    correct_message = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
    
    result = service.update_example(
        example_id=target_example_id,
        message=correct_message
    )
    
    if result:
        print(f"\nSuccessfully patched message!")
        print(f"New message: {result.get('message')}")
    else:
        print("\nFailed to patch message.")
        
    # 3. Test if it's searchable now
    print("\nTesting search...")
    res = service.search_similar(target_intent, k=2)
    hits = res.get('hits', [])
    for hit in hits:
        print(f"Search Hit: [{hit['distance']:.4f}] {hit.get('message', '')}")

if __name__ == "__main__":
    patch_corrupted_message()
