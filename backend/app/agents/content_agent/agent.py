import os
import json
import logging
import time
import asyncio

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log
from langchain_core.messages import HumanMessage

from app.core.logging_config import get_logger
from app.core.llm_manager import key_manager

load_dotenv(override=True) # Load .env file (override system variables)

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
            rag_examples = self._search_spam_rag(intent_summary, k=3)
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
            logger.info(f"    [Info] Try loading Spam Guide from: {guide_path}")
            with open(guide_path, "r", encoding="utf-8") as f:
                spam_guide_content = f.read()
                self._full_guide_cache = spam_guide_content
                return self._full_guide_cache
        except Exception as e:
            try: 
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                guide_path = os.path.join(base_dir, "data/spam_guide.md")
                logger.info(f"    [Info] Try loading Spam Guide from fallback: {guide_path}")
                with open(guide_path, "r", encoding="utf-8") as f:
                    spam_guide_content = f.read()
                    self._full_guide_cache = spam_guide_content
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
                        is_fallback_used = False
                        fallback_model_used = None
                        # [Fix] Add explicit 45s timeout to prevent 300s hang
                        try:
                            response = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                        except asyncio.TimeoutError as e:
                            logger.warning(f"[{provider}] LLM Timeout occurred (45s). Attempting Fallback to Sub Model.")
                            raw_sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-pro-preview")
                            sub_model = raw_sub_model.strip().strip("'").strip('"') if raw_sub_model else "gemini-3.1-pro-preview"
                            if not sub_model:
                                sub_model = "gemini-3.1-pro-preview"
                            
                            fallback_key = key_manager.get_key("GEMINI")
                            if fallback_key:
                                fallback_llm = self._get_cached_client("GEMINI", fallback_key, sub_model)
                                try:
                                    response = await asyncio.wait_for(fallback_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                                    is_fallback_used = True
                                    fallback_model_used = sub_model
                                except Exception as fallback_e:
                                    logger.error(f"[Fallback] Sub model also failed: {fallback_e}")
                                    raise Exception("Async LLM Timeout (Fallback failed)") from e
                            else:
                                raise Exception("Async LLM Timeout (No fallback key)") from e
                        
                        key_manager.extract_and_add_tokens(provider, response)
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
                    response = await llm.ainvoke([HumanMessage(content=prompt)])
                    key_manager.extract_and_add_tokens(provider, response)
                    content = _normalize_llm_content(response.content)
                    
                else: # OPENAI
                    current_api_key = api_key
                    model_name = self.model_name
                    
                    llm = self._get_cached_client(provider, current_api_key, model_name)
                    response = await llm.ainvoke([HumanMessage(content=prompt)])
                    key_manager.extract_and_add_tokens(provider, response)
                    content = _normalize_llm_content(response.content)
                # All providers
                key_manager.report_success(provider)
                if locals().get("is_fallback_used", False) and locals().get("fallback_model_used"):
                    content = f"__FALLBACK_{fallback_model_used}__\n" + content
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
        stop=stop_after_attempt(1),
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

        fallback_model = None
        if content.startswith("__FALLBACK_"):
            parts = content.split("__\n", 1)
            if len(parts) == 2:
                fallback_info = parts[0].replace("__FALLBACK_", "")
                fallback_model = fallback_info
                content = parts[1]
                
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
                
        reason_str = str(result_json.get("reason", ""))
        if fallback_model and reason_str:
            result_json["reason"] = f"[Content_Fallback: {fallback_model}] " + reason_str
        
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
        
        # Ensure signals dict is up to date
        signals["harm_anchor"] = harm_anchor
        signals["route_or_cta"] = route_or_cta

        # ========== TRUST SPAM GUIDE & LLM ==========
        # Spam Guide 기반 프롬프트를 전적으로 신뢰합니다.
        
        label = result_json.get("label", "HAM").upper()
        if label == "SPAM":
            if spam_prob >= 0.6:
                is_spam = True
            elif 0.4 <= spam_prob < 0.6:
                is_spam = None # Undecided, will be handled by HITL
                classification_code = "30" # HITL Required
                if not reason.startswith("[HITL]"):
                    reason = f"[HITL] Probability ({spam_prob:.2f}) is ambiguous. Requesting user feedback. | {reason}"
            else:
                is_spam = False
                if classification_code in ["0", "1", "2", "3", "10"]:
                    classification_code = None
                reason = f"[Override] LLM output SPAM but probability is too low ({spam_prob:.2f}). Forced HAM. | {reason}"
        elif label == "HOLD_SHORT":
            is_spam = "HOLD_SHORT"
        else:
            is_spam = False
            if classification_code in ["0", "1", "2", "3", "10"]:
                classification_code = None

        obfuscated_urls = result_json.get("obfuscated_urls", [])
        if not isinstance(obfuscated_urls, list):
            obfuscated_urls = []

        return {
            "is_spam": is_spam,
            "spam_probability": spam_prob,
            "classification_code": classification_code,
            "reason": reason,
            "signals": signals,
            "obfuscated_urls": obfuscated_urls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    def _build_prompt(self, message: str, detected_pattern: str, context_data: dict) -> tuple[str, list]:
        guide_context = context_data.get("guide_context", "")
        rag_examples = context_data.get("rag_examples", [])
        
        # RAG 예시 섹션 구성
        # ChromaDB L2 distance: 0에 가까울수록 유사
        # [Intent-based RAG] OpenAI text-embedding-3-small은 벡터 분산이 큼. 0.85 ~ 0.95 권장.
        # (문장 일치 0.2 ~ 0.4 / 의도(맥락) 유사 0.7 ~ 0.9 / 무관 1.1 이상)
        distance_threshold = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.95"))
        
        rag_section = ""
        valid_examples = []
        
        if rag_examples:
            logger.info(f"    [RAG Examples] Strictly filtering by threshold ({distance_threshold})")
            for idx, ex in enumerate(rag_examples):
                # [Fix] Map 'distance' from RAG service to 'score'
                score = ex.get('score', ex.get('distance', 999))
                
                # 모든 예시에 대해 임계값 기준 적용 (Top-1, Top-2 강제 주입 제거)
                if score <= distance_threshold:
                    valid_examples.append({**ex, 'score': score})
                    logger.debug(f"    [RAG Examples]   - score: {score:.3f}, included (Threshold <= {distance_threshold})")
                else:
                    logger.debug(f"    [RAG Examples]   - score: {score:.3f}, excluded (Threshold > {distance_threshold})")
            
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
        
        import datetime
        current_date_str = datetime.datetime.now().strftime("%Y년 %m월 %d일")
        
        prompt_text = f"""
너는 스팸 분류 전문가다. 판단 기준은 아래 Spam Guide에만 존재한다.
(System Info: 오늘 날짜는 {current_date_str} 이다. 메시지의 날짜가 과거/미래인지 판단할 때 반드시 이 기준일을 사용하라.)

--------------------------------------------------
[Message]
\"\"\"{message}\"\"\"

[Spam Guide]
{guide_context}
{rag_section}

--------------------------------------------------

[CRITICAL INSTRUCTIONS] 
1. 텍스트 분석 집중: 오직 텍스트 문맥과 구조만 분석하라. URL의 실제 접속 가능성이나 목적지는 고려하지 않는다.
2. 가이드 절대 준수: 위 제공된 [Spam Guide] 문서의 규칙(제0원칙 및 예외 보호 등)과 판단 우선순위를 어떠한 경우에도 최우선 기준으로 확고히 적용하라.

[PROCEDURE]
Step 1. 시그널 1차 판정:
   - harm_anchor: 도박/성인/사기/피싱/리딩방/불법 등 치명적 위해성(가이드의 최우선 스팸 기준)이 있는지 (`true` / `false`)
   - route_or_cta: 수신자의 행동(클릭, 전화, 오픈채팅 가입 등)을 강하게 유도하는지 (`true` / `false`)

Step 2. 의도 명확도 산출: 최종 스팸 확률을 spam_probability(0.0~1.0)로 산출하라.

Step 3. [암묵적 도메인 (Covert Domain) 추론 및 추출]
   - 만약 메시지 내에 "도박, 스포츠토토, 카지노, 성인 유흥" 등을 암시하는 불법적인 문맥이 존재하거나, 접속을 유도하는 기이한 텍스트 구조가 있을 경우 다음과 같이 숨겨진 URL을 복원하여 `obfuscated_urls`에 넣는다.
   - ① 고의 확장자 누락/잘림: `NH1245`, `메인337`처럼 독립된 식별 코드나, `nike26. `처럼 확장자 직전까지만 쓰여진 경우 무조건 `.com`을 붙여 복원하라 (예: `NH1245.com`, `nike26.com`).
   - 🚨 [★절대 주의★]: 메시지 내에 마침표(.) 등 특수문자가 난잡하게 섞여 있더라도, 영문자와 숫자로 조합된 단어 뒤에 점이 붙은 형태(예: `dbb73.`)가 보인다면 이는 무의미한 점이 아니라 100% 은닉 도메인(`dbb73.com`)입니다!
   - 위와 같은 은닉 도메인 단서가 단 하나라도 발견되면, 절대로 `HOLD_SHORT` 판정을 내리지 말고 무조건 `SPAM` 판정 후 `obfuscated_urls`에 복원 도메인을 기재하십시오.
   - ② 한글음차/변형 확장자: `.com`을 `점켬`, `점컴`, `쩜컴`, `닷컴` 등으로 변형한 경우 `.com`으로 복원하여 추출하라 (예: `TOY9898 점켬` -> `TOY9898.com`).
   - ③ 특수기호 위장 확장자: `c@rn`, `cㅇm` 처럼 알파벳을 비슷한 모양의 특수기호/기타 문자로 위장한 경우 정상 문자로 치환하여 추출하라 (예: `mx6001.c@rn` -> `mx6001.carn` 또는 `mx6001.com`).
   - ④ 영문 번역/음차 유추: 단독 한글 코드가 영단어 발음인 경우(예: `메인337`), 한글과 영어를 각각 추출하라 (`메인337.com`, `main337.com`).
   - 단, 악성 의도가 없는 완전 정상/일상 대화, 일반적인 금융 인증번호 등에는 절대 `.com`을 붙이지 마라.

Step 4. 최종 판정 (label 확정):
   - Guide 기준에 따라 완벽한 정상문자면 HAM. 
   - Guide 기준 SPAM 사유에 해당하면 무조건 SPAM. SPAM일 경우 spam_code (0, 1, 2, 3 중 택1)를 반드시 Guide의 3항(분류 코드 선택) 기준에 맞게 지정하라.
   - URL 없는 극단적 짧은 파편화 난독 문자라면 HOLD_SHORT 적용. 단, 파편화 문자 사이에서도 `영문+숫자+마침표` 형태의 은닉 도메인(예: `dbb73.`)이 식별되면 HOLD_SHORT를 취소하고 SPAM으로 통과시킬 것!

[OUTPUT — JSON ONLY]
{{
"label": "HAM|SPAM|HOLD_SHORT",
"spam_code": "0|1|2|3|null",
"spam_probability": 0.0,
"reason": "Spam Guide의 어떤 기준에 의해 판정했는지 명시하여 한국어로 짧게 작성할 것.",
"signals": {{ "harm_anchor": false, "route_or_cta": false }},
"obfuscated_urls": []
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
            # 1. Intent Summary Generation (Directly use agenerate_intent_summary if possible, else sync fallback)
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
                        "signals": {"harm_anchor": True, "route_or_cta": True}
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
            
            # [특수 판정 방어] 이중 필터 - HOLD_SHORT 길이 검증
            if result.get('is_spam') == "HOLD_SHORT":
                from app.agents.history_manager import HistoryManager
                if not HistoryManager.is_eligible_for_hold(message):
                    # 글자수 초과이므로 HAM으로 강제 예외 전환
                    result['is_spam'] = False
                    result['classification_code'] = None
                    result['reason'] = f"[HOLD 거부] 설정된 메시지 길이 초과. 일반 HAM으로 우회됨. | {result.get('reason')}"
                    logger.warning("[Content_Agent] Length mismatch. Forced HOLD_SHORT to HAM.")

            # 판정 결과 로그 (표준화된 형식)
            is_spam = result.get('is_spam')
            verdict = "HOLD_SHORT" if is_spam == "HOLD_SHORT" else ("SPAM" if is_spam else ("HITL" if is_spam is None else "HAM"))
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
                        "signals": {"harm_anchor": True, "route_or_cta": True}
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
                        sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-pro-preview")
                        fallback_key = key_manager.get_key("GEMINI")
                        if fallback_key:
                            fallback_llm = self._get_cached_client("GEMINI", fallback_key, sub_model)
                            try:
                                response = await asyncio.wait_for(fallback_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                            except Exception:
                                raise Exception("Async Summary LLM Timeout (Fallback failed)") from e
                        else:
                            raise Exception("Async Summary LLM Timeout") from e
                        
                        
                    key_manager.extract_and_add_tokens(provider, response)
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
                            sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-pro-preview")
                            fallback_key = key_manager.get_key("GEMINI")
                            if fallback_key:
                                fallback_llm = self._get_cached_client("GEMINI", fallback_key, sub_model)
                                try:
                                    response = await asyncio.wait_for(fallback_llm.ainvoke([HumanMessage(content=prompt)]), timeout=45.0)
                                    if hasattr(response, 'content') and isinstance(response.content, str):
                                        response.content = f"[Content_Fallback: {sub_model}] " + response.content
                                except Exception:
                                    raise Exception("Async Summary LLM Timeout after rotation (Fallback failed)") from e
                            else:
                                raise Exception("Async Summary LLM Timeout after rotation") from e
                            
                            
                        key_manager.extract_and_add_tokens(provider, response)
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
        (Synchronous version using Thread fallback to bridge Async loop safely)
        """
        import asyncio
        import threading
        
        result_box = []
        def run_in_thread():
            try:
                # new thread -> no running loop -> can safely asyncio.run
                res = asyncio.run(self.agenerate_intent_summary(message))
                result_box.append(res)
            except Exception as e:
                result_box.append(e)

        try:
            try:
                asyncio.get_running_loop()
                in_loop = True
            except RuntimeError:
                in_loop = False

            if not in_loop:
                return asyncio.run(self.agenerate_intent_summary(message))
            else:
                # We are already inside a running loop (e.g., LangGraph Batch ThreadPoolExecutor fallback)
                # Spawning a thread isolates the async context completely.
                t = threading.Thread(target=run_in_thread)
                t.start()
                t.join()
                
                res = result_box[0]
                if isinstance(res, Exception):
                    raise res
                return res
        except Exception as e:
            logger.warning(f"Sync Intent Summary Thread Bridge Failed: {e}")
            return f"Intent analysis of: {message[:50]}..."
