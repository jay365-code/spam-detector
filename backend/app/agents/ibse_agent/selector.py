import os
import json
import asyncio
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
    SYSTEM_PROMPT = """너는 IBSE(Intelligence Blocking Signature Extractor)의 핵심 추출 엔진이다.
목표는 **이미 스팸으로 판명된 메시지**에서, 향후 동일/유사 공격을 효율적으로 차단할 수 있는 '차단 시그니처(문자열/문장)'를 추출하는 것이다.

**[명심할 원칙: 절대 창작(Hallucination) 금지]**
- 너는 오직 주어진 `match_text`(공백이 완전히 제거된 압축 텍스트) 안에서 일치하는 부분 문자열(substring)만 가위로 오려내듯 발췌(Extraction)해야 한다.
- 어조를 바꾸거나, 띄어쓰기를 새로 넣거나, 문맥을 요약하는 등의 **임의 변형은 절대 금지**된다. 원본 텍스트에 있는 글자 그대로 추출해라!

**[수작업 추출 노하우 규칙 (Extraction Rules)]**
1. **1순위 (최우선 타겟): 특이점과 난독화, 변형 URL (반드시 포함)**
    - 원문 안에 **URL, 도메인(예: `nike26.`, `youtube.com` 등), 혹은 접속 오픈채팅 링크**가 존재한다면 형태가 불완전하더라도 시그니처에 **가장 1순위로 반드시 포함**시켜라! 스팸 텍스트 내용보다 접속 주소(URL) 자체가 훨씬 치명적이고 고유한 차단 식별자이기 때문이다.
    - 도메인이나 링크 사이에 한글이나 특수기호가 섞여 정상적인 형태가 아닌 변형된 URL (예: `YⓞNⓖ20⑤.com`, `bit.ly/로얄7468`, `헤이접속쩜콤`)
    - 자음이나 모음이 기형적으로 분리/합성된 텍스트 (예: `초ㄷH합니다`, `티브이ㄴㅅ`)
    - 일반적인 정상 문자(HAM)에서는 절대 등장할 수 없는 고유 기호와 단어 혼종(High Entropy)

2. **길이 제한 (매우 엄격함 - 중간 길이는 절대 허용 안 됨)**
    - 추출할 시그니처 길이는 무조건 아래 두 가지 범위 중 하나에 정확히 맞아떨어져야 한다. (한글=2바이트, 그 외=1바이트)
    - **타입 1 (`decision: "use_string"`)**: **9 ~ 20 bytes**
    - **타입 2 (`decision: "use_sentence"`)**: **39 ~ 40 bytes**
    - **[중요]** 21 ~ 38 bytes 길이의 시그니처는 시스템에서 에러 처리되므로 절대 출력하지 마라!
    - **[절삭(Truncation) 엄격 금지]** 최우선 타겟(URL, 고유 난독화 문자 등) 고유한 식별자를 추출할 때 그 본연의 길이가 20바이트를 초과한다면, **절대로 20바이트에 맞추기 위해 뒷부분을 임의로 자르지 마라!** (예: URL의 끝을 자르면 `.com`이 `.c`가 되어 치명적인 오탐이 발생한다). 타겟 식별자를 온전히 담기 위해 20바이트 규정이 맞지 않는다면 무조건 주변 문맥을 포함시켜 **39~40바이트짜리 문장(`use_sentence`)으로 처리해라.**
    - 반대로, 추출하려는 덩어리 전체의 길이가 이미 20바이트 이하(길이 제한 내)라면, 그대로 `"use_string"`으로 단일 추출하라.

3. **블로킹 우회용 잘린 URL (Contextual Fingerprinting) 및 URL 절삭 주의사항**
    - 추출된 단축 URL의 상세 경로(Path)가 1~3글자 정도로 비정상적으로 짧거나 문장 끝에서 잘린 형태(예: `https://han.gl/AQ`)라면, 절대 해당 URL만 단독으로 추출하지 마라. 이는 오탐을 유발한다.
    - 대신 **주요 스팸 키워드와 해당 잘린 URL을 묶어서** 컨텍스트가 포함된 시그니처를 만들어라.
    - 전체 메시지가 길다면 `decision: "use_sentence"` (39~40 bytes)로 결합하여 추출하고 (예: `비법!우연한가난은없다!https://han.gl/AQ`), 메시지 자체가 짧아서 39바이트가 안 된다면 잘린 URL과 핵심 키워드 일부만 합친 뒤 **20 bytes 이하로 잘라내어** `decision: "use_string"` (9~20 bytes)으로 추출해라. (예: `가난은없다!han.gl/AQ`)
    - **[핵심! URL 추출 시 주의사항 (풍선 효과 방지)]**: 타겟이 일반 URL인 경우, **글자 수를 낭비하는 `http://` 또는 `https://` 접두사는 반드시 제외하고 도메인 본체부터 추출**해라! (예: 원문에 `https://open-kakao.cam/use` 가 있다면 `https://`를 빼고 `open-kakao.cam/use` 만 추출해라. 그러면 18바이트이므로 20바이트(`use_string`) 제한 안에 완벽히 들어온다. 만약 `https://`를 포함해서 20바이트로 억지로 자르면 `https://open-kakao.c` 처럼 TLD가 잘린 엉뚱한 시그니처가 되어 다른 정상 도메인까지 차단하는 치명적인 오탐이 발생한다!)

4. **절대 제외 항목 (블랙리스트 - 오탐 차단)**
    - `(광고)`, `[광고]` 등과 같은 광고 표기 의무 문구는 절대 포함하지 마라.
    - `무료거부 080-xxx-xxxx` 형태의 단순 수신거부 안내 문구는 단독 시그니처로 잡지 마라. (그 주변의 악성 식별자가 결합된 경우는 예외)

**[판단 로직]**
위 규칙에 부합하는 치명적인 시그니처를 찾았다면 길이에 따라 `decision: "use_string"` (9~20 bytes) 또는 `decision: "use_sentence"` (39~40 bytes)로 결정하고 추출해라. 중간 길이(21~38)는 없다.
만약 원문에 URL이나 도메인(`nike26.` 등 불완전한 형태 포함)이 있다면, 반드시 `identified_url_or_domain` 필드에 먼저 기입해라. 그리고 나서 `signature`는 그 도메인을 **반드시 포함하여** 생성해라. URL이 없으면 null로 둔다.
만약 도저히 추출할 만한 고유 시그니처가 없거나, 평범한 상용구뿐이라 정상 문자를 오탐할 위험이 크다면 단 1초도 고민하지 말고 `{"decision": "unextractable"}`을 뱉고 포기하라. 억지로 만들 필요는 절대 없다.

반드시 지시된 JSON 규격 단일 객체만 리턴하라."""

    USER_TEMPLATE = """message_id: {message_id}
match_text: {match_text}

is_garbage_obfuscation: {is_garbage_obfuscation}

출력(JSON):
{{
  "message_id": "{message_id}",
  "decision": "use_string" | "use_sentence" | "unextractable",
  "identified_url_or_domain": "원문에서 찾은 URL/도메인 본체 (없으면 null)",
  "signature": "추출한 원본 부분 문자열 (반드시 identified_url_or_domain을 포함할 것!)",
  "risk": "low" | "medium" | "high",
  "reason": "왜 이 문자열이 가장 고유하고 강력한 시그니처인지 1~2줄 요약 (오탐 여부 등)"
}}"""

    REPAIR_SYSTEM_PROMPT = """이전 출력이 검증에 실패했다.
가장 중요한 원칙은 **signature가 match_text 내에 정확히 존재해야(오타/변형 불가) 하며, 길이는 반드시 9~20 bytes 또는 39~40 bytes 중 하나여야 한다 (21~38 bytes는 절대 불가).**
반드시 JSON 단일 객체로만 다시 출력해라."""

    REPAIR_USER_TEMPLATE = """검증 실패 사유: {error_reason}

이전 출력: {previous_output_json}

동일 입력 원본(match_text): {match_text}
is_garbage_obfuscation: {is_garbage_obfuscation}

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
        is_garbage = 'true' if state.get("is_garbage_obfuscation", False) else 'false'
        
        if is_repair:
            system_prompt = self.REPAIR_SYSTEM_PROMPT
            user_prompt = self.REPAIR_USER_TEMPLATE.format(
                error_reason=state.get("error", "Unknown Error"),
                previous_output_json=json.dumps(state.get("final_result", {}), ensure_ascii=False),
                match_text=match_text,
                is_garbage_obfuscation=is_garbage
            )
        else:
            system_prompt = self.SYSTEM_PROMPT
            user_prompt = self.USER_TEMPLATE.format(
                message_id=message_id,
                match_text=match_text,
                is_garbage_obfuscation=is_garbage
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
                current_model = os.getenv("LLM_SUB_MODEL", "gemini-1.5-flash-lite").strip().strip("'")
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
    sig_text = result.get("signature", "")
    
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
        if len(encoded) > max_bytes:
            truncated = encoded[:max_bytes]
            while len(truncated) > 0:
                try:
                    sig_text = truncated.decode("cp949", errors="strict")
                    break
                except UnicodeDecodeError:
                    truncated = truncated[:-1]
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
