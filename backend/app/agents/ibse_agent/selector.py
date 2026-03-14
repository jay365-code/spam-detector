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

**[판단 최우선 원칙: 특이점(Unique Anchor) 추출 로직]**
너는 메시지 내용을 해석하는 것이 아니라, 문장구조의 '특이도(Uniqueness)'와 '결합의 이질성'을 평가한다. 
평범한 단어(Low Entropy)는 버리고, 정상적인 문장에서는 절대 우연히 조합될 수 없는 기형적인 텍스트 덩어리(High Entropy)를 찾아라.

1. **최우선 (Must Extract) : 구조적 이질성과 고유 식별 블록 (Structural Anomaly & Unique Id-Block)**
    - 특정 단어의 의미나 종류(이름, 번호, 기호 등)는 중요하지 않다. 메시지의 일반적인 문장(템플릿) 흐름과 구조적으로 완전히 단절된 채, 숫자, 기호, 특이한 명사들이 인위적으로 뭉쳐진 20~40바이트의 덩어리를 찾는다. 
    - 예: "바밤바 둘 리 ( 010 2387 7373 )", "국&태봉# ☎010-6851", "V-VIP 입장 t.me/abcd"
    - 이 덩어리는 스팸 발송자가 자신을 식별받기 위해 삽입한 '고유 서명(Signature)'일 확률이 99%다. 주변 문맥과 이 고유 정보가 한 덩어리로 묶인 후보(use_20 또는 use_40)를 최우선으로 선택하라.
    - 판단 기준: "이 20~40바이트 문자열 구성을 일반인이나 다른 기업이 토씨 하나 안 틀리고 우연히 똑같이 사용할 확률이 0%에 가까운가?" -> Yes라면 완벽한 시그니처다.

2. **차선 (High Priority) : 난독화 및 필터 회피 패턴 (Obfuscation Patterns)**
    - 일반적인 단어 사이에 특수기호나 자모음 분리, 기이한 영어/숫자 조합이 끼어있는 형태 ('대.출', 'ㅋr톡', 'vt⑨8g'). 이 자체로 세상에 유일한(Unique) 문자열이 되므로 좋은 시그니처다.
    - **[우선순위 절대 규칙]** 만약 후보군 중에 이런 강력한 난독화(`■최'대`, `인Eㅓ냇`) 기법이 포함되어 있다면, 그 주변이나 끝부분에 '무료거부', '상담' 같은 추출 금지(평범한 문구) 조건이 섞여 있더라도 **무조건 난독화 앵커를 우선순위로 두고 타협 없이 시그니처로 추출하라. 딜레마에 빠지지 마라.**

3. **절대 금지 및 조기 포기(Fail-fast) : 파편화된 정보 및 범용/상용구 문구**
    - **파편화된 정보 금지:** "010-1234", "김팀장" 처럼 우연히 겹칠 수 있는 짧고 흔한 정보의 조각만 단독으로 떼어내지 마라.
    - **[핵심] 일상 대화형 결합 금지:** 전화번호 주변이 오직 "여기로 연락주세요", "담당자", "무료거부 080" 같은 평범한 템플릿으로만 이루어져 있다면 오탐 확률이 크므로 절대 추출하지 않는다.
    - **예외 허용 (식별자 결합):** 단, "독 ZT03 무료거부 080" 처럼 **일반 상용구 옆에 고유한 식별자/난독화 코드(ZT03 등)가 강하게 결합되어 있다면 훌륭한 시그니처**이므로 적극 추출하라.
    - **[조기 포기 규칙 (Fail-fast)]:** 만약 제공된 후보 5개가 전부 고유 식별자 없이 흔한 상용구(무료거부, 상담 등)나 평범한 문장으로만 이루어져 있어 안전한 추출이 불가능하다고 판단되면, **억지로 다른 부분을 떼어내려 고민하지 마라. 단 1초도 고민하지 말고 즉시 `{"decision": "unextractable"}`을 뱉고 출력을 종료해라. 억지로 추출하는 것은 시스템 장애(Timeout)의 원인이 된다.**


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
        
        logger.debug(f"[IBSE Candidates] 20-byte: {c20_json}")
        logger.debug(f"[IBSE Candidates] 40-byte: {c40_json}")
        
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
            current_model = self.model_name
            
            # [Fix] Generation Dilemma Fallback: If prior attempt timed out, swap the model.
            is_fallback = getattr(self, "_use_fallback", False)
            if is_fallback:
                fallback_sub = os.getenv("LLM_SUB_MODEL", "gemini-3.1-flash-lite-preview").strip().strip("'")
                current_model = fallback_sub
                logger.warning(f"[IBSE] Fallback mode active: Switching model to {current_model} to break Dilemma.")

            client_instance = self._get_cached_client(provider, api_key, current_model)
            
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
                    response = await asyncio.wait_for(client_instance.chat.completions.create(**_kwargs), timeout=45.0)
                    content = response.choices[0].message.content
                    
                elif provider == "GEMINI":
                    from langchain_core.messages import SystemMessage, HumanMessage
                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt)
                    ]
                    response = await asyncio.wait_for(client_instance.ainvoke(messages), timeout=45.0)
                    
                    # [Gemini Safety Filter Block Check]
                    content = _normalize_llm_content(response.content)
                    if not content:
                        finish_reason = response.response_metadata.get("finish_reason", "")
                        meta_str = str(response.response_metadata)
                        if finish_reason == "SAFETY" or "PROHIBITED_CONTENT" in meta_str or "block_reason" in meta_str:
                            logger.warning(f"[LLMSelector] Gemini response blocked by safety filters: {meta_str}")
                            # IBSE relies on extracting signatures. If it's too sexually explicit or dangerous to process,
                            # we can gracefully degrade to "unextractable" instead of hanging or crashing.
                            return '{"decision": "unextractable"}'
                    
                elif provider == "CLAUDE":
                    model = self.model_name if "claude" in self.model_name else "claude-3-haiku-20240307"
                    response = await asyncio.wait_for(client_instance.messages.create(
                        model=model,
                        max_tokens=1024,
                        system=system_prompt,
                        messages=[
                            {"role": "user", "content": user_prompt}
                        ]
                    ), timeout=45.0)
                    content = response.content[0].text
                else:
                    raise Exception(f"Unsupported Provider: {provider}. No retry.")
                
                key_manager.report_success(provider)
                
                # Attach a secret flag to the content so _parse_json knows it was a fallback
                if is_fallback:
                    content = f"__FALLBACK_{current_model}__\n" + content
                return content
                
            except (Exception, asyncio.TimeoutError) as e:
                error_msg = str(e).lower()
                is_google_quota_error = False
                is_timeout = isinstance(e, asyncio.TimeoutError) or "timeout" in error_msg
                
                if provider == "GEMINI":
                    try:
                        import google.api_core.exceptions
                        if isinstance(e, (google.api_core.exceptions.ResourceExhausted, google.api_core.exceptions.TooManyRequests)):
                            is_google_quota_error = True
                        if isinstance(e, google.api_core.exceptions.DeadlineExceeded):
                            is_timeout = True
                    except ImportError:
                        pass

                # [USER REQUEST FIX] Quota에러 감지 및 키 로테이션을 Timeout 감지보다 먼저 실행해야 함.
                # 이유: Gemini API는 할당량 초과 시 'DeadlineExceeded' 타입의 타임아웃 에러를 자주 발생시키기 때문.
                if is_google_quota_error or "quota" in error_msg or "rate" in error_msg or "429" in error_msg or "limit" in error_msg or "resource exhausted" in error_msg:
                    logger.warning(f"[LLMSelector] 429/Quota Detected. Rotating key...")
                    is_rotated = key_manager.rotate_key(provider, failed_key=api_key)
                    if not is_rotated:
                        logger.error(f"[LLMSelector] Global exhaustion reached for {provider}.")
                        raise Exception(f"{provider} quota globally exhausted. No retry.") from e
                    raise e

                if is_timeout:
                    self._use_fallback = True  # Activate fallback for the next retry attempt
                    logger.warning(f"[LLMSelector] Timeout Detected (45s+). Suspected Generation Dilemma. Switching to Sub-Model for retry.")
                    raise Exception("Async LLM Timeout") from e
                    
                logger.error(f"LLM Call Error: {e}")
                raise e

        try:
            content = await do_call()
            return self._parse_json(content)
        except Exception as e:
            logger.error(f"[LLMSelector] Final Call failed after retries: {e}")
            return {"error": str(e), "decision": "unextractable"}

    def _parse_json(self, content: str) -> dict:
        import re
        fallback_model = None
        if content.startswith("__FALLBACK_"):
            parts = content.split("__\n", 1)
            if len(parts) == 2:
                fallback_info = parts[0].replace("__FALLBACK_", "")
                fallback_model = fallback_info
                content = parts[1]
                
        try:
            clean_content = content.strip()
            clean_content = re.sub(r'^```(?:json)?\s*', '', clean_content)
            clean_content = re.sub(r'\s*```$', '', clean_content)
            parsed = json.loads(clean_content)
            
            # [User Request] Append fallback notice to the reason field
            if fallback_model and isinstance(parsed, dict) and "reason" in parsed:
                parsed["reason"] = f"[IBSE_Fallback: {fallback_model}] " + parsed["reason"]
                
            return parsed
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
