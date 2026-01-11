import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not set.")
    exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"

headers = {
    "Content-Type": "application/json"
}

data = {
    "contents": [{
        "parts": [{"text": "Hello, can you hear me?"}]
    }]
}

print(f"Sending REST request to {url.split('?')[0]}...")

try:
    response = requests.post(url, headers=headers, json=data, timeout=10)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print("Response received!")
        print(result)
        # print text
        print(result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", ""))
    else:
        print("Error response:")
        print(response.text)

except Exception as e:
    print(f"Exception: {e}")
