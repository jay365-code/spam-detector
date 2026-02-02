
import asyncio
from typing import List, Dict, Any

# Mock Services
class MockSpamRagService:
    def search_similar_batch(self, query_intent_summaries: List[str], k: int = 3) -> List[Dict[str, Any]]:
        print(f"[MockRag] Received {len(query_intent_summaries)} summaries for batch search.")
        results = []
        for i, summary in enumerate(query_intent_summaries):
            # Return a distinct result for each input to verify matching
            results.append({
                "hits": [{"id": f"rag_{i}", "message": f"Context for {summary}"}],
                "query_summary": summary
            })
        return results

class MockContentAgent:
    def __init__(self):
        self.rag_service = MockSpamRagService()

    def _load_full_guide(self):
        return "Generic Guide"

    def generate_intent_summary(self, message: str) -> str:
        # Simulate blocking work
        return f"Summary({message})"

    async def prepare_batch_contexts(self, messages: list[str]) -> list[dict]:
        print(f"[MockAgent] Preparing batch contexts for {len(messages)} messages.")
        loop = asyncio.get_running_loop()
        
        # 1. Intent Summary Generation (Simulating Parallel execution)
        summary_tasks = [
            loop.run_in_executor(None, lambda m=msg: self.generate_intent_summary(m))
            for msg in messages
        ]
        intent_summaries = await asyncio.gather(*summary_tasks)
        print(f"[MockAgent] Generated {len(intent_summaries)} summaries.")
        
        # 2. Batch RAG Search
        # Directly calling mock service
        rag_results_list = self.rag_service.search_similar_batch(intent_summaries, k=2)
        
        # 3. Assemble Contexts
        contexts = []
        for i, rag_res in enumerate(rag_results_list):
            hits = rag_res.get("hits", [])
            contexts.append({
                "guide_context": "Generic Guide",
                "rag_examples": hits,
                "intent_summary": intent_summaries[i],
                "input_msg_ref": messages[i] # Added for verification
            })
            
        return contexts

async def verify_batch_matching():
    agent = MockContentAgent()
    
    # Test Data: 5 messages
    messages = [f"Message_{i}" for i in range(5)]
    
    print("--- Starting Verification ---")
    contexts = await agent.prepare_batch_contexts(messages)
    
    print("\n--- Verifying Results ---")
    correct_count = 0
    for i, ctx in enumerate(contexts):
        msg = messages[i]
        intent = ctx["intent_summary"]
        rag_hit = ctx["rag_examples"][0]["message"]
        
        print(f"Index {i}:")
        print(f"  Input: {msg}")
        print(f"  Intent: {intent}")
        print(f"  RAG Context: {rag_hit}")
        
        # Verification Logic
        is_match = (intent == f"Summary({msg})") and (rag_hit == f"Context for Summary({msg})")
        if is_match:
            print("  => ✅ MATCH OK")
            correct_count += 1
        else:
            print("  => ❌ MISMATCH")

    if correct_count == len(messages):
        print("\nSUCCESS: All items matched correctly.")
    else:
        print("\nFAILURE: Some items were mismatched.")

if __name__ == "__main__":
    asyncio.run(verify_batch_matching())
