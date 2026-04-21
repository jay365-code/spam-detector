import os
import json
import asyncio
import re
from typing import List, Optional
from .state import IBSEState
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log
import logging

logger = logging.getLogger(__name__)

def _normalize_llm_content(content) -> str:
    if content is None: return ""
    if isinstance(content, str): return content
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            return first.get("text", "") or ""
        if isinstance(first, str): return first
    return str(content)

class LLMSelector:
    _recent_signatures_cache = ""
    _recent_signatures_time = 0

    @classmethod
    def get_recent_signatures_context(cls) -> str:
        import time
        from app.core.signature_db import SignatureDBManager
        if time.time() - cls._recent_signatures_time > 300: # 5 minutes TTL
            try:
                res = SignatureDBManager.get_signatures(limit=30, sort_col="last_hit", sort_order="desc")
                sigs = [f"- {s['signature']}" for s in res.get("data", []) if s.get("signature")]
                if sigs:
                    samples = "\n".join(sigs)
                    cls._recent_signatures_cache = f"\n\n[실제 차단 시그니처 최근 모범 예시 30선]\n아래는 최근 가장 활발하게 차단 이력(HIT)이 발생한 모범 스팸 시그니처 30개이다.\n원문에서 어떤 부분을 어떻게 뜯어내야 하는지(은어, 기호 조합, 무공백 등) 형태를 학습하고 모방하라.\n단, 이는 학습용 참조(Reference)일 뿐이므로, 현재 주어지는 원문 안에 존재하지 않는 텍스트를 지어내거나(Hallucination) 복사해서는 절대 안 된다.\n{samples}"
                else:
                    cls._recent_signatures_cache = ""
                cls._recent_signatures_time = time.time()
            except Exception as e:
                logger.error(f"Failed to load recent signatures for prompt: {e}")
        return cls._recent_signatures_cache

    @property
    def SYSTEM_PROMPT(self) -> str:
        guide_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/signature_spam_guide.md"))
        try:
            with open(guide_path, "r", encoding="utf-8") as f:
                guide_content = f.read()
            samples_context = self.get_recent_signatures_context()
            return f"너는 IBSE(Intelligence Blocking Signature Extractor)의 핵심 추출 엔진이다.\n목표는 **이미 스팸으로 판명된 메시지**에서, 향후 동일/유사 공격을 효율적으로 차단할 수 있는 '차단 시그니처(문자열/문장)'를 추출하는 것이다.\n\n{guide_content}{samples_context}\n\n반드시 지시된 JSON 규격 단일 객체만 리턴하라."
        except Exception as e:
            logger.error(f"Failed to load signature_spam_guide.md: {e}")
            return "너는 IBSE(Intelligence Blocking Signature Extractor)의 핵심 추출 엔진이다. 반드시 지시된 JSON 규격 단일 객체만 리턴하라."

    USER_TEMPLATE = """message_id: {message_id}

[추출 결정 요구 사항]
가이드 문서의 "최종 판결(Decision) 및 바이트(Bytes) 길이 로직" 및 우선순위 트리에 따라 정교하게 시그니처를 추출하라. 
"오직 절대적으로 유니크한가?" 라는 단일 잣대와 함께 주어진 가이드 라인의 길이 제약(9~20바이트 혹은 39~40바이트 제한, 9바이트 미만 금지 룰 등)을 엄격하게 준수해야 한다.

---
[INPUT DATA]
- 분석 대상 메시지 (원본 메시지): {match_text}
- 복원된 난독화 도메인 (obfuscated_urls): {obfuscated_urls}

출력(JSON):
{{
  "message_id": "{message_id}",
  "decision": "use_string" | "use_sentence" | "unextractable",
  "identified_url_or_domain": "원문에서 찾은 URL/도메인 본체 (없으면 null)",
  "signature": "추출한 유니크한 원본 부분 문자열 (가이드라인의 우선순위 및 길이 제약을 엄격히 준수할 것)",
  "risk": "low" | "medium" | "high",
  "reason": "왜 이 문자열이 가장 고유하고 강력한 시그니처인지 1~2줄 요약"
}}"""

    REPAIR_SYSTEM_PROMPT = """이전 출력이 검증에 실패했다.
가장 중요한 원칙은 **signature가 match_text 내에 정확히 존재해야하며, 길이는 반드시 9~20 bytes 또는 39~40 bytes 중 하나여야 한다.** (루트 도메인만 달랑 단독 추출하는 오탐은 금지며, 문맥 텍스트나 고유 Path를 포함해 '유니크한 문자열'을 만들어야 함)
반드시 JSON 단일 객체로만 다시 출력해라."""

    REPAIR_USER_TEMPLATE = """검증 실패 사유: {error_reason}

이전 출력: {previous_output_json}

동일 입력 원본(match_text): {match_text}
obfuscated_urls: {obfuscated_urls}

규칙에 맞춰 JSON을 다시 출력해라.
{{
  "message_id": "{message_id}",
  "decision": "use_string" | "use_sentence" | "unextractable",
  "identified_url_or_domain": "원문에서 찾은 URL/도메인 본체 (없으면 null)",
  "signature": "추출한 원본 텍스트 조각 (루트 도메인 단독 추출 금지, 오직 유니크하게 추출할 것)",
  "risk": "low" | "medium" | "high",
  "reason": "왜 이 문자열이 가장 고유하고 강력한 시그니처인지 1~2줄 요약 (오탐 여부 등)"
}}"""

    def __init__(self):
        from app.core.llm_manager import key_manager
        self._key_manager = key_manager
        self._loop_bound_clients = {}

    def _get_cached_client(self, provider: str, api_key: str, model_name: str):
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        cache_key = f"{provider}_{api_key}_{model_name}"
        dict_key = (cache_key, current_loop)

        if dict_key in self._loop_bound_clients:
            return self._loop_bound_clients[dict_key]

        logger.info(f"[LLMSelector] Instantiating new LLM client for {provider} ({model_name})")
        if provider == "OPENAI":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, max_retries=0)
        elif provider == "GEMINI":
            from langchain_google_genai import ChatGoogleGenerativeAI
            safety_settings = {
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
            client = ChatGoogleGenerativeAI(
                model=model_name if "gemini" in model_name else "gemini-1.5-flash",
                google_api_key=api_key,
                temperature=0.0,
                safety_settings=safety_settings,
                convert_system_message_to_human=True,
                max_retries=0
            )
        elif provider == "CLAUDE":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
            
        self._loop_bound_clients[dict_key] = client
        return client

    @property
    def model_name(self) -> str:
        return os.getenv("LLM_MODEL", "gpt-4o")

    @property
    def provider(self) -> str:
        return os.getenv("LLM_PROVIDER", "OPENAI").upper()

    async def select(self, state: IBSEState, is_repair: bool = False) -> dict:
        message_id = state.get("message_id", "unknown")
        match_text = state.get("match_text", "")
        obfuscated_urls = json.dumps(state.get("obfuscated_urls", []), ensure_ascii=False)
        
        if is_repair:
            system_prompt = self.REPAIR_SYSTEM_PROMPT
            user_prompt = self.REPAIR_USER_TEMPLATE.format(
                error_reason=state.get("error", "Unknown Error"),
                previous_output_json=json.dumps(state.get("final_result", {}), ensure_ascii=False),
                match_text=match_text,
                obfuscated_urls=obfuscated_urls,
                message_id=message_id
            )
        else:
            system_prompt = self.SYSTEM_PROMPT
            user_prompt = self.USER_TEMPLATE.format(
                message_id=message_id,
                match_text=match_text,
                obfuscated_urls=obfuscated_urls
            )
            
        logger.debug(f"\n{'='*20} [IBSE LLM Prompt for {message_id}] {'='*20}\n[SYSTEM PROMPT]\n{system_prompt}\n\n[USER PROMPT]\n{user_prompt}\n{'='*60}\n")
            
        return await self._call_llm(system_prompt, user_prompt)

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> dict:
        async def _raw_call():
            provider = self.provider
            if self._key_manager.is_quota_exhausted(provider):
                raise Exception(f"{provider} quota globally exhausted. No retry.")
            
            api_key = self._key_manager.get_key(provider)
            current_model = self.model_name
            is_fallback = getattr(self, "_use_fallback", False)
            if is_fallback:
                current_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-pro-preview").strip().strip("'")
                logger.warning(f"[IBSE] Fallback mode active: Switching model to {current_model}.")

            client_instance = self._get_cached_client(provider, api_key, current_model)
            
            try:
                if provider == "OPENAI":
                    _kwargs = {
                        "model": current_model,
                        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                        "response_format": {"type": "json_object"},
                    }
                    if not any(current_model.startswith(p) for p in ("o1", "o3", "o4", "gpt-5")):
                        _kwargs["temperature"] = 0.0
                    response = await asyncio.wait_for(client_instance.chat.completions.create(**_kwargs), timeout=65.0)
                    content = response.choices[0].message.content
                elif provider == "GEMINI":
                    from langchain_core.messages import SystemMessage, HumanMessage
                    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    response = await asyncio.wait_for(client_instance.ainvoke(messages), timeout=65.0)
                    content = _normalize_llm_content(response.content)
                    if not content or "SAFETY" in str(response.response_metadata):
                        return '{"decision": "unextractable"}'
                elif provider == "CLAUDE":
                    response = await asyncio.wait_for(client_instance.messages.create(
                        model=current_model, max_tokens=1024, system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}]
                    ), timeout=65.0)
                    content = response.content[0].text
                else:
                    raise Exception("Unsupported Provider")
                self._key_manager.report_success(provider)
                if is_fallback: content = f"__FALLBACK_{current_model}__\n" + content
                return content
            except Exception as e:
                # [추가] 불량 키(invalid_argument, api_key_invalid)도 rotate 대상으로 처리
                is_quota = any(kw in str(e).lower() for kw in [
                    "quota", "429", "invalid_argument", "api key not found", "api_key_invalid"
                ])
                if is_quota:
                    if not self._key_manager.rotate_key(provider, failed_key=api_key):
                        raise Exception("Quota exhausted globally") from e
                raise e

        @retry(
            stop=stop_after_attempt(1),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception(lambda e: "No retry." not in str(e)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        async def main_call_with_retry():
            return await _raw_call()

        try:
            content = await main_call_with_retry()
            parsed = self._parse_json(content)
            if "error" in parsed:
                raise Exception(parsed["error"])
                
            # [사용자 요청 반영] 메인 모델이 시그니처가 없다고(unextractable) 포기하더라도, 곧바로 서브 모델에 기회를 주어 크로스체크 하도록 강제
            if parsed.get("decision") == "unextractable" and not getattr(self, "_use_fallback", False):
                logger.warning("[IBSE] Main model decided 'unextractable'. Refusing to give up. Passing to Fallback model.")
                raise Exception("Main model concluded unextractable. Delegating to Fallback model.")
                
            return parsed
        except Exception as e:
            if not getattr(self, "_use_fallback", False):
                logger.warning(f"[IBSE] Main model failed with '{type(e).__name__} - {e}'. Attempting Fallback Mode (One attempt only)...")
                self._use_fallback = True
                try:
                    # Retry with fallback model (No Tenacity Retries - exactly 1 attempt)
                    content_fb = await _raw_call()
                    return self._parse_json(content_fb)
                except Exception as e2:
                    logger.error(f"[IBSE] Fallback also failed: {type(e2).__name__} - {e2}")
                    return {"error": str(e2), "decision": "unextractable"}
            
            return {"error": str(e), "decision": "unextractable"}

    def _parse_json(self, content: str) -> dict:
        import re
        fallback_model = None
        if content.startswith("__FALLBACK_"):
            parts = content.split("__\n", 1)
            if len(parts) == 2:
                fallback_model, content = parts[0].replace("__FALLBACK_", ""), parts[1]
        try:
            parsed = json.loads(re.sub(r'\s*```$', '', re.sub(r'^```(?:json)?\s*', '', content.strip())))
            if fallback_model and "reason" in parsed:
                parsed["reason"] = f"[IBSE_Fallback: {fallback_model}] " + parsed["reason"]
            return parsed
        except Exception as e:
            return {"error": "JSON Parse Error"}

async def select_signature_node(state: IBSEState) -> dict:
    selector = LLMSelector()
    is_repair = bool(state.get("error"))
    result = await selector.select(state, is_repair=is_repair)
    
    match_text = state.get("match_text", "")
    sig_text = result.get("signature") or ""
    decision = result.get("decision", "unextractable")

    # [Python 하이브리드 엔진] 공백 전처리 (Method 1)
    import re
    spaceless_msg = re.sub(r'\s+', '', match_text)
    
    # LLM이 포기했거나 시그니처를 못 찾은 경우 Python 40-byte Fallback 동원
    if not sig_text or decision == "unextractable":
        clean_blocks = re.split(r'\(광고\)|\[광고\]|무료거부|무료수신거부', spaceless_msg)
        for block in clean_blocks:
            if len(block.encode('cp949', errors='ignore')) >= 39:
                valid_len = 0
                for i in range(1, len(block) + 1):
                    if len(block[:i].encode("cp949", errors="replace")) <= 40:
                        valid_len = i
                    else:
                        break
                sig_text = block[:valid_len]
                decision = "use_sentence"
                result["decision"] = decision
                result["signature"] = sig_text
                result["reason"] = "[Python Fallback] LLC Failed. Extracted 40-byte block."
                break

    if "signature" in result and result["signature"] and decision in ["use_string", "use_sentence"]:
        # 시그니처에서 무조건 공백 제거
        sig_text = re.sub(r'\s+', '', result.get("signature", ""))
        
        idx = spaceless_msg.find(sig_text)
        b_len = len(sig_text.encode("cp949", errors="replace"))
        
        if decision == "use_string":
            if b_len < 9:
                if idx != -1:
                    left_idx = idx
                    right_idx = idx + len(sig_text)
                    while b_len < 9:
                        expanded = False
                        if left_idx > 0:
                            left_idx -= 1
                            expanded = True
                        if right_idx < len(spaceless_msg) and len(spaceless_msg[left_idx:right_idx].encode("cp949", errors="replace")) < 9:
                            right_idx += 1
                            expanded = True
                            
                        sig_text = spaceless_msg[left_idx:right_idx]
                        b_len = len(sig_text.encode("cp949", errors="replace"))
                        if not expanded:
                            break
                            
            if b_len > 20:
                valid_len = 0
                for i in range(1, len(sig_text) + 1):
                    if len(sig_text[:i].encode("cp949", errors="replace")) <= 20:
                        valid_len = i
                    else:
                        break
                sig_text = sig_text[:valid_len]

        elif decision == "use_sentence":
            if b_len < 39:
                if idx != -1:
                    left_idx = idx
                    right_idx = idx + len(sig_text)
                    while True:
                        current_len = len(spaceless_msg[left_idx:right_idx].encode("cp949", errors="replace"))
                        if current_len >= 39:
                            break
                        expanded = False
                        if left_idx > 0:
                            test_left = left_idx - 1
                            if len(spaceless_msg[test_left:right_idx].encode("cp949", errors="replace")) <= 40:
                                left_idx = test_left
                                expanded = True
                        if right_idx < len(spaceless_msg):
                            test_right = right_idx + 1
                            if len(spaceless_msg[left_idx:test_right].encode("cp949", errors="replace")) <= 40:
                                right_idx = test_right
                                expanded = True
                        
                        if not expanded:
                            break
                        sig_text = spaceless_msg[left_idx:right_idx]
                        
                b_len = len(sig_text.encode("cp949", errors="replace"))
                if b_len < 39:
                    decision = "use_string"
                    result["decision"] = decision
                    valid_len = 0
                    for i in range(1, len(sig_text) + 1):
                        if len(sig_text[:i].encode("cp949", errors="replace")) <= 20:
                            valid_len = i
                        else:
                            break
                    sig_text = sig_text[:valid_len]

            if b_len > 40:
                valid_len = 0
                for i in range(1, len(sig_text) + 1):
                    if len(sig_text[:i].encode("cp949", errors="replace")) <= 40:
                        valid_len = i
                    else:
                        break
                sig_text = sig_text[:valid_len]

        result["signature"] = sig_text
        result["byte_len_cp949"] = len(sig_text.encode("cp949", errors="replace"))
        
    # 마지막 안전장치: 원문 일치 검증 (결과가 없을시 Unextractable 방어)
    if result.get("signature") and result["signature"] not in spaceless_msg:
         if result.get("decision") != "unextractable":
             result["decision"] = "unextractable"
             result["reason"] = f"Hallucination prevented: {result['signature']} not inside spaceless msg"
             result["signature"] = ""

    return {
        "final_result": result,
        "extracted_signature": result.get("signature"),
        "extraction_type": result.get("decision"),
        "error": result.get("error")
    }
