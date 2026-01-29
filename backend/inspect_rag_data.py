
import requests
import json

def inspect_data():
    try:
        response = requests.get("http://localhost:8000/api/spam-rag")
        data = response.json()
        
        if data["success"]:
            examples = data["data"]
            print(f"Total examples: {len(examples)}")
            
            has_date_count = 0
            for ex in examples:
                created_at = ex.get("created_at")
                if created_at:
                    has_date_count += 1
                    print(f"ID: {ex.get('id')}, Date: {created_at}, Message: {ex.get('message')[:20]}...")
                else:
                    print(f"ID: {ex.get('id')}, Date: NONE, Message: {ex.get('message')[:20]}...")
            
            print(f"\nSummary: {has_date_count}/{len(examples)} items have created_at timestamp.")
        else:
            print("Failed to fetch data:", data)
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    inspect_data()
