import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

print(f"Loaded Key: {api_key[:8]}...****")

def test_chat_http():
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-5-mini",
        "messages": [{"role": "user", "content": "Hello via HTTP"}],
        "max_tokens": 5
    }
    
    print("\n[TEST] HTTP Request to v1/chat/completions...")
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"Status Code: {response.status_code}")
        print("Response Body:")
        print(response.text)
        
        if response.status_code == 429:
            print("\n[DIAGNOSIS] Server returned 429 Too Many Requests.")
            if "insufficient_quota" in response.text:
                print("Specific type: insufficient_quota (Billing issue)")
            else:
                print("Specific type: Rate limit exceeded")
                
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_chat_http()
