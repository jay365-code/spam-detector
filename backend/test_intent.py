# -*- coding: utf-8 -*-
import asyncio
import os
from app.agents.content_agent.agent import ContentAnalysisAgent
from app.services.spam_rag_service import get_spam_rag_service

async def main():
    agent = ContentAnalysisAgent()
    rag_service = get_spam_rag_service()
    
    msg = "(광고) 환절기 건강 유의하시고 저녁맛있게 드세요^^!  ▶정다운 대표  무료거부0808706154"
    
    with open("test_out_utf8.txt", "w", encoding="utf-8") as f:
        f.write("--- 1. Testing intent generation ---\n")
        intent1 = await agent.agenerate_intent_summary(msg)
        f.write(f"Call 1 (Intent Analysis): {intent1}\n")
        
        intent2 = await agent.agenerate_intent_summary(msg)
        f.write(f"Call 2 (Intent Analysis): {intent2}\n")
        
        f.write("\n--- 2. Testing Web UI style RAG retrieval ---\n")
        res_web = rag_service.search_similar(intent1, k=3)
        hits_web = res_web.get("hits", [])
        threshold = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.50"))
        filtered_web = [h for h in hits_web if h.get("distance", 999) <= threshold]
        f.write(f"Web Raw Hits: {len(hits_web)}\n")
        for i, h in enumerate(hits_web):
            f.write(f" - [{h['distance']:.3f}] {h.get('label', '')}: {h['message'][:50]}...\n")
        f.write(f"Web Filtered Hits (Threshold <= {threshold}): {len(filtered_web)}\n")
            
        f.write("\n--- 3. Testing Batch style RAG retrieval ---\n")
        batch_contexts = await agent.prepare_batch_contexts([msg])
        ctx = batch_contexts[0]
        hits_batch = ctx.get("rag_examples", [])
        f.write(f"Batch Raw Hits: {len(hits_batch)}\n")
        for i, h in enumerate(hits_batch):
            score = h.get('score', h.get('distance', 999))
            f.write(f" - [{score:.3f}] {h.get('label', '')}: {h['message'][:50]}...\n")
        
        # Simulate Prompt Injection Logic (Forces top 2)
        prompt, valid_examples = agent._build_prompt(msg, "None", ctx)
        f.write(f"\nBatch Injected Hits (in Prompt): {len(valid_examples)}\n")
        for i, h in enumerate(valid_examples):
            f.write(f" - [{h.get('score', 999):.3f}] {h.get('label', '')}: {h['message'][:50]}...\n")

if __name__ == '__main__':
    asyncio.run(main())
