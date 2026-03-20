import logging
import asyncio
from typing import TypedDict, Optional, Dict, Any, List

from langgraph.graph import StateGraph, END

# Define State
class BatchState(TypedDict):
    message: str
    s1_result: Dict[str, Any] # Rule check result
    prefetched_context: Optional[Dict[str, Any]] # [Batch Optimization] Injected Context
    pre_parsed_url: Optional[str] # KISA TXT에서 탭으로 파싱한 URL (있으면 본문 추출 대신 사용)
    pre_parsed_only_mode: Optional[bool]  # KISA TXT면 URL 없을 때 본문 추출 스킵 (Chat/Excel은 False)
    
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
        pre_parsed_url = state.get("pre_parsed_url")
        pre_parsed_only_mode = state.get("pre_parsed_only_mode", False)
        # 난독화 디코딩된 텍스트가 있으면 전달
        decoded_text = s1.get("decoded_text")
        # URL Agent is already Async - Content 결과를 컨텍스트로 전달
        # pre_parsed_url: KISA TXT에서 파싱한 URL이 있으면 본문 추출 대신 사용
        # pre_parsed_only_mode: KISA TXT면 URL 없을 때 본문 추출 스킵
        res = await url_agent.acheck(msg, content_context=content_result, decoded_text=decoded_text, pre_parsed_url=pre_parsed_url, pre_parsed_only_mode=pre_parsed_only_mode, playwright_manager=playwright_manager)
        return {"url_result": res}

    async def ibse_node(state: BatchState):
        msg = state["message"]
        c_res = state.get("content_result", {})
        signals = c_res.get("signals", {})
        is_garbage = signals.get("is_garbage_obfuscation", False)
        is_safe_url_injection = signals.get("is_safe_url_injection", False)
        
        # IBSE Agent is now Async
        res = await ibse_service.process_message(msg, is_garbage_obfuscation=is_garbage, is_safe_url_injection=is_safe_url_injection)
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
                 url_reason_text = u_res.get('reason', '')
                 if 'All URLs scanned' in url_reason_text:
                     final["reason"] = f"{existing_reason} | [URL: Inconclusive ({url_reason_text})]"
                 else:
                     final["reason"] = f"{existing_reason} | [URL: Suspected but Inconclusive ({url_reason_text})]"
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
                     # Do NOT wipe final["classification_code"] to preserve Content Agent's original intent

        # Ensure malicious_url_extracted is explicitly in the final dict if set
        if "malicious_url_extracted" in final and final["malicious_url_extracted"] is True:
             # Ensure the value is properly returned
             final["malicious_url_extracted"] = True


        # 2. Add IBSE Info
        if i_res:
             if i_res.get("signature"):
                 final["ibse_signature"] = i_res.get("signature")
                 final["ibse_len"] = i_res.get("byte_len_cp949", i_res.get("byte_len"))
                 
             # [Broken URL Drop Logic]
             # IBSE Agent extracts a contextual sentence instead of the broken URL.
             # We must drop the URL from the final output to fulfill "URL : 없음" requirement.
             is_broken = u_res and u_res.get("details", {}).get("is_broken_short_url") is True
             
             # User requested fix: Drop URL if Safe URL Injection is detected.
             # This is flagged by fp_sentinel_node setting final["drop_url"] = True later,
             # but we can also set it proactively here if we have a url_reason indicating it.
             url_reason = final.get("reason", "")
             url_reason_lower = url_reason.lower()
             is_injection = "위장 url" in url_reason_lower or "정상 도메인 위장" in url_reason_lower or "방패막이" in url_reason_lower or "decoy" in url_reason_lower or "safe url injection" in url_reason_lower
             
             if is_broken or is_injection:
                 final["drop_url"] = True
                 if "details" in u_res:
                     u_res["details"]["extracted_url"] = None
                     u_res["details"]["final_url"] = None
                     u_res["details"]["attempted_urls"] = []

             # 3. User Requested: If unextractable AND no URL was found, drop completely from Excel
             # If is_broken is True, treat it as no URL.
             has_extracted_url = bool(u_res and (u_res.get("target_urls") or u_res.get("current_url") or u_res.get("visited_history")))
             if is_broken: has_extracted_url = False
                 
             if i_res.get("decision") == "unextractable" and not has_extracted_url:
                 # SPAM으로 분류된 건은 시그니처가 없더라도 육안분석 시트에 로그를 남기기 위해 예외 처리
                 if not final.get("is_spam"):
                     final["exclude_from_excel"] = True
                 
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
        c_garbage_obfuscate = signals.get("is_garbage_obfuscation", False)
        c_normal_layout = signals.get("is_normal_layout", False)
        
        u_blocked = False
        u_spam = False
        if u_res:
             u_blocked = u_res.get("bot_protection_active", False)
             u_spam = u_res.get("is_spam") is True
             
        # [Priority 0.5] Safe URL Injection Detection
        # content_agent가 도박/불법 텍스트인데 youtube.com 등 정상 사이트(혹은 아무 관련 없는 사이트)를 방패막이로 썼다고 판별한 경우.
        # URL Agent가 파싱 중 (404 에러 등으로) SPAM 판정을 내렸든 SAFE 판정을 내렸든 무관하게,
        # 이 URL은 스팸 본질과 무관한 '정상 도메인'이므로 무조건 추출 명단에서 드롭해야 한다. (youtube.com을 치명적 스팸으로 차단하는 것 방지)
        is_safe_url_injection = signals.get("is_safe_url_injection", False)
        text_prob = final.get("spam_probability", 0.0)
        
        if is_safe_url_injection and text_prob >= 0.8:
            semantic_class = "Type_B" if (c_impersonation or c_vague_cta or c_personal_lure or c_normal_layout) else "Type_A"
            learning_label = "HAM" if semantic_class == "Type_B" else "SPAM"
            final["is_spam"] = True # Enforcement
            final["drop_url"] = True # 무조건 URL 드롭 지시 (가장 중요)
            existing_reason = final.get("reason", "")
            
            if "[Safe-URL Injection 감지" not in existing_reason:
                final["reason"] = f"{existing_reason} | [Safe-URL Injection 감지: 방패막이 위장 전술 (URL 스크래핑 결과와 무관). URL 드롭 및 SPAM 확정]"
            
            # Type B 방패 처리
            if semantic_class == "Type_B" and "[FP Sentinel Override]" not in final["reason"]:
                 final["reason"] += " | [FP Sentinel Override] 사칭/기만(Type_B) 보호"
                 
            # Priority 0.5가 발동하면 이후 로직은 스킵
            pass
                 
        # [Priority 0] URL CONFIRMED SAFE → 무조건 HAM 확정
        # (단, 위 Priority 0.5의 Safe-URL Injection에 해당하지 않는 경우에만)
        # URL Agent가 안전하다고 명시적으로 확인한 경우, c_impersonation 여부와 무관하게 HAM 처리
        # (관리비 미납 알림 등 정상 URL을 포함한 메시지가 사칭으로 오분류되는 것 방지)
        elif "CONFIRMED SAFE" in final.get("reason", ""):
             semantic_class = "Ham"
             learning_label = "HAM"
             # is_spam은 aggregator가 이미 False로 설정했으므로 그대로 유지

        # Rulset 1: Type_B (FP-Sensitive Spam) - 사칭/기만 감지
        # c_impersonation=True이고 최종 스팸으로 판정된 경우
        # 대기업/공공기관 사칭은 정상 업무 단어를 사용하므로 학습 보호 필수
        elif c_impersonation and final.get("is_spam") is True:
             semantic_class = "Type_B"
             learning_label = "HAM" # 학습에서 제외하여 학습 보호
             
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 final["reason"] = f"{existing_reason} | [FP Sentinel Override] 사칭/기만(Type_B) 보호"
                 
        # Ruleset 1.2: Type_B (Vague CTA 스팸 확정)
        # 텍스트가 의도적으로 모호/범용어이고 최종 스팸으로 판정된 경우 (URL 추출 여부 무관)
        # → 텍스트만 스팸으로 학습하면 학습 모델에 치명적 오탐 유발할 수 있으므로 보호
        elif c_vague_cta and final.get("is_spam") is True:
             semantic_class = "Type_B"
             learning_label = "HAM"
             
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 final["reason"] = f"{existing_reason} | [FP Sentinel Override] 모호한 CTA 스팸(Type_B) 처리 (학습 보호)"

        # Ruleset 1.3: Type_B (Personal Lure)
        # 지인 사칭, 경조사 위장 등 100% 일상어로 구성되었으나 스팸으로 판정된 경우
        elif c_personal_lure and final.get("is_spam") is True:
             semantic_class = "Type_B"
             learning_label = "HAM"
             
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 has_sig = bool(final.get("ibse_signature"))
                 if has_sig:
                     final["reason"] = f"{existing_reason} | [FP Sentinel Override] 사적/경조사 위장(Type_B) 보호 + 시그니처: {final.get('ibse_signature')}"
                 else:
                     final["reason"] = f"{existing_reason} | [FP Sentinel Override] 사적/경조사 위장(Type_B) 보호"

        # Ruleset 1.4: Type_B (Garbage Obfuscation)
        # 내용 없이 필터 우회용 문자 조각들로만 구성되었고 스팸으로 판정된 경우
        elif c_garbage_obfuscate and final.get("is_spam") is True:
             semantic_class = "Type_B"
             learning_label = "HAM"
             
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                 final["reason"] = f"{existing_reason} | [FP Sentinel Override] 난독화/쓰레기 토큰(Type_B) 보호"

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

        # Ruleset 1.6: Type_B (Safety Block)
        # 구글 안전 필터 등에 의해 강제 차단(Safety Filter Blocked)된 메시지
        # → 정상적인 서비스/학교 안내문자일 확률이 높으므로 URL/서명 유무와 상관없이 강제 Type_B 편입하여 오탐(FP) 집계를 막음
        elif final.get("is_spam") is True and "Safety Filter Blocked" in final.get("reason", ""):
            semantic_class = "Type_B"
            learning_label = "HAM"
            existing_reason = final.get("reason", "")
            if "[FP Sentinel Override]" not in existing_reason:
                final["reason"] = f"{existing_reason} | [FP Sentinel Override] 안전 필터 차단 감지로 인한 Type_B 전환"

        # Ruleset 1.7: Type_B (Normal Layout Ad with Compliance Issues)
        # 정상적인 홍보/모집 문자 레이아웃이지만 정통망법 미준수나 강한 유도로 스팸 판정된 경우
        # → 레이아웃 자체가 너무 평범하므로 CNN이 학습하면 정상 광고를 오탐할 위험 큼
        elif c_normal_layout and final.get("is_spam") is True:
             semantic_class = "Type_B"
             learning_label = "HAM"
             
             existing_reason = final.get("reason", "")
             if "[FP Sentinel Override]" not in existing_reason:
                  final["reason"] = f"{existing_reason} | [FP Sentinel Override] 템플릿 오탐 방지: 일반 광고 레이아웃(Type_B) 보호"

        # Rulset 2: Type_A (Pure Spam)
        elif final.get("is_spam") is True:
             semantic_class = "Type_A"
             learning_label = "SPAM"
             
        # Rulset 3: Ham
        else:
             semantic_class = "Ham"
             learning_label = "HAM"
             
        # 최종 HAM 판정 시, 앞서 병렬 실행된 IBSE 노드가 추출했던 문자열(시그니처) 초기화
        if semantic_class == "Ham":
             final["ibse_signature"] = None
             final["ibse_category"] = None
             
        # Type_B Sub-classification
        if semantic_class == "Type_B":
             # 본문에 있는 url은 분석은 하되, type 결정에는 input text의 url만 사용
             pre_parsed = state.get("pre_parsed_url")
             is_input_url_present = bool((pre_parsed or "").strip())

             # 최종 결과가 SPAM 파생(Type_B 자체도 SPAM)이고 소스 데이터(KISA)의 URL 필드에 값이 존재하면 (URL) 서브타입 지정
             has_url_subtype = is_input_url_present
             
             has_sig = bool(final.get("ibse_signature"))
             
             if has_url_subtype and has_sig:
                 semantic_class = "Type_B (URL, SIGNATURE)"
             elif has_url_subtype:
                 semantic_class = "Type_B (URL)"
             elif has_sig:
                 semantic_class = "Type_B (SIGNATURE)"
             else:
                 semantic_class = "Type_B (NONE)"
             
        # (Removed fallback logic as requested by user)

        final["semantic_class"] = semantic_class
        final["learning_label"] = learning_label
        
        # [NEW] 안전망: 스팸(Type A/B)으로 분류되었는데 LLM 누락으로 분류 코드가 없을 경우 강제 할당
        if semantic_class != "Ham" and not final.get("classification_code"):
             # Ruleset 1.5처럼 URL에 의해 스팸으로 뒤집힌 경우 url_spam_code 우선 적용, 없으면 기본 "0"
             final["classification_code"] = final.get("url_spam_code") or "0"
        
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
            
        # [NEW] KISA TXT 등으로 pre_parsed_url 이 명시적으로 넘어온 경우
        if state.get("pre_parsed_url"):
            has_url = True
            
        # [NEW] Content Agent가 난독화 복원 도메인을 찾아낸 경우 무조건 URL 검사 진행
        if c_res and c_res.get("obfuscated_urls"):
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
