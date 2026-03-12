import os
from dotenv import load_dotenv

load_dotenv(override=True) # Load .env file (override system variables)

import json
import logging
import time
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log
from app.core.logging_config import get_logger
from app.core.llm_manager import key_manager

# New imports added as per instruction (Moved to local scope to fix 23s startup delay)
# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_anthropic import ChatAnthropic
# from langchain_openai import ChatOpenAI

logger = get_logger(__name__)


class QuotaExhaustedNoRetryError(Exception):
    """모든 키 quota 소진 시 즉시 중단 (tenacity 재시도 제외)"""
    pass
# from openai import OpenAI  <-- Removed global import


def _normalize_llm_content(content) -> str:
    """
    LLM 응답 content를 항상 str로 변환.
    Gemini(LangChain) 등은 content를 list [{"type":"text","text":"..."}] 형태로 반환할 수 있음.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            return first.get("text", "") or ""
        if isinstance(first, str):
            return first
        # LangChain AIMessageChunk 등: .get("text") 또는 .text
        return str(getattr(first, "text", first) if hasattr(first, "text") else first)
    return str(content)


def _clean_intent_summary(text: str) -> str:
    """
    LLM이 Intent Summary 앞에 마크다운 헤더/볼드 레이블을 포함할 경우 제거.
    예: "**Principal Intent / Tactics / Action Request**\nIllegal Loan..."
        → "Illegal Loan..."
    """
    import re
    text = text.strip()
    # **...** 볼드 패턴 제거
    text = re.sub(r"\*\*.*?\*\*\s*\n?", "", text).strip()
    # "Principal Intent / Tactics / Action Request" 헤더 줄 제거 (대소문자 무시)
    text = re.sub(r"(?i)^principal intent\s*/\s*tactics\s*/\s*action request\s*\n?", "", text).strip()
    # 앞쪽 줄이 슬래시 없이 단독 레이블이면 제거 (슬래시 포함 본문만 남김)
    lines = text.splitlines()
    if lines and "/" not in lines[0] and len(lines) > 1:
        text = "\n".join(lines[1:]).strip()
    return text


class ContentAnalysisAgent: # Renamed from RagBasedFilter
    def __init__(self):
        self.vector_db = None
        self._full_guide_cache = None
        # [Optimization] Event-Loop Bound Cache: (provider_key_model, loop) -> client
        self._loop_bound_clients = {}

    @property
    def model_name(self) -> str:
        """런타임에 LLM_MODEL 반영 (설정 변경 시 즉시 적용)"""
        return os.getenv("LLM_MODEL", "gpt-4o-mini")

    def _get_vector_db(self):
        if self.vector_db is None:
            # Local imports to optimize startup
            logger.info("[ContentAnalysisAgent] Lazy loading Vector DB...")
            import time
            start_t = time.time()
            from langchain_community.vectorstores import Chroma
            from langchain_openai import OpenAIEmbeddings
            logger.info(f"[ContentAnalysisAgent] Imports took {time.time() - start_t:.4f}s")
            
            logger.info("ChromaDB 초기화 중...")
            start_t = time.time()
            self.vector_db = Chroma(
                collection_name="spam_guide",
                embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
                persist_directory=os.path.join(os.path.dirname(__file__), "../../../data/chroma_db")
            )
            logger.info(f"[ContentAnalysisAgent] ChromaDB initialized in {time.time() - start_t:.4f}s")
        return self.vector_db

    def search_guide(self, message: str, k: int = 3):
        """Guide 검색 (실패 시 빈 리스트 반환)"""
        try:
            db = self._get_vector_db()
            results = db.similarity_search(message, k=k)
            logger.info(f"RAG 검색 결과: {len(results)}건")
            for i, doc in enumerate(results):
                logger.debug(f"  [{i+1}] {doc.page_content[:80]}...")
            return results
        except Exception as e:
            logger.warning(f"RAG Guide Search Error: {e}")
            return []
    
    def _search_spam_rag(self, intent_summary: str, k: int = 2) -> list:
        """스팸 참조 예시 검색 (Spam RAG) - Intent Summary 기반"""
        # 환경변수로 검색 비활성화 가능 (비용 절감)
        rag_enabled = os.getenv("SPAM_RAG_ENABLED", "1")
        if rag_enabled != "1":
            print(f"    [Spam RAG] Disabled (SPAM_RAG_ENABLED={rag_enabled})")
            return []
        
        try:
            from app.services.spam_rag_service import get_spam_rag_service
            rag_service = get_spam_rag_service()
            # Intent Summary로 검색
            results = rag_service.search_similar(intent_summary, k=k)
            return results.get("hits", []) # Contract: returns dict with 'hits'
        except Exception as e:
            logger.warning(f"RAG Search Error: {e}")
            return []

    def _retrieve_context(self, message: str, intent_summary: str = None) -> dict:
        """
        Retrieves context from Vector DB or loads full spam guide.
        Also retrieves similar FN examples using Intent Summary.
        
        Returns:
            dict with 'guide_context' and 'rag_examples'
        """
        logger.debug("Using Full Spam Guide Text (Always)")
        guide_context = self._load_full_guide()
        
        # RAG 예시 검색 (유사 스팸 사례) - Intent Summary 필수
        rag_examples = []
        if intent_summary:
            rag_examples = self._search_spam_rag(intent_summary, k=4)
            if rag_examples:
                logger.info(f"Spam RAG: {len(rag_examples)}건 검색됨")
            else:
                logger.debug("Spam RAG: 유사 사례 없음")
        else:
             logger.warning("Spam RAG: Intent Summary missing, skipping search.")
        
        return {
            "guide_context": guide_context,
            "rag_examples": rag_examples
        }
    
    def _load_full_guide(self) -> str:
        """전체 spam_guide.md 로드 (Caching 적용)"""
        if self._full_guide_cache:
            return self._full_guide_cache
            
        try:
            guide_path = os.path.join(os.path.dirname(__file__), "../../../data/spam_guide.md")
            with open(guide_path, "r", encoding="utf-8") as f:
                self._full_guide_cache = f.read()
                return self._full_guide_cache
        except Exception as e:
            try: 
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                guide_path = os.path.join(base_dir, "data/spam_guide.md")
                with open(guide_path, "r", encoding="utf-8") as f:
                    self._full_guide_cache = f.read()
                    return self._full_guide_cache
            except Exception as e2:
                logger.error(f"    [Error] Failed to load spam_guide.md: {e2}")
                return "스팸 판단 기준: 도박, 성인, 사기, 불법 대출 의도가 명확하면 SPAM, 그렇지 않으면 HAM."

    def _get_cached_client(self, provider: str, api_key: str, model_name: str):
        """
        Retrieves or creates an LLM client instance safely bound to the current asyncio loop.
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        cache_key = f"{provider}_{api_key}_{model_name}"
        dict_key = (cache_key, current_loop)

        if dict_key in self._loop_bound_clients:
            return self._loop_bound_clients[dict_key]

        logger.info(f"[ContentAnalysisAgent] Instantiating new LLM client for {provider} ({model_name})")
        
        if provider == "GEMINI":
            from langchain_google_genai import ChatGoogleGenerativeAI
            # [Safety Settings]
            from langchain_google_genai import HarmCategory, HarmBlockThreshold
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            # [CRITICAL] max_retries=0 disables Langchain's internal exponential backoff
            # This allows our LLMKeyManager to rotate keys immediately on 429 quota exhaustion
            client = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=0.0,
                safety_settings=safety_settings,
                convert_system_message_to_human=True,
                max_retries=0 
            )
            
        elif provider == "CLAUDE":
            from langchain_anthropic import ChatAnthropic
            client = ChatAnthropic(
                model=model_name, 
                anthropic_api_key=api_key, 
                temperature=0.0,
                max_retries=0
            )
            
        else: # OPENAI
            from langchain_openai import ChatOpenAI
            client = ChatOpenAI(
                model=model_name, 
                api_key=api_key, 
                temperature=0.0,
                max_retries=0
            )

        self._loop_bound_clients[dict_key] = client
        return client

    # Define SafetyBlockRetryError to handle Gemini PROHIBITED_CONTENT cases
    class SafetyBlockRetryError(Exception):
        pass

    async def _aquery_llm(self, prompt: str) -> str:
        """
        주어진 프롬프트를 사용하여 선택된 LLM에 질의를 보냅니다.
        """
        # [Early Exit] 타 에이전트/태스크에 의해 이미 모든 키 소진이 확인되었는지 체크
        provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
        if key_manager.is_quota_exhausted(provider):
            raise QuotaExhaustedNoRetryError(f"{provider} quota exhausted (all keys). No retry.")
        keys = key_manager._keys_pool.get(provider, [])
        # User Request: Retry exactly the number of available keys to test each key once on Quota 429.
        max_quota_tries = max(1, len(keys))
        
        for attempt in range(max_quota_tries):
            if key_manager.is_quota_exhausted(provider):
                raise QuotaExhaustedNoRetryError(f"{provider} quota exhausted (all keys). No retry.")
                
            api_key = key_manager.get_key(provider)
            if not api_key:
                raise ValueError(f"{provider}_API_KEY is not configured.")

            try:
                if provider == "GEMINI":
                    # We removed the individual api_key fetches since it's fetched before the try block
                    current_api_key = api_key
                    model_name = self.model_name if "gemini" in self.model_name else "gemini-1.5-flash"
                    
                    llm = self._get_cached_client(provider, current_api_key, model_name)
                    
                    try:
                        from langchain_core.messages import HumanMessage
                        # [Fix] Add explicit 45s timeout to prevent 300s hang
                        try:
                            response = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                        except asyncio.TimeoutError as e:
                            logger.warning(f"[{provider}] LLM Timeout occurred (45s). Attempting Fallback to Sub Model.")
                            sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-flash-lite-preview")
                            fallback_key = key_manager.get_key("GEMINI")
                            if fallback_key:
                                fallback_llm = self._get_cached_client("GEMINI", fallback_key, sub_model)
                                try:
                                    response = await asyncio.wait_for(fallback_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                                except Exception as fallback_e:
                                    logger.error(f"[Fallback] Sub model also failed: {fallback_e}")
                                    raise Exception("Async LLM Timeout (Fallback failed)") from e
                            else:
                                raise Exception("Async LLM Timeout (No fallback key)") from e
                        
                        content = _normalize_llm_content(response.content)
                        
                        # Gemini Safety Filter Block 처리
                        if not content:
                            finish_reason = response.response_metadata.get("finish_reason", "")
                            meta_str = str(response.response_metadata)
                            if finish_reason == "SAFETY" or "PROHIBITED_CONTENT" in meta_str or "block_reason" in meta_str:
                                logger.warning(f"[Gemini] Response blocked by safety filters (PROHIBITED_CONTENT): {meta_str}")
                                raise self.SafetyBlockRetryError("Response blocked by safety filters (PROHIBITED_CONTENT)")
                            
                    except self.SafetyBlockRetryError:
                        raise
                    except Exception as e:
                        # Check for safety filter block which might raise specific exceptions or return empty/stopped response
                        err_str = str(e).lower()
                        if "safety" in err_str or "blocked" in err_str or "prohibited" in err_str:
                            logger.warning(f"[Gemini] Response blocked by safety filters exception: {e}")
                            raise self.SafetyBlockRetryError(f"Response blocked by safety filters: {e}")
                        else:
                            raise e
                    
                elif provider == "CLAUDE":
                    current_api_key = api_key
                    model_name = self.model_name if "claude" in self.model_name else "claude-3-haiku-20240307"
                    
                    llm = self._get_cached_client(provider, current_api_key, model_name)
                    from langchain_core.messages import HumanMessage
                    response = await llm.ainvoke([HumanMessage(content=prompt)])
                    content = _normalize_llm_content(response.content)
                    
                else: # OPENAI
                    current_api_key = api_key
                    model_name = self.model_name
                    
                    llm = self._get_cached_client(provider, current_api_key, model_name)
                    from langchain_core.messages import HumanMessage
                    response = await llm.ainvoke([HumanMessage(content=prompt)])
                    content = _normalize_llm_content(response.content)
                # All providers
                key_manager.report_success(provider)
                return content
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # ----------------------------------------------------------------
                # [Provider별 Quota/Rate-Limit 에러 감지]
                # 각 SDK의 고유 Exception 타입을 먼저 체크하고,
                # isinstance 체크 실패 시 error string으로 폴백
                # ----------------------------------------------------------------
                is_quota_error = False
                
                if provider == "GEMINI":
                    try:
                        import google.api_core.exceptions
                        if isinstance(e, (google.api_core.exceptions.ResourceExhausted, google.api_core.exceptions.TooManyRequests)):
                            is_quota_error = True
                    except ImportError:
                        pass
                    # [버그 수정] 확실한 429 오인식 방지를 위해 HTTP status code 또는 명백한 문구를 추가
                    if not is_quota_error:
                        is_quota_error = any(kw in error_msg for kw in ["quota", "rate", "429", "limit", "resource exhausted", "too many requests"])
                
                elif provider == "OPENAI":
                    try:
                        import openai
                        if isinstance(e, openai.RateLimitError):
                            is_quota_error = True
                    except ImportError:
                        pass
                    # String fallback: "rate_limit", "insufficient_quota", "429"
                    if not is_quota_error:
                        is_quota_error = any(kw in error_msg for kw in ["rate limit", "rate_limit", "quota", "429", "limit", "insufficient"])
                
                elif provider == "CLAUDE":
                    try:
                        import anthropic
                        if isinstance(e, anthropic.RateLimitError):
                            is_quota_error = True
                    except ImportError:
                        pass
                    # String fallback: "rate limit", "overloaded", "429"
                    if not is_quota_error:
                        is_quota_error = any(kw in error_msg for kw in ["rate limit", "rate_limit", "quota", "429", "limit", "overloaded"])
                
                # ----------------------------------------------------------------
                # [공통 Quota 처리] 키 로테이션 + 재시도 or 전체 고갈 선언
                # ----------------------------------------------------------------
                if is_quota_error:
                    logger.warning(f"[ContentAnalysisAgent] {provider} Quota/Rate-Limit detected (Attempt {attempt+1}/{max_quota_tries}). Attempting key rotation...")
                    
                    # [동시성 개선] 실패한 키를 넘겨주어 중복 전환 방지 및 글로벌 고갈 감지
                    is_rotated = key_manager.rotate_key(provider, failed_key=current_api_key)
                    
                    if not is_rotated:
                        logger.error(f"[ContentAnalysisAgent] Global exhaustion reached for {provider}.")
                        raise QuotaExhaustedNoRetryError(f"{provider} quota globally exhausted. No retry.") from e
                    
                    if attempt < max_quota_tries - 1:
                        logger.info(f"[ContentAnalysisAgent] Switching to new {provider} key (Attempt {attempt+1}/{max_quota_tries})...")
                        # [BUG FIX] 진행 중이던 캐시 객체를 삭제해야 다음 번 get_cached_client에서 새로운 Key로 객체가 생성됨
                        cache_key = f"{provider}_{current_api_key}_{model_name}"
                        
                        try:
                            current_loop = asyncio.get_running_loop()
                            dict_key = (cache_key, current_loop)
                        except RuntimeError:
                            dict_key = (cache_key, None)
                            
                        if dict_key in self._loop_bound_clients:
                            del self._loop_bound_clients[dict_key]
                        
                        continue
                    else:
                        logger.error(f"[ContentAnalysisAgent] All {provider} keys exhausted.")
                        key_manager.mark_exhausted(provider)
                        raise QuotaExhaustedNoRetryError(f"{provider} quota exhausted. No retry.") from e
                
                # [비Quota 에러] tenacity가 재시도하도록 위로 전파
                logger.exception(f"{provider} Async API Error (Network/Transient)")
                
                # [강제 해제] Timeout이나 Network Error 발생 시 캐시된 세션(Client)이 죽은 소켓을 물고 있을 수 있음
                # 따라서 다음 Tenacity 재시도 시에는 무조건 새로운 Client 객체를 생성하게 만들어야 함.
                cache_key = f"{provider}_{current_api_key}_{model_name}"
                try:
                    current_loop = asyncio.get_running_loop()
                    dict_key = (cache_key, current_loop)
                except RuntimeError:
                    dict_key = (cache_key, None)
                    
                if dict_key in self._loop_bound_clients:
                    del self._loop_bound_clients[dict_key]
                    logger.info(f"[ContentAnalysisAgent] Invalidated cached client for {provider} due to network error.")
                    
                raise e
                
        # 루프가 정상 return 없이 종료된 경우 (이론상 미도달)
        raise QuotaExhaustedNoRetryError(f"All {provider} keys repeatedly failed.")


    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(lambda e: not isinstance(e, (QuotaExhaustedNoRetryError, ContentAnalysisAgent.SafetyBlockRetryError))),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def _aquery_llm_with_retry(self, prompt: str) -> str:
        """
        Helper method to wrap _aquery_llm with tenacity retry logic (Async).
        Handles transient network errors like WinError 10060/10054.
        QuotaExhaustedNoRetryError 시에는 즉시 중단 (불필요한 재시도 방지).
        """
        return await self._aquery_llm(prompt)

    def _parse_response(self, content, provider: str) -> dict:
        import re

        content = _normalize_llm_content(content)
        result_json = None

        # 1. Try to find JSON block wrapped in ```json ... ```
        json_block = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_block:
            try:
                result_json = json.loads(json_block.group(1))
            except json.JSONDecodeError:
                pass

        # 2. Try to find any JSON block wrapped in ``` ... ```
        if result_json is None:
            json_block = re.search(r"```\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_block:
                try:
                    result_json = json.loads(json_block.group(1))
                except json.JSONDecodeError:
                    pass
                
        # 3. Try to find the first valid JSON object in the text (greedy match from first { to last })
        if result_json is None:
            try:
                start_idx = content.find('{')
                end_idx = content.rfind('}')
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx+1]
                    result_json = json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # If all parsing attempts fail
        if result_json is None:
            logger.error("JSON Decode Error: Failed to extract valid JSON from LLM response")
            return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": "Error (JSON Parse Fail)"}
        
        # Reverted to 'spam_probability' as per user request for readability.
        spam_prob = float(result_json.get("spam_probability", 0.0))
        
        # Additional Safety: If label is SPAM but probability is low (e.g. 0.0 default), trust label?
        label = result_json.get("label", "HAM").upper()
        if label == "SPAM" and spam_prob < 0.6:
             pass
        classification_code = str(result_json.get("classification_code", ""))
        
        # New Parsing Logic: Map spam_code/ham_code to classification_code if missing
        if not classification_code:
            spam_code = result_json.get("spam_code")
            ham_code = result_json.get("ham_code")
            
            if spam_code and str(spam_code).lower() != "null":
                classification_code = str(spam_code)
            elif ham_code and str(ham_code).lower() != "null":
                classification_code = str(ham_code)
        
        # New Schema Logic: Prefer singular 'reason', fallback to joining 'reasons' if list exists
        reason = result_json.get("reason")
        if not reason:
            reasons = result_json.get("reasons", [])
            if isinstance(reasons, list) and reasons:
                reason = " | ".join(reasons)
            else:
                reason = f"{provider} Analysis"
        
        # Extract Token Usage (Simplified for brevity, similar to original)
        input_tokens = 0
        output_tokens = 0
        
        # Extract signals for HARD GATE enforcement
        signals = result_json.get("signals", {})
        harm_anchor = signals.get("harm_anchor", False)
        route_or_cta = signals.get("route_or_cta", False)
        is_impersonation = signals.get("is_impersonation", False)
        is_vague_cta = signals.get("is_vague_cta", False)
        is_personal_lure = signals.get("is_personal_lure", False)
        is_garbage_obfuscation = signals.get("is_garbage_obfuscation", False)
        
        # Ensure signals dict is up to date
        signals["is_impersonation"] = is_impersonation
        signals["is_vague_cta"] = is_vague_cta
        signals["is_personal_lure"] = is_personal_lure
        signals["is_garbage_obfuscation"] = is_garbage_obfuscation

        # ========== HARD GATE ENFORCEMENT ==========
        # Rule 1: harm_anchor = false → 무조건 HAM
        # Rule 2: 의도 명확(prob >= 0.85) + harm_anchor=true → SPAM (route_or_cta 무시)
        # Rule 3: 의도 애매(prob < 0.85) + harm_anchor=true → route_or_cta 확인 필요
        
        if not harm_anchor:
            # HARD GATE: harm_anchor가 false면 무조건 HAM
            is_spam = False
            if classification_code in ["0", "1", "2", "3", "10"]:
                classification_code = None
            label = result_json.get("label", "HAM").upper()
            if label == "SPAM":
                reason = f"[HARD GATE Override] harm_anchor=false → HAM 강제. 원래 reason: {reason}"
        elif harm_anchor and spam_prob >= 0.85:
            # 의도가 매우 명확 (prob >= 0.85): route_or_cta 확인 불필요 → SPAM 확정
            is_spam = True
            # route_or_cta가 false여도 SPAM 처리
        elif harm_anchor and not route_or_cta:
            # 의도가 애매 (prob < 0.85) + route_or_cta=false → HAM
            if spam_prob >= 0.6:
                # 의도는 있지만 확신은 부족, route_or_cta 없음 → HAM 처리하되 경고
                is_spam = False
                if classification_code in ["0", "1", "2", "3", "10"]:
                    classification_code = None
                reason = f"[HARD GATE] harm_anchor=true, prob={spam_prob:.2f} but route_or_cta=false → HAM. 원래 reason: {reason}"
            else:
                is_spam = False
                if classification_code in ["0", "1", "2", "3", "10"]:
                    classification_code = None
                reason = f"[HARD GATE] harm_anchor=true but route_or_cta=false → HAM. 원래 reason: {reason}"
        else:
            # harm_anchor=true AND route_or_cta=true → 확률 기반 판단
            if spam_prob < 0.4:
                is_spam = False
                if classification_code in ["0", "1", "2", "3", "10"]:
                    classification_code = None
            elif 0.4 <= spam_prob < 0.6:
                is_spam = None # Undecided, will be handled by HITL
                classification_code = "30" # HITL Required
                reason = f"[HITL] Probability ({spam_prob:.2f}) is ambiguous. Requesting user feedback."
            else: # >= 0.6
                is_spam = True

        # ========== HAM SIGNAL DEFENSE ==========
        # 학습 보호 시그널(is_impersonation, is_vague_cta, is_personal_lure, is_garbage_obfuscation)은
        # SPAM 확정 메시지에만 의미가 있음. HAM으로 판정된 경우 강제로 false로 초기화.
        if not is_spam:
            if any([signals.get("is_impersonation"), signals.get("is_vague_cta"), 
                    signals.get("is_personal_lure"), signals.get("is_garbage_obfuscation")]):
                logger.debug("[HAM Signal Defense] HAM 판정 메시지의 학습 보호 시그널을 false로 초기화")
            signals["is_impersonation"] = False
            signals["is_vague_cta"] = False
            signals["is_personal_lure"] = False
            signals["is_garbage_obfuscation"] = False

        return {
            "is_spam": is_spam,
            "spam_probability": spam_prob,
            "classification_code": classification_code,
            "reason": reason,
            "signals": signals,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    def _build_prompt(self, message: str, detected_pattern: str, context_data: dict) -> tuple[str, list]:
        guide_context = context_data.get("guide_context", "")
        rag_examples = context_data.get("rag_examples", [])
        
        # RAG 예시 섹션 구성
        # ChromaDB L2 distance: 0에 가까울수록 유사
        # [Intent-based RAG] 문장 유사도가 아닌 '의도 유사도'를 보기 위해 임계값을 0.35로 완화
        # 0.15 (문장 일치) -> 0.50 (의도 일치: 단어 달라도 맥락 유사하면 허용, 3-small 기준치 높임)
        distance_threshold = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.50"))
        
        rag_section = ""
        valid_examples = []
        
        if rag_examples:
            logger.info(f"    [RAG Examples] Top-2 forced + threshold ({distance_threshold}) from 3rd onwards")
            for idx, ex in enumerate(rag_examples):
                # [Fix] Map 'distance' from RAG service to 'score'
                score = ex.get('score', ex.get('distance', 999))
                
                # Top-2는 무조건 포함, 3번째부터는 distance <= threshold만 포함
                if idx < 2:
                    valid_examples.append({**ex, 'score': score})
                    logger.debug(f"    [RAG Examples]   - score: {score:.3f}, included (Top-{idx+1}, forced)")
                elif score <= distance_threshold:
                    valid_examples.append({**ex, 'score': score})
                else:
                    logger.debug(f"    [RAG Examples]   - score: {score:.3f}, excluded (threshold: {distance_threshold})")
            
            if valid_examples:
                rag_section = "\n[Reference Context - Similar Intent Examples]\n"
                rag_section += "아래는 유사한 의도(Intent)를 가진 과거 메시지 판정 결과입니다. 참고 자료로만 활용하세요.\n"
                rag_section += "\n[CRITICAL - Near-Duplicate 판정 규칙]\n"
                rag_section += "아래 조건 중 하나라도 해당하면 해당 예시를 '참고' 수준이 아니라 '강제 준수' 대상으로 취급한다:\n"
                rag_section += "  1) normalized_text가 분석 대상 메시지와 exact match인 경우\n"
                rag_section += "  2) 유사도 score < 0.05 이고, 토큰/형태 유사도도 매우 높은 경우 (사실상 동일 메시지)\n"
                rag_section += "이 경우, 해당 예시의 판정(label)을 그대로 따르고, reason 필드에 '과거 동일 사례 판정 적용' 임을 반드시 명시하라.\n"
                for i, ex in enumerate(valid_examples, 1):
                    msg_preview = ex.get('message', '')[:100]
                    category = ex.get('category', 'N/A')
                    reason = ex.get('reason', 'N/A')
                    
                    rag_section += f"\n예시 {i} (유사도: {ex.get('score', 0):.3f}):\n"
                    rag_section += f"  메시지: \"{msg_preview}{'...' if len(ex.get('message', '')) > 100 else ''}\"\n"
                    rag_section += f"  판정: {ex.get('label', 'SPAM')} (code: {ex.get('code', '')})\n"
                    rag_section += f"  카테고리: {category}\n"
                    rag_section += f"  근거: {reason}\n"
                
                logger.info(f"    [RAG Examples] {len(valid_examples)} examples included in prompt (threshold: {distance_threshold})")
                
                # [User Request] Log the exact context injected into prompt
                logger.debug(f"    [RAG Examples Injected Content]:\n{rag_section}")
        
        prompt_text = f"""
너는 스팸 분류 전문가다. 판단 기준은 아래 Spam Guide에만 존재한다.

--------------------------------------------------
[Message]
\"\"\"{message}\"\"\"

[Spam Guide]
{guide_context}
{rag_section}

--------------------------------------------------

[CRITICAL] 너는 텍스트만 분석한다. URL의 '존재 여부'나 '이동 경로'는 판단 근거가 아니다.
단, 텍스트로서의 **URL 난독화 패턴**(특수문자 삽입, 기이한 도메인 형태, 띄어쓰기 등)은 **강력한 스팸 회피 시그널(Textual Signal)**로 간주해야 한다.
외국어 메시지는 언어 장벽에 상관없이 그 속에 숨겨진 **'의도(Intent)'와 '회피 목적의 난독화(Obfuscation)'**가 있는지 분석하라.

[PROCEDURE]
Step 1. HARD GATE 확인 → harm_anchor = false 이면 무조건 HAM (label="HAM")

Step 2. harm_anchor 판정 → Guide 2.2 기준 (URL 무시, 텍스트만, 도박/성인/사기/어뷰즈 의도가 명확해야 true)

Step 3. 의도 명확도 판정 → spam_probability로 표현 (0.85 이상이면 의도가 매우 명확)

Step 4. 구조적 기만(Structural Impersonation) 여부 판정 → is_impersonation
   - 단순히 특정 단어가 아닌, '공공기관의 통보 형식'이나 '기업의 공식 서비스 흐름' 등 **정상적인 문장 구조와 레이아웃을 정교하게 모방**한 경우 true

Step 4-1. 모호한 행동 유도(Vague CTA) 여부 판정 → is_vague_cta
   - 텍스트 자체가 범용어/모호한 표현으로만 구성되어 있고, 특정 문맥 없이 클릭만을 유도하는 패턴인 경우 true
   - 이러한 패턴은 CNN 모델이 일반적인 권유 문구와 스팸을 구분하기 어렵게 만듦

Step 4-2. 사적 관계/경조사 위장 (Personal Lure) 판단 → is_personal_lure
   - 안부 인사, 부고, 청첩장 등 지인 간의 일상적인 **문장 나열 패턴(Sequential Pattern)**을 100% 모방한 경우 true

Step 4-3. 필터 회피용 벡터 노이즈 (Garbage Obfuscation) 판단 → is_garbage_obfuscation
   - 필터 우회를 위해 의미 없는 문자 조각(`l0`, `ㄹ`, `R3993` 등)이나 파편화된 코드가 섞인 경우 true
   - 이는 CNN 모델의 임베딩 레이어에서 **고주파 노이즈**로 작용하여 특징 추출을 방해함

Step 5. [CNN 모델 강건성(Robustness) 유지 안내]
   is_impersonation / is_vague_cta / is_personal_lure / is_garbage_obfuscation 네 시그널은 **CNN의 합성곱 필터(Convolutional Filter)가 정상 문맥을 '악성 패턴'으로 잘못 정의하는 것을 방지**하기 위해 추출합니다.
   ⚠️ 중요: 이 시그널은 **메시지가 SPAM으로 확정된 경우에만** 의미를 가집니다. HAM 메시지에서는 항상 false로 설정하세요.
   이 시그널이 true이면 해당 메시지는 즉시 차단되지만, **모델 학습 데이터(Training Set)에서는 제외**됩니다.

   **판단 기준 (SPAM 확정 후 적용):** "이 메시지의 구조적 패턴이 CNN 학습에 사용될 경우, 향후 유사한 구조의 정상 메시지를 오탐(False Positive)할 위험이 있는가?"
   - 사칭: 정상 업무의 '알림 구조'를 스팸 특징으로 학습 → 유사한 정상 알림 오탐 위험
   - Vague CTA: 보편적인 '권유/안내 패턴'을 스팸 특징으로 학습 → 일반적인 제안 메시지 오탐 위험
   - Personal Lure: 지인 간 '안부/경조사 문장 흐름'을 스팸 특징으로 학습 → 실제 안부 메시지 오탐 위험
   - Garbage: 무의미한 벡터 노이즈가 특징 맵(Feature Map)을 왜곡 → 모델의 일반화 성능 저하

Step 6. SPAM 확정 조건:
   - 의도가 매우 명확 (spam_probability >= 0.85): harm_anchor=true면 SPAM (route_or_cta 무시)
   - 의도가 애매 (spam_probability < 0.85): harm_anchor=true AND route_or_cta=true 일 때만 SPAM

[OUTPUT — JSON ONLY]
{{
"label": "HAM|SPAM",
"ham_code": "HAM-1|HAM-2|HAM-3|null",
"spam_code": "0|1|2|3|null",
"spam_probability": 0.0,
"reason": "한국어로 판단 근거 작성. 특히 CNN 모델이 오해할 수 있는 '문장 구조적 특징'을 언급할 것",
"signals": {{ "harm_anchor": false, "route_or_cta": false, "is_impersonation": false, "is_vague_cta": false, "is_personal_lure": false, "is_garbage_obfuscation": false }}
}}
"""
        return prompt_text, valid_examples

    def check(self, message: str, stage1_result: dict) -> dict:
        """
        Stage 2: RAG + LLM (Sync Version)
        """
        # 메시지 원문 로그
        logger.debug(f"분석 시작 | msg={message[:80]}{'...' if len(message) > 80 else ''}")
        
        try:
            # 1. Intent Summary Generation (Use loop to run the async version or simplified sync)
            # For check (sync), we wrap the async call
            # 1. Intent Summary Generation (Directly use agenerate_intent_summary if possible, else sync fallback)
            import asyncio
            try:
                # check is sync, but we want the high-quality intent summary from agenerate
                intent_summary = self.generate_intent_summary(message)
            except Exception as e:
                logger.warning(f"Sync Intent Summary Generation Failed: {e}")
                intent_summary = f"Intent analysis of: {message[:50]}..."

            logger.info(f"Intent Summary: {intent_summary[:120]}...")

            # 2. RAG Retrieval (guide + FN examples)
            context_data = self._retrieve_context(message, intent_summary)
            
            # [Telemetry] Calculate Distance Metrics (Top 1/2 + Gap)
            rag_examples = context_data.get('rag_examples', [])
            d1, d2, gap = 9.9, 9.9, 0.0
            if len(rag_examples) >= 1:
                d1 = rag_examples[0].get('score', rag_examples[0].get('distance', 9.9))
                if len(rag_examples) >= 2:
                    d2 = rag_examples[1].get('score', rag_examples[1].get('distance', 9.9))
                    gap = d2 - d1
            logger.info(f"RAG Metrics | Top1={d1:.4f} | Top2={d2:.4f} | Gap={gap:.4f}")

            # 2. LLM Inference
            detected_pattern = stage1_result.get("detected_pattern", "None")
            prompt, valid_examples = self._build_prompt(message, detected_pattern, context_data)
            
            # [Telemetry] RAG Injection Stats
            rag_retrieved = len(rag_examples)
            rag_injected = len(valid_examples)
            has_guide = bool(context_data.get('guide_context'))
            
            # Label Distribution & IDs
            spam_hits = sum(1 for ex in valid_examples if ex.get('label') == 'SPAM')
            ham_hits = sum(1 for ex in valid_examples if ex.get('label') == 'HAM')
            injected_ids = [ex.get('id', 'unk') for ex in valid_examples]
            
            logger.info(f"프롬프트 생성 완료 | RAG Guide={'O' if has_guide else 'X'} | rag_retrieved={rag_retrieved}, rag_injected={rag_injected}")
            logger.info(f"RAG Details | injected_labels=SPAM:{spam_hits}/HAM:{ham_hits} | injected_ids={injected_ids}")
            
            try:
                # Bridge sync check to async LLM call safely
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    current_loop = None

                if current_loop and current_loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                    content = current_loop.run_until_complete(self._aquery_llm_with_retry(prompt))
                else:
                    content = asyncio.run(self._aquery_llm_with_retry(prompt))
                    
            except self.SafetyBlockRetryError as e:
                logger.warning(f"Safety filter blocked initial request. Retrying WITHOUT RAG examples.")
                # Clear RAG examples and rebuild prompt
                context_data['rag_examples'] = []
                prompt_retry, _ = self._build_prompt(message, detected_pattern, context_data)
                
                try:
                    if current_loop and current_loop.is_running():
                        content = current_loop.run_until_complete(self._aquery_llm_with_retry(prompt_retry))
                    else:
                        content = asyncio.run(self._aquery_llm_with_retry(prompt_retry))
                except self.SafetyBlockRetryError:
                    logger.warning("[Gemini] Response blocked by safety filters EVEN WITHOUT RAG. Returning fallback SPAM verdict.")
                    content = json.dumps({
                        "label": "SPAM",
                        "spam_probability": 0.99,
                        "classification_code": "2",
                        "reason": "Safety Filter Blocked: Content was flagged as prohibited (likely highly offensive or explicit) even after removing context. Assuming High-Risk SPAM.",
                        "signals": {"harm_anchor": True, "route_or_cta": True, "is_impersonation": False, "is_vague_cta": False, "is_personal_lure": False}
                    })
                except Exception as retry_e:
                    logger.error(f"Sync bridging retry for LLM failed: {retry_e}")
                    raise retry_e
                    
            except Exception as e:
                logger.error(f"Sync bridging for LLM failed: {e}")
                # Fallback to a legacy sync query if needed, or just re-raise
                raise e
            
            # LLM 응답 로그
            logger.debug(f"LLM 응답: {content[:1000]}{'...' if len(content) > 1000 else ''}")
            
            result = self._parse_response(content, os.getenv("LLM_PROVIDER", "OPENAI"))
            
            # 판정 결과 로그 (표준화된 형식)
            is_spam = result.get('is_spam')
            verdict = "SPAM" if is_spam else ("HITL" if is_spam is None else "HAM")
            logger.info(f"판정완료 | {verdict} | code={result.get('classification_code')} | prob={result.get('spam_probability')}")
            logger.info(f"  - Reason: {result.get('reason')}")
            
            return result
            
        except Exception as e:
            error_msg = str(e).lower()
            if "quota" in error_msg or "exhausted" in error_msg or "429" in error_msg:
                logger.error(f"LLM 분석 중 Quota 소진 오류 발생: {e}")
                return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": f"Quota Exhausted Error: {e}"}
            else:
                logger.exception(f"LLM 분석 중 오류 발생: {e}")
                return {"is_spam": False, "spam_probability": 0.99, "classification_code": "2", "reason": f"Error (LLM Fail / Safety Block Retry Failed): {e}"}

    from typing import Callable, Awaitable, Optional

    async def acheck(self, message: str, stage1_result: dict, status_callback: Optional[Callable[[str], Awaitable[None]]] = None, content_context: dict = None) -> dict:
        """
        Stage 2: RAG + LLM (Async Version with Callbacks)
        Optional: content_context (If provided, skips internal RAG retrieval)
        """
        import asyncio
        loop = asyncio.get_running_loop()
        
        # 메시지 원문 로그 (DEBUG로 변경)
        logger.debug(f"분석 시작 (async) | msg={message[:80]}{'...' if len(message) > 80 else ''}")
        
        try:
            context_data = {}
            
            # [Optimization] Use injected context if available (Batch Mode)
            if content_context:
                logger.debug("Using injected batch context (Skipping RAG retrieval)")
                context_data = content_context
                
            else:
                # 1. RAG Retrieval (guide + FN examples)
                if status_callback:
                    await status_callback("🧠 의도 파악 중...")
                
                # 0. Generate Intent Summary (Direct Async Call)
                # [Fix] Don't use run_in_executor for an async method wrapper
                intent_summary = await self.agenerate_intent_summary(message)
                logger.info(f"Intent Summary: {intent_summary[:120]}...")

                # 1. RAG Retrieval (guide + FN examples, Run in thread to avoid blocking)
                if status_callback:
                    await status_callback("🔍 문맥 검색 중... (RAG + FN Examples)")
                
                context_data = await loop.run_in_executor(None, lambda: self._retrieve_context(message, intent_summary))
            
            # [Telemetry] Calculate Distance Metrics (Top 1/2 + Gap)
            rag_examples = context_data.get('rag_examples', [])
            d1, d2, gap = 9.9, 9.9, 0.0
            if len(rag_examples) >= 1:
                d1 = rag_examples[0].get('score', rag_examples[0].get('distance', 9.9))
                if len(rag_examples) >= 2:
                    d2 = rag_examples[1].get('score', rag_examples[1].get('distance', 9.9))
                    gap = d2 - d1
            logger.info(f"RAG Metrics | Top1={d1:.4f} | Top2={d2:.4f} | Gap={gap:.4f}")
            
            # 2. LLM Inference
            if status_callback:
                await status_callback("🧠 AI 정밀 분석 중...")
            
            logger.debug("Building prompt...")
            detected_pattern = stage1_result.get("detected_pattern", "None")
            prompt, valid_examples = self._build_prompt(message, detected_pattern, context_data)
            
            # [Telemetry] RAG Injection Stats
            rag_retrieved = len(rag_examples)
            rag_injected = len(valid_examples)
            has_guide = bool(context_data.get('guide_context'))

            # Label Distribution & IDs
            spam_hits = sum(1 for ex in valid_examples if ex.get('label') == 'SPAM')
            ham_hits = sum(1 for ex in valid_examples if ex.get('label') == 'HAM')
            injected_ids = [ex.get('id', 'unk') for ex in valid_examples]

            logger.info(f"프롬프트 생성 완료 | RAG Guide={'O' if has_guide else 'X'} | rag_retrieved={rag_retrieved}, rag_injected={rag_injected}")
            logger.info(f"RAG Details | injected_labels=SPAM:{spam_hits}/HAM:{ham_hits} | injected_ids={injected_ids}")
            
            logger.debug(f"Prompt built, length: {len(prompt)} chars")
            
            logger.debug("Calling LLM...")
            # Run async LLM call with retry
            try:
                content = await self._aquery_llm_with_retry(prompt)
            except self.SafetyBlockRetryError as e:
                logger.warning("Safety filter blocked initial request (async). Retrying WITHOUT RAG examples.")
                if status_callback:
                    await status_callback("⚠️ 안전 필터 차단됨. RAG 예시 제외 후 재분석 시도 중...")
                
                # Clear RAG examples and rebuild prompt
                context_data['rag_examples'] = []
                prompt_retry, _ = self._build_prompt(message, detected_pattern, context_data)
                
                # Retry Call
                try:
                    content = await self._aquery_llm_with_retry(prompt_retry)
                except self.SafetyBlockRetryError:
                    logger.warning("[Gemini] Response blocked by safety filters EVEN WITHOUT RAG. Returning fallback SPAM verdict.")
                    content = json.dumps({
                        "label": "SPAM",
                        "spam_probability": 0.99,
                        "classification_code": "2",
                        "reason": "Safety Filter Blocked: Content was flagged as prohibited (likely highly offensive or explicit) even after removing context. Assuming High-Risk SPAM.",
                        "signals": {"harm_anchor": True, "route_or_cta": True, "is_impersonation": False, "is_vague_cta": False, "is_personal_lure": False}
                    })
            except QuotaExhaustedNoRetryError as e:
                logger.error(f"Async LLM query failure (Quota Exhausted): {e}")
                return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": f"Error: {e}"}
            except Exception as e:
                logger.error(f"Async LLM query failure: {e}")
                return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": f"Error: {e}"}
            
            # LLM 응답 로그
            logger.debug(f"LLM 응답: {content[:1000]}{'...' if len(content) > 1000 else ''}")
            
            result = self._parse_response(content, os.getenv("LLM_PROVIDER", "OPENAI"))
            
            # 판정 결과 로그 (표준화된 형식)
            is_spam = result.get('is_spam')
            verdict = "SPAM" if is_spam else ("HITL" if is_spam is None else "HAM")
            logger.info(f"판정완료 | {verdict} | code={result.get('classification_code')} | prob={result.get('spam_probability')}")
            logger.info(f"  - Reason: {result.get('reason')}")
            
            if status_callback:
                await status_callback(f"✅ 분석 완료 (판정: {verdict})")
                
            return result
            
        except Exception as e:
            logger.exception(f"Async LLM 분석 중 오류 발생: {e}")
            if status_callback:
                await status_callback(f"⚠️ 오류 발생: {str(e)}")
            return {"is_spam": False, "spam_probability": 0.99, "classification_code": "2", "reason": f"Error (LLM Fail / Safety Block Retry Failed): {e}"}

    async def check_batch(self, messages: list[str], stage1_results: list[dict]) -> list[dict]:
        """
        Stage 2 (Batch) implementation
        Process multiple messages appropriately.
        """
        results = []
        
        # Simple iterative processing for now. 
        # Ideally, this could uses LLM batch APIs or concurrent execution,
        # but for consistent results with the single check logic, iteration is safest.
        for i, message in enumerate(messages):
            s1_result = stage1_results[i] if i < len(stage1_results) else {}
            try:
                # Reuse the existing check logic
                # Note: check() is synchronous in this class currently (uses standard calls).
                # If we want true async, we should refactor check() to be async or run_in_executor.
                # Since get_chat_model returns correct client, we stick to sequential for reliability first.
                result = self.check(message, s1_result)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch Item Error: {e}")
                results.append({
                    "is_spam": False, 
                    "reason": f"Error in batch processing: {str(e)}",
                    "classification_code": "ERROR"
                })
        
        return results

    def _get_rag_service(self):
        """Helper to get RAG service instance"""
        from app.services.spam_rag_service import get_spam_rag_service
        return get_spam_rag_service()

    async def prepare_batch_contexts(self, messages: list[str]) -> list[dict]:
        """
        [Batch Optimization]
        1. Generate Intent Summaries for all messages in parallel (Restored).
        2. Perform Batch RAG Search using Intent Summaries.
        3. Retrieve generic spam guide (Once).
        
        Returns:
            List of context data dicts corresponding to messages.
        """
        import asyncio
        loop = asyncio.get_running_loop()
        
        # 1. Intent Summary Generation (Parallel)
        summary_tasks = [self.agenerate_intent_summary(msg) for msg in messages]
        intent_summaries = await asyncio.gather(*summary_tasks)
        
        if len(intent_summaries) > 1:
            logger.info(f"Generated {len(intent_summaries)} intent summaries for batch.")
        else:
            logger.debug(f"Generated intent summary for JIT process.")
        
        # 2. Batch RAG Search
        rag_results_list = []
        try:
            service = self._get_rag_service()
            # [Optimization] Batch Embedding + Query using Intent Summaries
            rag_results_list = await loop.run_in_executor(
                None, 
                lambda: service.search_similar_batch(intent_summaries, k=3)
            )
        except Exception as e:
            logger.error(f"Batch RAG Search Error: {e}")
            # Fallback to empty results
            rag_results_list = [{"hits": []}] * len(messages)
        
        # 3. Load Generic Guide (Once)
        full_guide = self._load_full_guide()
        
        # 4. Assemble Contexts
        contexts = []
        for i, rag_res in enumerate(rag_results_list):
            hits = rag_res.get("hits", [])
            
            contexts.append({
                "guide_context": full_guide,
                "rag_examples": hits,
                "intent_summary": intent_summaries[i] 
            })
            
        return contexts

    def _get_chat_model(self):
        """
        Returns a LangChain Chat Model based on valid environment variables.
        """
        provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
        
        # Local Imports for Lazy Loading
        from langchain_openai import ChatOpenAI
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_anthropic import ChatAnthropic

        if provider == "GEMINI":
            api_key = key_manager.get_key("GEMINI")
            safety_settings = {
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
            return ChatGoogleGenerativeAI(
                model=self.model_name if "gemini" in self.model_name else "gemini-1.5-flash",
                google_api_key=api_key,
                temperature=0.0,  # 분류 작업에 적합한 가장 낮은 temperature
                safety_settings=safety_settings
            )
        elif provider == "CLAUDE":
            api_key = key_manager.get_key("CLAUDE")
            return ChatAnthropic(
                model=self.model_name if "claude" in self.model_name else "claude-3-haiku-20240307",
                anthropic_api_key=api_key,
                temperature=0.0  # 분류 작업에 적합한 가장 낮은 temperature
            )
        else: # OPENAI
            api_key = key_manager.get_key("OPENAI")
            return ChatOpenAI(
                model=self.model_name,
                api_key=api_key,
                temperature=0.0  # 분류 작업에 적합한 가장 낮은 temperature
            )



    async def generate_final_summary(self, message: str, content_result: dict, url_result: dict = None) -> str:
        """
        Generates a final executive summary based on both Content and URL analysis results.
        """
        prompt = f"""
        You are a Spam Prevention Expert. Synthesize the analysis results below into a 3-line final verdict for the user.

        [User Message]
        {message}

        [Content Analysis Result]
        - Verdict: {'SPAM' if content_result.get('is_spam') else 'HAM'}
        - Reason: {content_result.get('reason')}

        [URL Analysis Result]
        {'- N/A (URL not found or not analyzed)' if not url_result else f"- Verdict: {'SPAM' if url_result.get('is_spam') else 'SAFE'}"}
        {'- Reason: ' + url_result.get('reason') if url_result else ''}
        {'- Details: ' + str(url_result.get('details')) if url_result else ''}

        [Task]
        Write a friendly but firm final summary in Korean.
        1. **Final Conclusion**: Start with a clear emoji (🚫 for Spam, ✅ for Safe, ⚠️ for Caution).
        2. **Synthesis**: Explain *why* based on the combination of text and URL evidence. (e.g., "Text seemed safe, but the URL leads to a known phishing site.")
        3. **Action**: Tell the user exactly what to do (e.g., "Do not click," "Block this number," or "Safe to ignore").

        Provide a comprehensive and helpful summary without strict length limits.
        """

        try:
            llm = self._get_chat_model()
            # Since this is a single call (not stream), we use .invoke or generic call
            from langchain_core.messages import HumanMessage
            # Add retry for summary generation
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception(lambda e: not isinstance(e, QuotaExhaustedNoRetryError)),
                reraise=True
            )
            async def call_summary_llm():
                try:
                    provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
                    if key_manager.is_quota_exhausted(provider):
                        raise QuotaExhaustedNoRetryError(f"{provider} quota globally exhausted. No retry.")
                    # [Fix] Add explicit 45s timeout
                    import asyncio
                    try:
                        response = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                    except asyncio.TimeoutError as e:
                        logger.warning(f"[{provider}] Summary LLM Timeout occurred. Attempting fallback.")
                        sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-flash-lite-preview")
                        fallback_key = key_manager.get_key("GEMINI")
                        if fallback_key:
                            fallback_llm = self._get_cached_client("GEMINI", fallback_key, sub_model)
                            try:
                                response = await asyncio.wait_for(fallback_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                            except Exception:
                                raise Exception("Async Summary LLM Timeout (Fallback failed)") from e
                        else:
                            raise Exception("Async Summary LLM Timeout") from e
                        
                    key_manager.report_success(provider)
                    return response
                except Exception as e:
                    error_msg = str(e).lower()
                    provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
                    
                    # [Fix] Explicit type check for Google API errors (Gemini)
                    is_google_quota_error = False
                    if provider == "GEMINI":
                        try:
                            import google.api_core.exceptions
                            if isinstance(e, (google.api_core.exceptions.ResourceExhausted, google.api_core.exceptions.TooManyRequests)):
                                is_google_quota_error = True
                        except ImportError:
                            pass

                    if is_google_quota_error or "quota" in error_msg or "rate" in error_msg or "429" in error_msg or "limit" in error_msg or "resource exhausted" in error_msg:
                        logger.warning(f"[ContentAgent] Summary Generation Quota Detected. Error: {error_msg}")
                        logger.warning(f"[ContentAgent] {provider} Quota Exceeded. Rotating key...")
                        
                        # Get current key to mark as failed
                        current_key = key_manager.get_key(provider)
                        is_rotated = key_manager.rotate_key(provider, failed_key=current_key)
                        
                        if not is_rotated:
                            logger.error(f"[ContentAgent] Global exhaustion reached for {provider} during summary.")
                            raise QuotaExhaustedNoRetryError(f"{provider} quota globally exhausted. No retry.") from e
                        
                        # 쿨다운 대기 없이 즉시 다음 키로 시도
                        pass
                        # IMPORTANT: Since llm instance is created outside, we might need to recreate it or 
                        # just rely on the fact that next call to _get_chat_model (if we were calling it inside) would get new key.
                        # BUT here `llm` is already instantiated `llm = self._get_chat_model()`.
                        # We need to refresh `llm` instance with new key!
                        # However, we cannot easily reassign outer scope `llm` variable from inner function without `nonlocal`
                        # OR we can just call `self._get_chat_model().ainvoke` directly inside here.
                        new_llm = self._get_chat_model()
                        try:
                            response = await asyncio.wait_for(new_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                        except asyncio.TimeoutError as e:
                            logger.warning(f"[ContentAgent] Rotated Summary LLM Timeout. Attempting fallback.")
                            sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-flash-lite-preview")
                            fallback_key = key_manager.get_key("GEMINI")
                            if fallback_key:
                                fallback_llm = self._get_cached_client("GEMINI", fallback_key, sub_model)
                                try:
                                    response = await asyncio.wait_for(fallback_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                                except Exception:
                                    raise Exception("Async Summary LLM Timeout after rotation (Fallback failed)") from e
                            else:
                                raise Exception("Async Summary LLM Timeout after rotation") from e
                            
                        key_manager.report_success(provider)
                        return response
                        
                    raise e
                
            response = await call_summary_llm()
            
            # Extract content robustly
            final_content = ""
            if hasattr(response, 'content'):
                content = response.content
                if isinstance(content, list) and len(content) > 0:
                     # Handle list of blocks (e.g. Anthropic)
                     if isinstance(content[0], dict) and 'text' in content[0]:
                         final_content = content[0]['text']
                     else:
                         final_content = str(content) # Fallback if structure unknown
                else:
                    final_content = str(content) # Valid string
                
            elif isinstance(response, list) and len(response) > 0:
                 if isinstance(response[0], dict) and 'text' in response[0]:
                     final_content = response[0]['text']
                 elif hasattr(response[0], 'content'):
                     final_content = response[0].content
            else:
                 final_content = str(response)
            
            logger.info(f"Final Summary: {final_content}")
            return final_content

        except Exception as e:
            logger.error(f"Summary Generation Error: {e}")
            return "종합 결과 요약 생성 중 오류가 발생했습니다."

    async def agenerate_intent_summary(self, message: str) -> str:
        """
        Asynchronous version of intent summary generation with retries.
        """
        prompt = f"""
        [GOAL]
        Understand the input message and summarize its "Core Intent" in 1-2 sentences.
        Remove all variable values (amounts, phone numbers, URLs, specifics) and focus on the *Pattern* and *Action*.
        
        [INPUT]
        {message}
        
        [OUTPUT RULES]
        - Output the intent summary ONLY. No headers, no labels, no markdown, no extra explanation.
        - Use slash-separated format: [Intent] / [Tactics] / [Action Request]
        - Do NOT include any PII or specific numbers.
        - BAD example: "**Principal Intent / Tactics / Action Request** Illegal Loan..."
        - GOOD example: "Illegal Loan Advertisement / Immediate Deposit Promise / Request for contact via personal number"
        """
        
        try:
            raw = await self._aquery_llm_with_retry(prompt)
            return _clean_intent_summary(raw)
        except QuotaExhaustedNoRetryError as e:
            logger.error(f"Intent Summary Generation Quota Exhausted: {e}")
            return "Error generating intent summary: Quota exhausted"
        except Exception as e:
            logger.error(f"Intent Summary Generation Error: {e}")
            return "Error generating intent summary"

    def generate_intent_summary(self, message: str) -> str:
        """
        Public method to generate 'Judgement Semantic Unit' (Intent Summary).
        Used by main.py for saving RAG examples and internally for analysis.
        (Synchronous version for compatibility)
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we are in a thread with a loop running, we use run_coroutine_threadsafe
                return asyncio.run_coroutine_threadsafe(self.agenerate_intent_summary(message), loop).result()
            else:
                return asyncio.run(self.agenerate_intent_summary(message))
        except Exception:
            # Fallback for sync environments without a running loop
            return f"Intent analysis of: {message[:50]}..."
