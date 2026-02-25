import logging
import asyncio
from typing import TypedDict, Optional, Dict, Any, List

from langgraph.graph import StateGraph, END

# Define State
class BatchState(TypedDict):
    message: str
    s1_result: Dict[str, Any] # Rule check result
    prefetched_context: Optional[Dict[str, Any]] # [Batch Optimization] Injected Context
    
    # Results
    content_result: Optional[Dict[str, Any]]
    url_result: Optional[Dict[str, Any]]
    ibse_result: Optional[Dict[str, Any]]
    
    # Final
    final_result: Optional[Dict[str, Any]]

logger = logging.getLogger(__name__)

def create_batch_graph(content_agent, url_agent, ibse_service, playwright_manager: Optional[Any] = None):
    """
    Factory to create the Unified Batch Graph with injected dependencies.
    """
    
    # --- Nodes ---
    
    async def content_node(state: BatchState):
        msg = state["message"]
        s1 = state["s1_result"]
        prefetched = state.get("prefetched_context")
        
        loop = asyncio.get_running_loop()
        
        if prefetched:
            # [Batch Optimization] Use prefetched context directly
            # check()와 유사하지만, context retrieval 단계를 건너뛰고 바로 _build_prompt -> _query_llm 호출
            # 하지만 check() 메서드는 내부적으로 _retrieve_context를 호출함.
            # 따라서 acheck의 로직을 본따서 context-aware execution을 해야 함.
            # 가장 깔끔한 방법: acheck/check에 'content_context' 인자를 추가하여 retrieval bypass 지원
            # (UrlAgent는 이미 지원함). 
            # ContentAnalysisAgent.acheck에 'content_context'(이름이 헷갈리지만 context_data임) 지원 추가 필요.
            res = await content_agent.acheck(msg, s1, content_context=prefetched)
        else:
            # Legacy/Fallback Mode
            res = await loop.run_in_executor(None, lambda: content_agent.check(msg, s1))
            
        return {"content_result": res}

    async def url_node(state: BatchState):
        msg = state["message"]
        content_result = state.get("content_result", {})
        s1 = state.get("s1_result", {})
        # 난독화 디코딩된 텍스트가 있으면 전달
        decoded_text = s1.get("decoded_text")
        # URL Agent is already Async - Content 결과를 컨텍스트로 전달
        res = await url_agent.acheck(msg, content_context=content_result, decoded_text=decoded_text, playwright_manager=playwright_manager)
        return {"url_result": res}

    async def ibse_node(state: BatchState):
        msg = state["message"]
        # Offload sync IBSE Agent to executor
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: ibse_service.process_message(msg))
        return {"ibse_result": res}

    def aggregator_node(state: BatchState):
        # Merge Logic
        c_res = state.get("content_result", {})
        u_res = state.get("url_result")
        i_res = state.get("ibse_result")
        
        final = c_res.copy()
        
        # 1. URL Override Logic (Chat mode와 동일한 로직)
        # Bidirectional Override: URL 결과에 따라 Content 판정을 수정할 수 있음
        if u_res:
             final["url_result"] = u_res  # Keep the data
             
             url_is_spam = u_res.get("is_spam")
             reason_lower = u_res.get("reason", "").lower()
             is_inconclusive = any(x in reason_lower for x in ["error", "inconclusive", "insufficient", "image only", "no url found", "no url extracted", "no url to scrape"])
             existing_reason = final.get("reason", "")
             content_code = final.get("classification_code")
             
             if is_inconclusive:
                 # Inconclusive -> Trust Content Verdict (no override)
                 final["reason"] = f"{existing_reason} | [URL: Suspected but Inconclusive]"
             elif url_is_spam:
                 # Case: Content(HAM) -> URL(SPAM) : SPAM Confirmed
                 final["is_spam"] = True
                 
                 # Update Probability (Use URL's high confidence)
                 url_prob = u_res.get("spam_probability", 0.95)
                 final["spam_probability"] = url_prob
                 
                 # Update Reason (Include specific URL reason)
                 url_reason = u_res.get("reason", "Malicious URL detected")
                 final["reason"] = f"{existing_reason} | [URL SPAM: {url_reason}]"
                 
                 # Code update: URL 스팸 코드가 있으면 무조건 업데이트 (URL 분석이 Ground Truth)
                 # Content가 이미 스팸 코드를 가지고 있어도, URL 방문 결과가 더 정확하므로 덮어씀
                 url_code = u_res.get("classification_code")
                 if url_code and str(url_code) != "0":
                     final["classification_code"] = url_code
             else:
                 # Case: Content(SPAM) -> URL(Safe) : HAM Confirmed
                 if final.get("is_spam"):
                     final["is_spam"] = False
                     final["reason"] = f"{existing_reason} | [URL: CONFIRMED SAFE (Override)]"
                     final["classification_code"] = None


        # 2. Add IBSE Info
        if i_res and i_res.get("signature"):
             final["ibse_signature"] = i_res.get("signature")
             final["ibse_len"] = i_res.get("byte_len")
             # final["reason"] += f" | Sig: {i_res.get('signature')}" # Optional
        
        return {"final_result": final}

    # --- Conditional Logic ---
    
    def router(state: BatchState):
        c_res = state.get("content_result", {})
        msg = state.get("message", "")
        s1 = state.get("s1_result", {})
        
        # [Fallback] If Content Agent failed due to Quota Error, halt the pipeline immediately 
        c_reason = c_res.get("reason", "").lower()
        if "quota" in c_reason or "exhausted" in c_reason or "429" in c_reason:
            logger.warning(f"[Graph Router] Halting pipeline due to Quota Error in Content Agent.")
            return "aggregator_node"
            
        routes = []
        
        # Check URL existence (Pre-check) to avoid unnecessary agent call
        import re
        # 원본 메시지에서 URL 체크 (한글 도메인 지원)
        # url_pattern = re.compile(r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})')
        url_pattern = re.compile(r'(?:https?://|www\.)\S+|[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.[a-zA-Z가-힣]{2,}')

        # 원본 메시지에서 URL 체크
        has_url = bool(url_pattern.search(msg))
        
        # 난독화 디코딩된 텍스트에서도 URL 체크
        decoded_text = s1.get("decoded_text")
        if decoded_text and not has_url:
            has_url = bool(url_pattern.search(decoded_text))
        
        # 또는 s1에서 이미 추출한 decoded_urls가 있으면 사용
        if s1.get("decoded_urls"):
            has_url = True
        
        # If Content Spam -> Run URL (if exists) AND IBSE (Parallel)
        # If Content Ham -> Run URL (if exists) -> If URL Spam -> Aggregator
        
        # Logic: 
        # Always run URL if exists (to catch Phishing missed by Content)
        if has_url:
            routes.append("url_node")
            
        # Run IBSE if Content is Spam
        if c_res.get("is_spam"):
            routes.append("ibse_node")
            
        # Note: If Content is Ham, we don't run IBSE initially.
        # But if URL returns Spam later, we missed IBSE?
        # Requirement: "If final is spam" -> IBSE.
        # If Content(Ham) + URL(Spam) -> Final(Spam).
        # We need IBSE in that case too.
        
        # Limitation of simple parallel branch: 
        # If URL Node runs parallel to IBSE, IBSE doesn't know URL result yet.
        # So IBSE only triggers on Content Spam here.
        # If URL turns Ham to Spam, we might need a 2nd pass or just accept we investigate Content Spams primarily.
        
        # Let's stick to: Trigger IBSE if Content is Spam.
        # (Extension: Could add edge URL -> IBSE? But that breaks parallel structure if we want Content->URL/IBSE)
        
        if not routes:
            return "aggregator_node"
            
        return routes


    # --- Graph Construction ---
    workflow = StateGraph(BatchState)
    
    workflow.add_node("content_node", content_node)
    workflow.add_node("url_node", url_node)
    workflow.add_node("ibse_node", ibse_node)
    workflow.add_node("aggregator_node", aggregator_node)
    
    workflow.set_entry_point("content_node")
    
    # Conditional Edges from Content
    workflow.add_conditional_edges(
        "content_node",
        router,
        ["url_node", "ibse_node", "aggregator_node"]
    )
    
    # Convergence
    workflow.add_edge("url_node", "aggregator_node")
    workflow.add_edge("ibse_node", "aggregator_node")
    
    return workflow.compile()
