import os

# Rewrite selector.py
with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\backend\app\agents\ibse_agent\selector.py', 'w', encoding='utf-8') as f:
    f.write('''import os
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
- 너는 오직 주어진 `original_text` 안에서 정확히 일치하는 부분 문자열(substring)만 가위로 오려내듯 발췌(Extraction)해야 한다.
- 어조를 바꾸거나, 띄어쓰기를 새로 넣거나, 문맥을 요약하는 등의 **임의 변형은 절대 금지**된다. 원본 텍스트에 있는 글자 그대로 추출해라!

**[수작업 추출 노하우 규칙 (Extraction Rules)]**
1. **1순위 (최우선 타겟): 특이점과 난독화, 변형 URL**
    - 도메인이나 링크 사이에 한글이나 특수기호가 섞여 정상적인 형태가 아닌 변형된 URL (예: `YⓞNⓖ20⑤.com`, `bit.ly/로얄7468`, `헤이접속쩜콤`)
    - 자음이나 모음이 기형적으로 분리/합성된 텍스트 (예: `초ㄷH합니다`, `티브이ㄴㅅ`)
    - 일반적인 정상 문자(HAM)에서는 절대 등장할 수 없는 고유 기호와 단어 혼종(High Entropy)

2. **길이 제한 (문자열 우선, 문장 차선)**
    - 추출할 시그니처는 가능하면 **9 ~ 20 bytes** 사이의 강렬한 **'문자열(String)'**에 집중하라. (한글은 2바이트, 공백/기호/영문 1바이트 기준)
    - 20 bytes 이내로 뚜렷한 특징을 잡기 애매하다면, 최대 **39 ~ 40 bytes** 수준의 긴 **'문장(Sentence)'** 조각으로 범위를 넓혀라.
    - 너무 짧으면 정상 문자를 차단하는 오탐(False Positive) 위험이 매우 큼.

3. **절대 제외 항목 (블랙리스트 - 오탐 차단)**
    - `(광고)`, `[광고]` 등과 같은 광고 표기 의무 문구는 절대 포함하지 마라.
    - `무료거부 080-xxx-xxxx` 형태의 단순 수신거부 안내 문구는 단독 시그니처로 잡지 마라. (그 주변의 악성 식별자가 결합된 경우는 예외)

**[판단 로직]**
위 규칙에 부합하는 치명적인 시그니처를 찾았다면 `decision: "use_string"` (9~20 bytes) 또는 `decision: "use_sentence"` (39~40 bytes)로 결정하고 추출해라.
만약 도저히 추출할 만한 고유 시그니처가 없거나, 평범한 상용구뿐이라 정상 문자를 오탐할 위험이 크다면 단 1초도 고민하지 말고 `{"decision": "unextractable"}`을 뱉고 포기하라. 억지로 만들 필요는 절대 없다.

반드시 지시된 JSON 규격 단일 객체만 리턴하라."""

    USER_TEMPLATE = """message_id: {message_id}
original_text: {original_text}

is_garbage_obfuscation: {is_garbage_obfuscation}

출력(JSON):
{{
  "message_id": "{message_id}",
  "decision": "use_string" | "use_sentence" | "unextractable",
  "signature": "추출한 원본 부분 문자열",
  "risk": "low" | "medium" | "high",
  "reason": "왜 이 문자열이 가장 고유하고 강력한 시그니처인지 1~2줄 요약 (오탐 여부 등)"
}}"""

    REPAIR_SYSTEM_PROMPT = """이전 출력이 검증에 실패했다.
가장 중요한 원칙은 **signature가 original_text 내에 정확히 존재해야(오타/변형 불가) 하며, 길이 제한(9~40 bytes) 및 블랙리스트를 준수해야 한다.**
반드시 JSON 단일 객체로만 다시 출력해라."""

    REPAIR_USER_TEMPLATE = """검증 실패 사유: {error_reason}

이전 출력: {previous_output_json}

동일 입력 원본(original_text): {original_text}
is_garbage_obfuscation: {is_garbage_obfuscation}

규칙에 맞춰 JSON을 다시 출력해라."""

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
        original_text = state.get("original_text", "")
        is_garbage = 'true' if state.get("is_garbage_obfuscation", False) else 'false'
        
        if is_repair:
            system_prompt = self.REPAIR_SYSTEM_PROMPT
            user_prompt = self.REPAIR_USER_TEMPLATE.format(
                error_reason=state.get("error", "Unknown Error"),
                previous_output_json=json.dumps(state.get("final_result", {}), ensure_ascii=False),
                original_text=original_text,
                is_garbage_obfuscation=is_garbage
            )
        else:
            system_prompt = self.SYSTEM_PROMPT
            user_prompt = self.USER_TEMPLATE.format(
                message_id=message_id,
                original_text=original_text,
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
                if is_fallback: content = f"__FALLBACK_{current_model}__\\n" + content
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
            parts = content.split("__\\n", 1)
            if len(parts) == 2:
                fallback_model, content = parts[0].replace("__FALLBACK_", ""), parts[1]
        try:
            parsed = json.loads(re.sub(r'\\s*```$', '', re.sub(r'^```(?:json)?\\s*', '', content.strip())))
            if fallback_model and "reason" in parsed:
                parsed["reason"] = f"[IBSE_Fallback: {fallback_model}] " + parsed["reason"]
            return parsed
        except Exception as e:
            return {"error": "JSON Parse Error"}

async def select_signature_node(state: IBSEState) -> dict:
    selector = LLMSelector()
    is_repair = bool(state.get("error"))
    result = await selector.select(state, is_repair=is_repair)
    
    # Update byte_len natively
    if "signature" in result and result["signature"]:
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
''')

# Rewrite validator.py
with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\backend\app\agents\ibse_agent\validator.py', 'w', encoding='utf-8') as f:
    f.write('''from .state import IBSEState
from .utils import get_cp949_byte_len

class Validator:
    def validate(self, text_context: str, result: dict) -> dict:
        decision = result.get("decision")
        signature = result.get("signature")
        
        if decision == "unextractable":
            return result
        
        if not signature:
            return {**result, "error": "Signature is empty but decision is not unextractable"}
        
        # 1. Exact Match Check (No Hallucination!)
        if signature not in text_context:
            return {**result, "error": "Strict extraction failed. The extracted signature does NOT exist exactly within the original message text."}
            
        # 2. Blacklist Check
        blacklist = ["광고", "(광고)", "[광고]", "080-", "무료거부", "수신거부", "무료수신거부"]
        for b in blacklist:
            if b in signature:
                return {**result, "error": f"Signature contains blacklisted word: {b}"}
                
        # 3. Byte Length constraints
        byte_len = get_cp949_byte_len(signature)
        if byte_len == -1: # Fallback calculation if encoding fails
             byte_len = len(signature) * 2
             
        if byte_len < 9:
             return {**result, "error": f"Signature is too short ({byte_len} bytes). Must be at least 9 bytes."}
             
        if decision == "use_string" and byte_len > 25:
             # Allowed up to 25 to give tiny flexibility, but flag error if too long
             return {**result, "error": f"Decision is use_string but length is {byte_len} bytes. Should be <= 20."}
             
        if decision == "use_sentence" and byte_len > 45:
             return {**result, "error": f"Decision is use_sentence but length is {byte_len} bytes. Should be <= 40."}
             
        return result

def validate_node(state: IBSEState) -> dict:
    original_text = state.get("original_text", "")
    final_result = state.get("final_result")
    
    if not final_result:
        return {"error": "No final_result to validate"}
    
    validator = Validator()
    validated_result = validator.validate(original_text, final_result)
    
    state_update = {"final_result": validated_result}
    if "error" in validated_result:
         state_update["error"] = validated_result["error"]
    else:
         state_update["error"] = None
         
    return state_update
''')
