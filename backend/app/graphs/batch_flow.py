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
                 url_reason = u_res.get("reason", "Malicious URL detected")
                 url_code = u_res.get("classification_code")
                 
                 if final.get("is_spam") is True:
                     # Case 1: Content(SPAM) + URL(SPAM) -> SPAM 유지, URL 코드/이유 추가
                     final["spam_probability"] = u_res.get("spam_probability", 0.95)
                     final["reason"] = f"{existing_reason} | [URL SPAM: {url_reason}]"
                     if url_code and str(url_code) != "0":
                         final["classification_code"] = url_code
                 else:
                     # Case 2: Content(HAM) + URL(SPAM) -> HAM 반환, 대신 [텍스트 HAM + 악성 URL] 특수 처리
                     # [User Request] 메시지 자체(텍스트)는 HAM이므로 덮어쓰지 않고 HAM을 유지한다. (오탐 학습 방지)
                     # 단, 엑셀/DB 저장을 위해 '악성 URL 추출됨' 특수 플래그를 넘긴다.
                     final["is_spam"] = False
                     final["reason"] = f"{existing_reason} | [텍스트 HAM + 악성 URL 분리 감지: {url_reason}]"
                     final["malicious_url_extracted"] = True
                     final["url_spam_code"] = url_code # URL 추출본 시트에 저장할 용도
             else:
                 # Case 3: URL(Safe) -> 만약 Content가 SPAM이었다 하더라도 Override하여 HAM 확정
                 if final.get("is_spam"):
                     final["is_spam"] = False
                     final["reason"] = f"{existing_reason} | [URL: CONFIRMED SAFE (Override)]"
                     final["classification_code"] = None

        # Ensure malicious_url_extracted is explicitly in the final dict if set
        if "malicious_url_extracted" in final and final["malicious_url_extracted"] is True:
             # Ensure the value is properly returned
             final["malicious_url_extracted"] = True


        # 2. Add IBSE Info
        if i_res and i_res.get("signature"):
             final["ibse_signature"] = i_res.get("signature")
             final["ibse_len"] = i_res.get("byte_len")
             # final["reason"] += f" | Sig: {i_res.get('signature')}" # Optional
        
        return {"final_result": final}

    def fp_sentinel_node(state: BatchState):
        """
        FP Sentinel (오탐 방지 정책 에이전트)
        의미 클래스(Semantic Class)를 분류하고, Type_B에 대해 학습 라벨(Learning Label)과 차단(Enforcement) 정책을 분리/강제합니다.
        """
        final = state.get("final_result", {})
        c_res = state.get("content_result", {})
        u_res = state.get("url_result")
        
        signals = c_res.get("signals", {})
        c_impersonation = signals.get("is_impersonation", False)
        c_vague_cta = signals.get("is_vague_cta", False)
        c_personal_lure = signals.get("is_personal_lure", False)
        
        u_blocked = False
        u_spam = False
        if u_res:
             u_blocked = u_res.get("bot_protection_active", False)
             u_spam = u_res.get("is_spam") is True
             
        # [Priority 0] URL CONFIRMED SAFE → 무조건 HAM 확정
        # URL Agent가 안전하다고 명시적으로 확인한 경우, c_impersonation 여부와 무관하게 HAM 처리
        # (관리비 미납 알림 등 정상 URL을 포함한 메시지가 사칭으로 오분류되는 것 방지)
        final_reason = final.get("reason", "")
        if "CONFIRMED SAFE" in final_reason:
             semantic_class = "Ham"
             learning_label = "HAM"
             # is_spam은 aggregator가 이미 False로 설정했으므로 그대로 유지

        # Rulset 1: Type_B (FP-Sensitive Spam) - 사칭/기만 감지
        # c_impersonation=True이면 URL 결과(존재여부, timeout 등) 무관하게 Type_B 확정
        # 대기업/공공기관 사칭은 정상 업무 단어를 사용하므로 나이브베이즈 보호 필수
        elif c_impersonation:
             semantic_class = "Type_B"
             learning_label = "HAM" # 학습에서 제외하여 나이브베이즈 보호
             
             # Enforcement: SPAM으로 강제 (HITL/HAM 오버라이드)
             if final.get("is_spam") is not True:
                 final["is_spam"] = True
                 final["classification_code"] = "10" # 강제 Phishing/사칭 코드
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 final["reason"] = f"{existing_reason} | [FP Sentinel Override] 사칭/기만(Type_B) 확정 차단"
                 
        # Ruleset 1.2: Type_B (Vague CTA 스팸 확정)
        # 텍스트가 의도적으로 모호/범용어이고 최종 스팸으로 판정된 경우 (URL 추출 여부 무관)
        # → 텍스트만 스팸으로 학습하면 나이브베이즈에 치명적 오탐 유발할 수 있으므로 보호
        elif c_vague_cta and final.get("is_spam") is True:
             semantic_class = "Type_B"
             learning_label = "HAM"
             
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 final["reason"] = f"{existing_reason} | [FP Sentinel Override] 모호한 CTA 스팸(Type_B) 처리 (NB 보호)"

        # Ruleset 1.3: Type_B (Personal Lure)
        # 지인 사칭, 경조사 위장 등 100% 일상어로 구성된 메시지 (URL 유무 무관하게 NB에서 철저히 보호)
        elif c_personal_lure:
             semantic_class = "Type_B"
             learning_label = "HAM"
             
             # Enforcement: SPAM으로 강제
             if final.get("is_spam") is not True:
                 final["is_spam"] = True
                 
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 final["reason"] = f"{existing_reason} | [FP Sentinel Override] 사적/경조사 위장(Type_B) 확정 차단"

        # Ruleset 1.5: Type_B (URL-Separated / URL-Blocked Case)
        # Content Agent가 HAM으로 판단했지만 URL이 악성이거나 접근 불가(timeout, bot-block)인 경우
        # → 텍스트는 정상처럼 보이지만 URL 위험이 있는 FP-Sensitive 케이스
        elif c_res.get("is_spam") is False and (
            final.get("malicious_url_extracted") is True or u_blocked
        ):
             semantic_class = "Type_B"
             learning_label = "HAM"
             final["is_spam"] = True  # Enforcement: 차단
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 cause = "악성 URL 탐지" if final.get("malicious_url_extracted") else "URL 접근 불가(timeout/bot-block)"
                 final["reason"] = f"{existing_reason} | [FP Sentinel Override] {cause} Type_B 확정 차단"

        # Rulset 2: Type_A (Pure Spam)
        elif final.get("is_spam") is True:
             semantic_class = "Type_A"
             learning_label = "SPAM"
             
        # Rulset 3: Ham
        else:
             semantic_class = "Ham"
             learning_label = "HAM"
             
        final["semantic_class"] = semantic_class
        final["learning_label"] = learning_label
        
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
    workflow.add_node("fp_sentinel_node", fp_sentinel_node)
    
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
    
    # FP Sentinel Policy Engine
    workflow.add_edge("aggregator_node", "fp_sentinel_node")
    workflow.add_edge("fp_sentinel_node", END)
    
    return workflow.compile()
