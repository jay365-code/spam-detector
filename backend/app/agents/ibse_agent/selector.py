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
- **[🚨 절대 금지]** 메시지가 40바이트를 명백히 넘음에도 불구하고 원본 텍스트 전체를 통째로 추출하지 마라! 반드시 40바이트 이내의 부분 문자열을 잘라내야 한다. 단 애초에 메시지 전체 길이가 39 bytes도 안 되는 아주 짧은 메시지인 경우에만 예외적으로 원문 전체를 변경 없이 묶어서 추출한다.

2) "use_string": 9~20 bytes 사이의 짧은 단어장/키워드 배열 추출 (가장 흔함)
- 추출 길이 제한: CP949 인코딩 기준 **반드시 9 bytes 이상 20 bytes 이하**여야 한다. (영문/숫자/특수기호는 1바이트, 한글은 2바이트로 계산)
- 🚨 [9바이트 미만 절대 금지] 만약 찾아낸 핵심 식별자(예: 'F-ONE')가 너무 짧아서 9바이트가 안 된다면, 절대 단독으로 추출하거나 포기하고 "NONE"을 뱉지 마라! 반드시 해당 키워드 주변의 특수기호나 단어를 덧붙여서(예: `◆F-ONE◆김대표`) 최소 9바이트 이상 20바이트 이하 길이를 강제로라도 맞추거나, 아예 39~40바이트의 `use_sentence`로 크게 묶어 추출해라.
- 🚨 [서명 중간 절단 절대 금지] 20바이트 혹은 40바이트 제한 기준에 맞추다 어쩔 수 없이 식별용 URL이나 핵심 영단어의 한가운데가 툭 잘려나간 형태(예: `www.youtube.com/watc`)로 추출해서는 절대 안 된다. 시그니처가 중간에 잘리면 오탐 확률이 대폭 늘어난다. 만약 주소가 너무 길어 길이 제한 탓에 중간이 잘릴 수밖에 없다면, 차라리 도메인/URL 추출을 포기하고 메시지 내 다른 Unique한 형태의 한글 문자열이나 고유 패턴을 시그니처로 삼아라. URL을 추출할 것이라면 반드시 '풀(Full)'로 완전한 형태로 뽑거나 다른 특이 문자열을 추출해라.
- **[🚨 억지 추출 금지]** 길이 기준(+잘림 없는 온전한 형태)에 부합하는 적절한 문자열을 원문에서 도저히 찾을 수 없다면, 억지로 기준에 어긋나는 부분을 끼워 맞춰 추출할 필요가 **전혀 없다**. 고민하지 말고 안전하게 `"decision": "unextractable"`을 리턴해라.

---
[INPUT DATA]
- 분석 대상 메시지 (공백 제거 상태): {match_text}
- 복원된 난독화 도메인 (obfuscated_urls): {obfuscated_urls}

출력(JSON):
{{
  "message_id": "{message_id}",
  "decision": "use_string" | "use_sentence" | "unextractable",
  "identified_url_or_domain": "원문에서 찾은 URL/도메인 본체 (없으면 null)",
  "signature": "추출한 원본 부분 문자열 (최우선: 난독화/투명 기호가 섞인 특이한 문자열(예: '쿠-팡')이 있다면 이를 1일 단기 차단용으로 우선 추출할 것. 평범한 텍스트일 때는 가급적 identified_url_or_domain을 포함할 것)",
  "risk": "low" | "medium" | "high",
  "reason": "왜 이 문자열이 가장 고유하고 강력한 시그니처인지 1~2줄 요약 (오탐 여부 등)"
}}"""

    REPAIR_SYSTEM_PROMPT = """이전 출력이 검증에 실패했다.
가장 중요한 원칙은 **signature가 match_text 내에 정확히 존재해야(오타/변형 불가) 하며, 길이는 반드시 9~20 bytes 또는 39~40 bytes 중 하나여야 한다 (21~38 bytes는 절대 불가).**
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
  "signature": "추출한 원본 부분 문자열 (반드시 identified_url_or_domain을 포함할 것!)",
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
    
    # 만약 LLM이 URL을 아예 못 찾았다면, 정규식으로 직접 찾아서 강제 주입
    if not identified_url or identified_url == "null":
        # 영문/숫자 혼합 도메인 및 경로를 최소한으로 잡는 범용 정규식
        found_urls = re.findall(r'[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[a-zA-Z0-9_/?=#&.-]*)?', match_text)
        if found_urls:
            # 보통 맨 마지막이나 핵심에 있는 URL이 타겟. 문자열 안에 존재하는 실제 URL만 필터링
            for u in found_urls:
                if u in match_text:
                    identified_url = u
                    break

    if identified_url and identified_url != "null" and isinstance(identified_url, str):
        if identified_url in match_text and identified_url not in sig_text:
            logger.warning(f"⚠️ [IBSE Agent] LLM missed URL in signature or gave up! Forcing inclusion programmatically: {identified_url}")
            url_len = len(identified_url.encode("cp949", errors="replace"))
            
            # [중요] 단축 URL (Path가 3 이하)인 경우 단독 추출은 오탐 유발, 반드시 Context 필요
            path_parts = identified_url.split('/')
            is_short_url = len(path_parts) > 1 and len(path_parts[-1]) <= 3
            
            if not is_short_url and url_len <= 20:
                result["decision"] = "use_string"
                sig_text = identified_url
            else:
                result["decision"] = "use_sentence"
                end_idx = match_text.find(identified_url) + len(identified_url)
                target_text = match_text[:end_idx]
                encoded = target_text.encode("cp949", errors="replace")
                if len(encoded) > 40:
                    truncated = encoded[-40:]
                    while len(truncated) > 0:
                        try:
                            sig_text = truncated.decode("cp949", errors="strict")
                            break
                        except UnicodeDecodeError:
                            truncated = truncated[1:] # 앞부분 바이트 깨짐 보정
                else:
                    sig_text = target_text
            
            result["signature"] = sig_text

    if "signature" in result and result["signature"] and result.get("decision") in ["use_string", "use_sentence"]:
        max_bytes = 20 if result["decision"] == "use_string" else 40
        sig_text = result["signature"]
        
        # Safely truncate CP949
        encoded = sig_text.encode("cp949", errors="replace")
        
        # [Dead Zone 방어] 문장열(use_sentence) 규정 위반 방지: 길이가 39바이트 미만인 경우 패딩(Padding) 혹은 강등 처리
        if result["decision"] == "use_sentence" and len(encoded) < 39:
            idx = match_text.find(sig_text)
            if idx != -1:
                end_idx = idx + len(sig_text)
                pad_front = match_text[:end_idx].encode("cp949", errors="replace")
                pad_back = match_text[idx:].encode("cp949", errors="replace")
                
                if len(pad_front) >= 39:
                    encoded = pad_front[-40:]
                    while len(encoded) > 0:
                        try:
                            sig_text = encoded.decode("cp949", errors="strict")
                            break
                        except UnicodeDecodeError:
                            encoded = encoded[1:]
                elif len(pad_back) >= 39:
                    encoded = pad_back[:40]
                    while len(encoded) > 0:
                        try:
                            sig_text = encoded.decode("cp949", errors="strict")
                            break
                        except UnicodeDecodeError:
                            encoded = encoded[:-1]
                else:
                    # 원문 전체를 모아도 39바이트 미만인 불가항력 -> 무조건 문자열(use_string)로 강제 다운그레이드
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
            
        try:
            result["byte_len_cp949"] = len(result["signature"].encode("cp949"))
        except:
             result["byte_len_cp949"] = len(result["signature"]) * 2

    return {
        "final_result": result,
        "extracted_signature": result.get("signature"),
        "extraction_type": result.get("decision"),
        "error": result.get("error")
    }
