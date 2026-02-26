import requests

API_URL = "http://127.0.0.1:8000/api/spam-rag"

def recreate_target():
    correct_message = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
    
    # 1. Fetch all and delete any existing duplicates
    try:
        response = requests.get(API_URL)
        data = response.json()
        examples = data.get('data', [])
        for ex in examples:
            if ex.get('message') == correct_message or ex.get('original_message') == correct_message:
                del_url = f"{API_URL}/{ex['id']}"
                requests.delete(del_url)
    except Exception as e:
        pass

    # 2. Add the completely new one
    payload = {
        "message": correct_message,
        "label": "SPAM",
        "code": "8",
        "category": "기타 스팸 (Others)",
        "reason": "사기/연락두절 (사용자수동입력)"
    }
    
    try:
        create_res = requests.post(API_URL, json=payload)
        create_res.raise_for_status()
        new_data = create_res.json()
        with open("recreate_log.txt", "w", encoding="utf-8") as f:
            f.write(f"Created new ID: {new_data['data']['id']}\n")
            f.write(f"New Intent: {new_data['data']['intent_summary']}\n")
    except Exception as e:
        with open("recreate_log.txt", "w", encoding="utf-8") as f:
            f.write(f"Error creating: {e}\n")
        return
        
    # 3. Test Search
    try:
        search_res = requests.get(f"{API_URL}/search", params={"query": correct_message, "k": 2})
        search_data = search_res.json()
        with open("recreate_log.txt", "a", encoding="utf-8") as f:
            f.write("Search Results:\n")
            for hit in search_data.get('data', {}).get('hits', []):
                f.write(f"[{hit.get('distance', 9.9):.4f}] {hit.get('message')}\n")
    except Exception as e:
        pass

if __name__ == "__main__":
    recreate_target()
