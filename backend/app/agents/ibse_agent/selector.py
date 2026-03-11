import os
import json
import dataclasses
import asyncio
from typing import List, Optional
from .state import IBSEState, Candidate
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log


def _normalize_llm_content(content) -> str:
    """Gemini 등 list 형태 content를 str로 변환"""
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
    return str(content)
import logging
logger = logging.getLogger(__name__)

class LLMSelector:
    """
    Selects the best signature candidate using LLM.
    """
    
    SYSTEM_PROMPT = """너는 IBSE(Intelligence Blocking Signature Extractor)의 판단 엔진이다.
목표는 **이미 스팸으로 판명된 메시지**에서, 향후 동일/유사 공격을 효율적으로 차단할 수 있는 '문자열 시그니처'를 추출하는 것이다.

**[입력 컨텍스트 (Input Context)]**
- 입력된 메시지는 앞단(LLM 기반 Content Agent)에서 이미 **SPAM**으로 분류되었다.
- 따라서 네가 다시 스팸 여부를 판단할 필요는 없다. 오직 **"이 스팸을 가장 효과적으로 차단할 고유 패턴이 있는가?"**에만 집중하라.

**[전략적 제약 사항 (Strategic Constraints)]**
- **시스템 자원 한계**: 시그니처 차단 리스트는 최대 10,000개로 제한되어 있다. 따라서 **확실하고, 재사용성이 높으며, 치명적인** 패턴만 선별적으로 등록해야 한다.
- **IBSE의 역할 정의**: 이 시스템은 ML이 놓친 것을 잡는 것이 아니라, 스팸을 **더 싸고 빠르게(단순 문자열 매칭) 차단하기 위한 보조 장치**다.
- **억지 추출 금지**: 확실한 시그니처가 없다면 굳이 추출하지 마라. 이미 ML이 차단했으므로, 애매한 시그니처를 만들어 리소스를 낭비할 필요가 없다. **'확실하지 않으면 `unextractable`'**이 원칙이다.

중요 제약:
- 시그니처는 반드시 후보 목록에서만 선택한다. 후보 밖의 문자열을 새로 만들거나 변형/정규화/요약하지 않는다.
- 후보는 match_text에서 잘라낸 연속 substring이며, CP949 바이트 길이가 제공된다.
- 20바이트 이하 후보로 충분히 특이하고 스팸 앵커가 있으면 use_20을 선택한다.
- 20바이트로는 일반적이거나 오탐 위험이 크면 40바이트 이하 후보 중 선택(use_40).
- 40바이트에서도 일반 문구 중심이거나 오탐 위험이 크면 unextractable을 선택한다.

**[판단 우선순위 (Decision Hierarchy)]**
1. **최우선 (Must Extract)**: ML을 우회하려는 시도
    - **변형/은어**: '대.출', 'ㅋr톡', 'S.E.X', '은밀한 대화' 등 특수문자 삽입, 자모 분리.
    - **난독화된 행동 유도**: "[OOO] 검색하세요" 등을 변형하여 쓴 경우.
2. **차선 (High Priority)**: 발신자 특정 (재사용성 높음)
    - **고유 식별 정보**: 개인 휴대폰 번호(010), 카톡/텔레그램 ID, 특정 상담원 이름(예: '김미영 팀장').
3. **보류/제외 (Consider Unextractable)**: 일반적인 스팸
    - **단순 홍보 문구**: "최고 수익 보장", "지금 가입 시 혜택", "무료 거부" 등. 누구나 쓸 수 있는 말은 차단 리스트에 넣어도 효과가 낮다. -> **`unextractable` 권장**.
    - **080 수신거부 번호**: 공용 번호이므로 제외.
    - **범용 문구**: 메시지의 핵심이 URL뿐이고 나머지가 "100% 증정", "가입 이벤트" 등 누구나 쓸 수 있는 멘트라면 `unextractable`을 선택.

**[특수 규칙: URL이 포함된 경우 (Special Rule for URLs)]**
- **정상적인 URL**(`http`, `www`, `naver.com` 등 **깨끗한 형태**)이 포함된 경우:
    - 리소스 낭비를 막기 위해 **`unextractable`을 선택**한다. (URL Agent 위임)
- **난독화된/변형된 URL**(`vt⑨8g.COm`, `k-bank. xyz` 등)이 포함된 경우:
    - 이는 정상 URL이 아니므로, **시그니처로 추출해야 한다**. (최우선 순위 적용)
    - 예: `vt⑨8g.COm` -> 추출 허용.
    - 예: `www.google.com` -> 추출 금지 (`unextractable`).

반드시 JSON 단일 객체만 출력한다. 추가 텍스트 금지."""

    USER_TEMPLATE = """message_id: {message_id}
match_text: {match_text}

candidates_20: {candidates_20_json}

candidates_40: {candidates_40_json}

출력(JSON):
{{
  "message_id": "{message_id}",
  "decision": "use_20" | "use_40" | "unextractable",
  "chosen_candidate_id": "...",
  "signature": "...",
  "byte_len_cp949": 0,
  "start_idx": 0,
  "end_idx_exclusive": 0,
  "risk": "low" | "medium" | "high",
  "reason": "한 줄 근거(특이성/앵커/오탐위험)"
}}"""

    REPAIR_SYSTEM_PROMPT = """이전 출력이 검증에 실패했다.
후보 목록에서만 다시 선택해라. 반드시 JSON 단일 객체로만 출력해라.
signature는 match_text[start:end]와 일치해야 하며 CP949 바이트 제한을 준수해야 한다."""

    REPAIR_USER_TEMPLATE = """검증 실패 사유: {error_reason}

이전 출력: {previous_output_json}

동일 입력:
message_id: {message_id}
match_text: {match_text}
candidates_20: {candidates_20_json}
candidates_40: {candidates_40_json}

위 조건을 만족하는 JSON만 다시 출력해라."""

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
        """런타임에 LLM_MODEL 반영 (설정 변경 시 즉시 적용)"""
        return os.getenv("LLM_MODEL", "gpt-4o")

    @property
    def provider(self) -> str:
        """런타임에 LLM_PROVIDER 반영"""
        return os.getenv("LLM_PROVIDER", "OPENAI").upper()

    async def select(self, state: IBSEState, is_repair: bool = False) -> dict:
        message_id = state.get("message_id", "unknown")
        match_text = state.get("match_text", "")
        c20 = state.get("candidates_20", [])
        c40 = state.get("candidates_40", [])
        
        # Serialize Candidates
        c20_json = json.dumps([dataclasses.asdict(c) for c in c20], ensure_ascii=False)
        c40_json = json.dumps([dataclasses.asdict(c) for c in c40], ensure_ascii=False)
        
        if is_repair:
            system_prompt = self.REPAIR_SYSTEM_PROMPT
            user_prompt = self.REPAIR_USER_TEMPLATE.format(
                error_reason=state.get("error", "Unknown Error"),
                previous_output_json=json.dumps(state.get("final_result", {}), ensure_ascii=False),
                message_id=message_id,
                match_text=match_text,
                candidates_20_json=c20_json,
                candidates_40_json=c40_json
            )
        else:
            system_prompt = self.SYSTEM_PROMPT
            user_prompt = self.USER_TEMPLATE.format(
                message_id=message_id,
                match_text=match_text,
                candidates_20_json=c20_json,
                candidates_40_json=c40_json
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
            client_instance = self._get_cached_client(provider, api_key, self.model_name)
            
            try:
                if provider == "OPENAI":
                    _no_temp_prefixes = ("o1", "o3", "o4", "gpt-5")
                    _supports_temp = not any(self.model_name.startswith(p) for p in _no_temp_prefixes)
                    _kwargs = {
                        "model": self.model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "response_format": {"type": "json_object"},
                    }
                    if _supports_temp:
                        _kwargs["temperature"] = 0.0
                    response = await asyncio.wait_for(client_instance.chat.completions.create(**_kwargs), timeout=120.0)
                    content = response.choices[0].message.content
                    
                elif provider == "GEMINI":
                    from langchain_core.messages import SystemMessage, HumanMessage
                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt)
                    ]
                    response = await asyncio.wait_for(client_instance.ainvoke(messages), timeout=120.0)
                    content = _normalize_llm_content(response.content)
                    
                elif provider == "CLAUDE":
                    model = self.model_name if "claude" in self.model_name else "claude-3-haiku-20240307"
                    response = await asyncio.wait_for(client_instance.messages.create(
                        model=model,
                        max_tokens=1024,
                        system=system_prompt,
                        messages=[
                            {"role": "user", "content": user_prompt}
                        ]
                    ), timeout=120.0)
                    content = response.content[0].text
                else:
                    raise Exception(f"Unsupported Provider: {provider}. No retry.")
                
                key_manager.report_success(provider)
                return content
                
            except (Exception, asyncio.TimeoutError) as e:
                error_msg = str(e).lower()
                is_google_quota_error = False
                if provider == "GEMINI":
                    try:
                        import google.api_core.exceptions
                        if isinstance(e, (google.api_core.exceptions.ResourceExhausted, google.api_core.exceptions.TooManyRequests)):
                            is_google_quota_error = True
                    except ImportError:
                        pass

                is_timeout = isinstance(e, asyncio.TimeoutError) or "timeout" in error_msg
                if is_timeout:
                    logger.warning(f"[LLMSelector] Timeout Detected (120s). Tenacity will backoff and retry.")
                    raise Exception("Async LLM Timeout") from e

                if is_google_quota_error or "quota" in error_msg or "rate" in error_msg or "429" in error_msg or "limit" in error_msg or "resource exhausted" in error_msg:
                    logger.warning(f"[LLMSelector] 429/Quota Detected. Rotating key...")
                    is_rotated = key_manager.rotate_key(provider, failed_key=api_key)
                    if not is_rotated:
                        logger.error(f"[LLMSelector] Global exhaustion reached for {provider}.")
                        raise Exception(f"{provider} quota globally exhausted. No retry.") from e
                    raise e
                    
                logger.error(f"LLM Call Error: {e}")
                raise e

        try:
            content = await do_call()
            return self._parse_json(content)
        except Exception as e:
            logger.error(f"[LLMSelector] Final Call failed after retries: {e}")
            return {"error": str(e), "decision": "unextractable"}

    def _parse_json(self, content: str) -> dict:
        try:
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Error: {e} | Content: {content}")
            return {"error": "JSON Parse Error", "raw_content": content}

async def select_signature_node(state: IBSEState) -> dict:
    match_text = state.get("match_text", "")
    if not match_text:
        return {"error": "No match_text"}
    
    selector = LLMSelector()
    is_repair = bool(state.get("error"))
    result = await selector.select(state, is_repair=is_repair)
    
    # Post-processing: Ensure 'signature' matches 'text_original' of the chosen candidate
    candidate_id = result.get("chosen_candidate_id")
    if candidate_id:
        # Find candidate in state
        all_candidates = state.get("candidates_20", []) + state.get("candidates_40", [])
        found_candidate = next((c for c in all_candidates if c.id == candidate_id), None)
        
        if found_candidate:
            # FORCE overwrite signature with original text to preserve spaces/format
            result["signature"] = found_candidate.text_original
            # Also ensure byte_len is consistent
            result["byte_len_cp949"] = found_candidate.byte_len_cp949
            
            # Update start/end indices? 
            # The indices in candidate are for match_text (normalized). 
            # If we want original indices, we'd need to store them in Candidate too. 
            # For now, let's just ensure the string value is correct.
            # (Validator checks inclusion: if we change signature to original, validator needs original text)
            
    return {
        "final_result": result,
        "llm_decision": result,
        "error": None if "error" not in result else result["error"]
    }
