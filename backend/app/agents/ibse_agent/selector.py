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
    @property
    def SYSTEM_PROMPT(self) -> str:
        guide_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/signature_spam_guide.md"))
        try:
            with open(guide_path, "r", encoding="utf-8") as f:
                guide_content = f.read()
            return f"너는 IBSE(Intelligence Blocking Signature Extractor)의 핵심 추출 엔진이다.\n목표는 **이미 스팸으로 판명된 메시지**에서, 향후 동일/유사 공격을 효율적으로 차단할 수 있는 '차단 시그니처(문자열/문장)'를 추출하는 것이다.\n\n{guide_content}\n\n반드시 지시된 JSON 규격 단일 객체만 리턴하라."
        except Exception as e:
            logger.error(f"Failed to load signature_spam_guide.md: {e}")
            return "너는 IBSE(Intelligence Blocking Signature Extractor)의 핵심 추출 엔진이다. 반드시 지시된 JSON 규격 단일 객체만 리턴하라."

    USER_TEMPLATE = """message_id: {message_id}

[추출 타입]
1) "use_sentence": 39~40 bytes 길이의 긴 시그니처 추출
- 추출 길이 제한: 순수 한글/영문/특수기호 혼합하여 39~40 bytes 분량 (글자수 무관)
- **[🚨 절대 금지]** 메시지 크기에 상관없이 원본 텍스트 전체를 통째로 추출하지 마라! 부분 문자열을 잘라내야 한다. 원문 전체 길이가 39 bytes가 안 되는 아주 짧은 메시지라도, 원문을 그대로 사용하는 것이 아니라 반드시 9~20 bytes (use_string) 이내로 유니크한 문자열을 추출해라.

2) "use_string": 9~20 bytes 사이의 짧은 단어장/키워드 배열 추출 (가장 흔함)
- 추출 길이 제한: CP949 인코딩 기준 **반드시 9 bytes 이상 20 bytes 이하**여야 한다. (영문/숫자/특수기호는 1바이트, 한글은 2바이트로 계산)
- 🚨 [9바이트 미만 절대 금지] 만약 찾아낸 핵심 식별자(예: 'F-ONE')가 너무 짧아서 9바이트가 안 된다면, 절대 단독으로 추출하거나 포기하고 "NONE"을 뱉지 마라! 반드시 해당 키워드 주변의 특수기호나 단어를 덧붙여 최소 9바이트 이상 20바이트 이하 길이를 강제로라도 맞추어라.
- 🚨 [도메인/URL 단독 추출 금지] 도메인이나 URL 구역의 글자로만 100% 채워진 시그니처는 대형 오탐 사고를 내므로 절대 금지한다. URL은 단독으로 쓰지 말고, 반드시 한글 텍스트(문자열)를 단독으로 추출하거나, 유니크함이 보장된다면 "한글 문자열 + URL 일부/전체" 형태의 혼합 조합으로 추출해라. 무엇이 되었든 가장 중요한 기준은 "이 시그니처가 스팸을 특정할 수 있는 유니크한 문자열인가?" 이다.
- **[🚨 억지 추출 금지]** 유니크한 문자/문장(시그니처)을 추출하지 못하겠다면 억지로 추출하지 말고 안전하게 `"decision": "unextractable"`을 선언하라.

---
[INPUT DATA]
- 분석 대상 메시지 (공백 제거 상태): {match_text}
- 복원된 난독화 도메인 (obfuscated_urls): {obfuscated_urls}

출력(JSON):
{{
  "message_id": "{message_id}",
  "decision": "use_string" | "use_sentence" | "unextractable",
  "identified_url_or_domain": "원문에서 찾은 URL/도메인 본체 (없으면 null)",
  "signature": "추출한 유니크한 원본 부분 문자열. (주의: URL이나 도메인만 단독으로 추출하지 마라. 한글 문자열 단독이거나 '문자열 + URL' 조합으로 유니크하게 뽑아라.)",
  "risk": "low" | "medium" | "high",
  "reason": "왜 이 문자열이 가장 고유하고 강력한 시그니처인지 1~2줄 요약"
}}"""

    REPAIR_SYSTEM_PROMPT = """이전 출력이 검증에 실패했다.
가장 중요한 원칙은 **signature가 match_text 내에 정확히 존재해야하며, 길이는 반드시 9~20 bytes 또는 39~40 bytes 중 하나여야 한다.** (도메인이나 URL만 단독으로 추출하는 것은 금지며, 문맥 텍스트를 포함해 '유니크한 문자열'을 만들어야 함)
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
  "signature": "추출한 원본 부분 문자열 (도메인/URL 단독 추출 금지, 문자열 단독 또는 문자열+URL 조합으로 유니크하게 추출할 것)",
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
            
        return await self._call_llm(system_prompt, user_prompt)

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> dict:
        from app.core.llm_manager import key_manager
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception(lambda e: "No retry." not in str(e)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        async def do_call():
            provider = self.provider
            if key_manager.is_quota_exhausted(provider):
                raise Exception(f"{provider} quota globally exhausted. No retry.")
            
            api_key = key_manager.get_key(provider)
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
                    response = await asyncio.wait_for(client_instance.chat.completions.create(**_kwargs), timeout=45.0)
                    content = response.choices[0].message.content
                elif provider == "GEMINI":
                    from langchain_core.messages import SystemMessage, HumanMessage
                    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    response = await asyncio.wait_for(client_instance.ainvoke(messages), timeout=45.0)
                    content = _normalize_llm_content(response.content)
                    if not content or "SAFETY" in str(response.response_metadata):
                        return '{"decision": "unextractable"}'
                elif provider == "CLAUDE":
                    response = await asyncio.wait_for(client_instance.messages.create(
                        model=current_model, max_tokens=1024, system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}]
                    ), timeout=45.0)
                    content = response.content[0].text
                else:
                    raise Exception("Unsupported Provider")
                key_manager.report_success(provider)
                if is_fallback: content = f"__FALLBACK_{current_model}__\n" + content
                return content
            except Exception as e:
                is_quota = "quota" in str(e).lower() or "429" in str(e).lower()
                if is_quota:
                    if not key_manager.rotate_key(provider, failed_key=api_key):
                        raise Exception("Quota exhausted globally") from e
                    raise e
                if isinstance(e, asyncio.TimeoutError):
                    self._use_fallback = True
                    raise Exception("Timeout") from e
                raise e

        try:
            content = await do_call()
            return self._parse_json(content)
        except Exception as e:
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
    
# Update byte_len natively and Truncate safely for CP949
    # [Python 2차 방어] LLM이 URL을 찾아놓고도 프롬프트를 어기고 시그니처에 빼먹은 경우,
    # 혹은 'unextractable'을 판정했거나 URL 자체를 못 찾은 경우 강제 치환
    identified_url = result.get("identified_url_or_domain")
    match_text = state.get("match_text", "")
    sig_text = result.get("signature") or ""
    
    # [Python 2차 방어] LLM이 URL을 찾아놓고도 프롬프트를 어기고 시그니처에 빼먹은 경우 강제 치환하는 로직 삭제 (사용자 방침에 따라 URL 강제 포함 금지)
    pass

    if "signature" in result and result["signature"] and result.get("decision") in ["use_string", "use_sentence"]:
        max_bytes = 20 if result["decision"] == "use_string" else 40
        sig_text = result["signature"]
        
        # Safely truncate CP949
        encoded = sig_text.encode("cp949", errors="replace")
        
        # [Dead Zone 방어] 문장열(use_sentence) 규정 위반 방지: 길이가 39바이트 미만인 경우 패딩(Padding) 혹은 강등 처리
        if result["decision"] == "use_sentence" and len(encoded) < 39:
            idx = match_text.find(sig_text)
            if idx != -1:
                left_idx = idx
                right_idx = idx + len(sig_text)
                
                # Expand string window to reach 39~40 bytes without breaking CP949 or inserting '?'
                while True:
                    current_len = len(match_text[left_idx:right_idx].encode("cp949", errors="replace"))
                    if current_len >= 39:
                        break
                        
                    expanded = False
                    
                    # Try expanding left
                    if left_idx > 0:
                        test_left = left_idx - 1
                        test_len = len(match_text[test_left:right_idx].encode("cp949", errors="replace"))
                        if test_len <= 40:
                            left_idx = test_left
                            expanded = True
                            if test_len >= 39:
                                break
                                
                    # Try expanding right
                    if right_idx < len(match_text):
                        test_right = right_idx + 1
                        test_len = len(match_text[left_idx:test_right].encode("cp949", errors="replace"))
                        if test_len <= 40:
                            right_idx = test_right
                            expanded = True
                            if test_len >= 39:
                                break
                    
                    if not expanded:
                        # Cannot expand further without exceeding 40 or reaching ends
                        break
                
                sig_text = match_text[left_idx:right_idx]
                
                if len(sig_text.encode("cp949", errors="replace")) < 39:
                    # 원문 전체를 모아도 39바이트 미만이거나 패딩 실패 -> 무조건 문자열(use_string)로 강제 변환
                    result["decision"] = "use_string"
                    max_bytes = 20
            else:
                # 할루시네이션(원문에 없는 텍스트) 등 -> 문자열(use_string)로 강제 변환
                result["decision"] = "use_string"
                max_bytes = 20
                
        # 확정된 max_bytes (20 or 40)와 최신 sig_text를 기준으로 다시 인코딩 진행
        encoded = sig_text.encode("cp949", errors="replace")
        if len(encoded) > max_bytes:
            url_to_preserve = result.get("identified_url_or_domain")
            obfuscated_urls = state.get("obfuscated_urls", [])
            if obfuscated_urls and isinstance(obfuscated_urls[0], str) and obfuscated_urls[0] in sig_text:
                url_to_preserve = obfuscated_urls[0]

            preserved = False
            if url_to_preserve and url_to_preserve != "null" and isinstance(url_to_preserve, str) and url_to_preserve in sig_text:
                url_encoded = url_to_preserve.encode("cp949", errors="replace")
                if len(url_encoded) <= max_bytes:
                    url_start_idx = sig_text.find(url_to_preserve)
                    url_end_idx = url_start_idx + len(url_to_preserve)
                    
                    left_idx = url_start_idx
                    right_idx = url_end_idx
                    
                    # 한 글자씩 양옆으로 윈도우를 확장하며 바이트 제한을 넘지 않는 선에서 최대한 넓힘
                    # CP949 바이트 중간이 잘려 한글이 깨지는(Mojibake) 치명적 문제 방지
                    while True:
                        expanded_left = False
                        if left_idx > 0:
                            test_str = sig_text[left_idx - 1 : right_idx]
                            if len(test_str.encode("cp949", errors="replace")) <= max_bytes:
                                left_idx -= 1
                                expanded_left = True
                                
                        expanded_right = False
                        if right_idx < len(sig_text):
                            test_str = sig_text[left_idx : right_idx + 1]
                            if len(test_str.encode("cp949", errors="replace")) <= max_bytes:
                                right_idx += 1
                                expanded_right = True
                                
                        if not (expanded_left or expanded_right):
                            break
                            
                    sig_text = sig_text[left_idx:right_idx]
                    preserved = True

            if not preserved:
                # 앞에서부터 1글자 단위로 바이트를 채움
                valid_len = 0
                for i in range(1, len(sig_text) + 1):
                    if len(sig_text[:i].encode("cp949", errors="replace")) <= max_bytes:
                        valid_len = i
                    else:
                        break
                sig_text = sig_text[:valid_len]
                
            result["signature"] = sig_text
            
        result["byte_len_cp949"] = len(result["signature"].encode("cp949", errors="replace"))

    return {
        "final_result": result,
        "extracted_signature": result.get("signature"),
        "extraction_type": result.get("decision"),
        "error": result.get("error")
    }
