
import os
import sys
import requests
import json
from datetime import datetime

# Adjust path to import app modules if needed, but using API is safer/easier
API_BASE = "http://localhost:8000"

def fix_timestamps():
    print("Fetching all examples...")
    try:
        response = requests.get(f"{API_BASE}/api/spam-rag")
        data = response.json()
        
        if not data["success"]:
            print("Failed to fetch data")
            return

        examples = data["data"]
        print(f"Found {len(examples)} examples.")
        
        updated_count = 0
        target_id = "rag_bcc1ed2f" # User identified this as the most recent
        
        # Default past date for existing items
        past_date = "2025-01-01T00:00:00"
        
        for ex in examples:
            ex_id = ex["id"]
            current_date = ex.get("created_at")
            
            new_date = None
            if not current_date:
                if ex_id == target_id:
                    new_date = datetime.now().isoformat()
                    print(f"Updating TARGET {ex_id} to NOW: {new_date}")
                else:
                    new_date = past_date
                    # print(f"Updating {ex_id} to PAST: {new_date}")
            
            if new_date:
                # Call Update API
                # We need to preserve other fields. update_spam_rag_example takes body.
                # However, the update API definition in main.py:
                # class SpamRagUpdate(BaseModel):
                #     message: str = None ...
                # It doesn't allow updating created_at directly publicly?
                # Wait, update_example in service PRESERVES metadata. It doesn't allow setting it via API arguments typically unless we exposed it.
                # Let's check main.py SpamRagUpdate model.
                pass

        # Since API might not expose created_at update, we might need to use internal service directly in this script.
        # This requires setting up the environment.
        pass

    except Exception as e:
        print(f"Error: {e}")

# Re-implementing using internal service to bypass API limitations on metadata update
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

sys.path.append(os.path.join(os.path.dirname(__file__)))
from app.services.spam_rag_service import get_spam_rag_service

def fix_data_internal():
    print("Initializing service...")
    service = get_spam_rag_service()
    db = service._get_db()
    collection = db._collection
    
    results = collection.get(include=["metadatas", "documents"])
    ids = results["ids"]
    metadatas = results["metadatas"]
    documents = results["documents"]
    
    print(f"Found {len(ids)} items in ChromaDB.")
    
    target_id = "rag_bcc1ed2f"
    past_date = "2025-01-01T00:00:00"
    
    updates_ids = []
    updates_metadatas = []
    
    for i, ex_id in enumerate(ids):
        meta = metadatas[i] if metadatas[i] else {}
        
        if "created_at" not in meta:
            if ex_id == target_id:
                meta["created_at"] = datetime.now().isoformat()
                print(f" -> Mark {ex_id} as NEW")
            else:
                meta["created_at"] = past_date
            
            updates_ids.append(ex_id)
            updates_metadatas.append(meta)
            
    if updates_ids:
        print(f"Updating {len(updates_ids)} items...")
        collection.update(ids=updates_ids, metadatas=updates_metadatas)
        print("Update complete.")
    else:
        print("No updates needed.")

def test_search():
    print("\nTesting Search...")
    query = "/A/B/.C b.2t* /,,u! ! *1/7~/ ~ /30 까지 A/B/C/.co/m*~"
    # Using the new query param format
    try:
        response = requests.get(f"{API_BASE}/api/spam-rag/search", params={"query": query, "k": 5})
        print(f"Search URL: {response.url}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            results = data.get("data", [])
            print(f"Found {len(results)} results.")
            for res in results:
                print(f" - {res['id']}: {res['score']}")
        else:
            print(response.text)
    except Exception as e:
        print(f"Search failed: {e}")

if __name__ == "__main__":
    fix_data_internal()
    test_search()
