
import sys
import os
import asyncio
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
load_dotenv(override=True)

from app.core.logging_config import setup_logging
setup_logging()

from app.agents.content_agent.agent import ContentAnalysisAgent
from app.services.spam_rag_service import get_spam_rag_service

async def verify_functional():
    print("\n=== Functional Verification: Intent RAG ===\n")
    agent = ContentAnalysisAgent()
    service = get_spam_rag_service()
    
    # 1. Test Intent Summary Generation
    print("[1] Testing Intent Summary Generation...")
    raw_msg = "무서류 300 가능 카톡 id: loan1234"
    summary = agent.generate_intent_summary(raw_msg) # Sync call now
    print(f"Original: {raw_msg}")
    print(f"Summary:  {summary}")
    
    if "loan" in summary.lower() or "대출" in summary:
        print(">> PASS: Summary captured intent.")
    else:
        print(">> WARNING: Summary might be off.")

    # 2. Add Example to RAG (Simulate API)
    print("\n[2] Adding Example to RAG...")
    try:
        res = service.add_example(
            intent_summary=summary,
            original_message=raw_msg,
            label="SPAM",
            code="1",
            category="Test",
            reason="Test Reason",
            metadata={"harm_anchor": True}  # Hard Gate Trigger
        )
        example_id = res['id']
        print(f">> PASS: Added example {example_id}")
    except ValueError as e:
        print(f">> SKIP: Example already exists ({e})")
        example_id = None # Need to find it if exists? For now assume fresh or skip.

    # 3. Test Retrieval with Obfuscated Input
    print("\n[3] Testing Retrieval with Obfuscated Input...")
    obfuscated_msg = "무.서.류 3/0/0 가.능 (카)톡"
    
    # Analyze needs to generate summary for this obfuscated msg first
    obfuscated_summary = agent.generate_intent_summary(obfuscated_msg)
    print(f"Obfuscated Msg: {obfuscated_msg}")
    print(f"Obfuscated Summary: {obfuscated_summary}")
    
    # Search
    hits = service.search_similar(obfuscated_summary, k=3)
    # Check if our example is found
    found = False
    hits_list = hits.get('hits', []) # search_similar returns dict now
    for hit in hits_list:     
        if hit.get('original_message') == raw_msg:
            found = True
            print(f">> Found Match! Dist: {hit.get('distance', 0):.4f}")
            break
            
    if found:
        print(">> PASS: Obfuscated input matched original intent.")
    else:
        print(">> FAIL: Obfuscated input did not match.")
        
    # 4. Cleanup
    if example_id:
        service.delete_example(example_id)
        print("\n>> Cleanup Done.")

if __name__ == "__main__":
    asyncio.run(verify_functional())
