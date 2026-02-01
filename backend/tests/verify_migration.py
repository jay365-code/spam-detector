import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from app.services.spam_rag_service import get_spam_rag_service

def verify_migration():
    print("Verifying ChromaDB Migration...")
    service = get_spam_rag_service()
    
    # Check collection name
    print(f"Service Collection Name: {service.collection_name}")
    if service.collection_name != "spam_rag_intent":
        print(f"FAILED: Collection name mismatch (Expected: spam_rag_intent, Got: {service.collection_name})")
        return

    # Check DB Connection
    db = service._get_db()
    print(f"DB Connected: {db}")
    
    # Check Collection stats
    stats = service.get_stats()
    print(f"Initial Stats: {stats}")
    
    # Basic Add/Search Test
    print("\nTesting Add/Search...")
    try:
        # Add Mock Example
        res = service.add_example(
            intent_summary="테스트 의도 요약",
            original_message="테스트 원본 메시지",
            label="SPAM",
            code="test",
            category="test_cat",
            reason="test_reason",
            metadata={"harm_anchor": True}
        )
        print(f"Add Result: {res['id']}")
        
        # Search
        search_res = service.search_similar("테스트 의도 요약")
        print("Search Result Contract:")
        print(f"Metric: {search_res.get('metric')}")
        print(f"Stats: {search_res.get('stats')}")
        print(f"Hits: {len(search_res.get('hits'))}")
        
        # Verify Contract Keys
        if "d1" in search_res["stats"] and "gap" in search_res["stats"]:
             print("PASSED: Search contract validation successful.")
        else:
             print("FAILED: Search contract missing keys.")

        # Cleanup
        service.delete_example(res['id'])
        print("Cleanup successful.")
        
    except Exception as e:
        print(f"FAILED: Operation error - {e}")

if __name__ == "__main__":
    verify_migration()
