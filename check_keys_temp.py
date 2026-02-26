import os
import requests
from dotenv import load_dotenv

load_dotenv('backend/.env')
keys_str = os.getenv('GEMINI_API_KEY', '')
keys = [k.strip() for k in keys_str.split(',') if k.strip()]
model_name = os.getenv('LLM_MODEL', 'gemini-3-flash-preview')

for i, key in enumerate(keys):
    masked = key[:10] + "..."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            print(f"Key {i} ({masked}): SUCCESS (Active & Ready)")
        elif res.status_code == 429:
            print(f"Key {i} ({masked}): HTTP 429 Quota Exhausted")
        else:
            msg = res.json().get('error', {}).get('message', '')[:100]
            print(f"Key {i} ({masked}): HTTP {res.status_code} -> Error: {msg}...")
    except Exception as e:
        print(f"Key {i} ({masked}): FAILED ({e})")
