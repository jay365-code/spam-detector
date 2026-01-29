
import os
import sys
from collections import defaultdict
from datetime import datetime

# Setup environment to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.services.spam_rag_service import get_spam_rag_service

def remove_duplicates(dry_run=True):
    print("Initializing service...")
    service = get_spam_rag_service()
    
    print("Fetching all examples...")
    examples = service.get_all_examples()
    print(f"Total examples: {len(examples)}")
    
    # Group by message content
    grouped = defaultdict(list)
    for ex in examples:
        msg = ex.get("message", "").strip()
        grouped[msg].append(ex)
    
    duplicates_found = 0
    deleted_count = 0
    
    print("\nChecking for duplicates...")
    for msg, items in grouped.items():
        if len(items) > 1:
            duplicates_found += 1
            print(f"\nDuplicate Group Found ({len(items)} items):")
            print(f"Message: {msg[:50]}...")
            
            # Sort by created_at desc (newest first). 
            # If created_at is missing, treat as old (empty string sorts before ISO dates)
            # We want to KEEP the newest one.
            items.sort(key=lambda x: x.get("created_at", "") or "", reverse=True)
            
            keep = items[0]
            remove_list = items[1:]
            
            print(f"  [KEEP] ID: {keep['id']}, Created: {keep.get('created_at')}")
            
            for rm in remove_list:
                print(f"  [DELETE] ID: {rm['id']}, Created: {rm.get('created_at')}")
                if not dry_run:
                    service.delete_example(rm['id'])
                    deleted_count += 1
    
    print("\n" + "="*30)
    print(f"Total duplicate groups: {duplicates_found}")
    if dry_run:
        print(f"Dry run complete. Found {len(examples)} items. {duplicates_found} groups would be cleaned up.")
        print("To verify and delete, run with dry_run=False inside the script or request me to run it.")
    else:
        print(f"Cleanup complete. Deleted {deleted_count} duplicate items.")

if __name__ == "__main__":
    # You can change this manually or I will call it with specific arg if I implement arg parser.
    # For now, let's just use a simple check or run it twice.
    import sys
    is_dry_run = "--run" not in sys.argv
    remove_duplicates(dry_run=is_dry_run)
