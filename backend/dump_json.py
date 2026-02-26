import requests
import json

API_URL = "http://127.0.0.1:8000/api/spam-rag"

def dump_all():
    response = requests.get(API_URL)
    data = response.json()
    with open("backend/all_rag_examples.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Dumped to backend/all_rag_examples.json")

if __name__ == "__main__":
    dump_all()
