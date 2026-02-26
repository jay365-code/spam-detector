import json
import requests

API_URL = "http://127.0.0.1:8000/api/spam-rag"

def patch_target():
    with open("backend/all_rag_examples.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    examples = data.get('data', [])
    target = None
    
    for ex in examples:
        msg = ex.get('message', '')
        orig = ex.get('original_message', '')
        
        # Check for the Cyrillic letter Ӽ or FFFD or similar short garbled strings
        # We know from check_old_db_deep.py that the original message was "Ӽ   "
        if msg.startswith('\u04fc') or orig.startswith('\u04fc'):
            target = ex
            break
            
    if not target:
        # Fallback: find it by looking for the one with label SPAM and very short length and not ascii
        for ex in examples:
            msg = ex.get('message', '')
            if ex.get('label') == 'SPAM' and len(msg) < 10 and ord(msg[0]) > 127:
                target = ex
                print("Found via fallback logic.")
                break

    if not target:
        print("Target not found.")
        return
        
    print(f"Target ID: {target['id']}")
    
    # Patch data
    update_url = f"{API_URL}/{target['id']}"
    correct_message = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
    
    payload = {
        "message": correct_message,
        # Re-apply other fields just in case if needed, but endpoint supports partial update
    }
    
    res = requests.put(update_url, json=payload)
    res.raise_for_status()
    
    print("\nSuccessfully patched via API!")
    
    # Test search
    print("\nTesting search...")
    search_res = requests.get(f"{API_URL}/search", params={"query": correct_message, "k": 1})
    search_data = search_res.json()
    for hit in search_data.get('data', {}).get('hits', []):
        print(f"[{hit.get('distance', 9.9):.4f}] {hit.get('message')}")

if __name__ == "__main__":
    patch_target()
