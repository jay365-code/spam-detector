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
    SYSTEM_PROMPT = """너는 IBSE(Intelligence Blocking Signature Extractor)의 핵심 추출 엔진이다.
목표는 **이미 스팸으로 판명된 메시지**에서, 향후 동일/유사 공격을 효율적으로 차단할 수 있는 '차단 시그니처(문자열/문장)'를 추출하는 것이다.

**[명심할 원칙: 절대 창작(Hallucination) 금지]**
- 너는 오직 주어진 `match_text`(공백이 완전히 제거된 압축 텍스트) 안에서 일치하는 부분 문자열(substring)만 가위로 오려내듯 발췌(Extraction)해야 한다.
- 어조를 바꾸거나, 띄어쓰기를 새로 넣거나, 문맥을 요약하는 등의 **임의 변형은 절대 금지**된다. 원본 텍스트에 있는 글자 그대로 추출해라!

**[스팸태깅 작업 절차 매뉴얼 준수 (Extraction Rules)]**
1. **1순위 (최우선 타겟): 특수문자나 한글을 사용한 변형 URL 추출 (반드시 시그니처에 포함)**
    - 예) `YⓞNⓖ20⑤.com`, `jk819ⓟⓓ.com`, `헤이접속쩜콤` 등
    - 불완전한 도메인(예: `nike26.`, `youtube.com`)이라도 접속 주소 형태면 무조건 1순위 타겟이다. 스팸 텍스트 내용보다 접속 주소(URL) 자체가 훨씬 치명적이고 고유한 차단 식별자이므로, 아무리 다른 문구가 자극적이더라도 **반드시 URL을 시그니처의 중심으로 잡아라!**
2. **2순위: 한글을 사용한 변형 URL 추출**
    - 예) `bit.ly/로얄7468`, `신규이벤중.p-e.kr`, `왕초문의.가기.cc`
3. **3순위: 위 URL이 없다면, 자음/모음을 분리한 고유 문자열 변형 추출**
    - 예) `님BAND에초ㄷH합니다`, `이터내+티브이ㄴㅅ`
4. **4순위: 위 형태조차 없다면, HAM 메시지에 절대 포함되지 않을 것 같은 일반 고유 문자열로 추출**

- 추출 길이 제한: 순수 한글/영문/특수기호 혼합하여 39~40 bytes 내외 분량. 문자열 개수와 상관없이 CP949 바이트 기준 39~40바이트를 채워라.
- 만약 짧은 단문이어서 애초에 39 bytes가 안 된다면, 메시지 **처음부터 끝까지 원문 전체**를 1글자도 변경 없이 그대로 추출해 `use_sentence`를 선택한다.

[최우선 순위 (KISA 가이드라인 강제 사항)]
1. (최우선) 본문 내에 URL(http, bit.ly, p-e.kr 등 모든 형태의 인터넷 주소)이 단 1개라도 존재한다면, **반드시 그 URL을 포함하여** 시그니처를 추출하라. 
   - 🚫 [초절대 금지 - 대량 오탐 경보] 단축 URL(bit.ly, me2.do 등)이나 범용 플랫폼 도메인(youtube.com, naver.com 등)의 **공통 도메인 앞부분만(예: "bit.ly/" 또는 "youtube.com") 뚝 떼어내어 9~20바이트 시그니처("use_string")로 단독 추출하는 것은 절대 금지**한다. 이렇게 하면 전 국민의 정상 링크마저 모조리 스팸으로 연쇄 차단되는 대참사가 발생한다! 
   - ✅ URL을 시그니처로 삼으려면 반드시 뒤에 붙는 고유 식별자/Path (예: `bit.ly/AbCdEf`) 전체가 온전히 포함되거나, 도메인 주변의 악성 한글 문맥이 강하게 결합되어야 한다. 
   - ✅ 만약 고유 Path가 너무 길어서 20바이트(`use_string`) 안에 도저히 안 담긴다면, URL을 억지로 끊어서 도메인만 남기지 마라! 그럴 때는 무조건 **문장형(`use_sentence`, 39~40바이트)**으로 결정을 바꾸어 URL 전체와 스팸 문맥 덩어리가 통째로 넉넉히 포함되게 추출하라!
   - ⚠️ 단, 'is_safe_url_injection' 플래그가 'true'로 설정되어 있다면 이 규칙은 예외다! 이는 스패머가 필터를 우회하려고 정상 도메인(유튜브, 네이버 등)을 방패막이 조끼처럼 입혀놓은 '위장 시그니처'이므로, 이때는 **절대로 URL을 시그니처에 포함시키지 말고** 철저히 배제한 채 순수 악성 텍스트(예: "토지노 꽁머니") 부분만 추출하라!
   - ⚠️ **[중요] 만약 `obfuscated_urls` (복원된 난독화 도메인) 목록이 제공되었다면, 이는 원본 텍스트 내에 특수기호나 한글로 교묘하게 변형된 도메인(예: `ariⓐⓔ6.com`, `점켬` 등)이 숨어있다는 뜻이다. 이때 시그니처로는 복원된 영문 도메인이 아니라, 원문(`match_text`)에 존재하는 '난독화된 원본 문자열 자체'를 찾아내어 반드시 포함시켜야 한다! (시그니처는 무조건 원문과 100% 일치해야 함)**
2. (차순위) 연락처 명시: 전화번호(예: 010-1234-5678), 텔레그램 ID(예: @SpamID) 등이 식별의 핵심이 되므로 가급적 포함하라.
3. (극단적 난독화) URL이나 번호가 아예 없는데, 자음/모음이 분절되거나(`ㅋ ㅏ ㅈ ㅣ ㄴ ㅗ`) 특수문자가 비정상적으로 섞인(`ㅅ_ㅏ+ㄷ.ㅏ:ㄹl`) 극악의 난독화 구간이 있다면 그 블록 전체를 추출하라.

4. **절대 제외 항목 (블랙리스트 - 오탐 차단)**
    - `(광고)`, `[광고]` 등과 같은 광고 표기 의무 문구는 절대 포함하지 마라.
    - `무료거부 080-xxx-xxxx` 형태의 단순 수신거부 안내 문구는 단독 시그니처로 잡지 마라. (그 주변의 악성 식별자가 결합된 경우는 예외)

**[판단 로직]**
위 규칙에 부합하는 치명적인 시그니처를 찾았다면 길이에 따라 `decision: "use_string"` (9~20 bytes) 또는 `decision: "use_sentence"` (39~40 bytes)로 결정하고 추출해라. 중간 길이(21~38 bytes)는 없다. (한글은 글자당 2바이트로 계산되므로 5글자 이상이면 대체로 9바이트를 넘는다.)
만약 원문 어딘가에 URL이나 접속 유도 도메인(`nike26.` 등 불완전/변형 형태 포함)이 한 글자라도 존재한다면, 반드시 `identified_url_or_domain` 필드에 먼저 기입해라. 그리고 나서 `signature`는 그 도메인을 **누락 없이 반드시 포함하여** 생성해라. URL을 빼놓고 일반 문구만으로 시그니처를 만드는 것은 중대한 매뉴얼 위반이다! URL이 아예 없는 메시지일 때만 null로 둔다.
만약 도저히 추출할 만한 고유 시그니처가 없거나, 평범한 상용구뿐이라 정상 문자를 오탐할 위험이 크다면 단 1초도 고민하지 말고 `{"decision": "unextractable"}`을 뱉고 포기하라. 억지로 만들 필요는 절대 없다.

반드시 지시된 JSON 규격 단일 객체만 리턴하라."""

    USER_TEMPLATE = """message_id: {message_id}
is_garbage_obfuscation: {is_garbage_obfuscation}
is_safe_url_injection: {is_safe_url_injection}

[추출 타입]
1) "use_sentence": 39~40 bytes 길이의 긴 시그니처 추출
- 추출 길이 제한: 순수 한글/영문/특수기호 혼합하여 39~40 bytes 분량 (글자수 무관)
- 만약 짧은 단문이어서 애초에 39 bytes가 안 된다면, 메시지 **처음부터 끝까지 원문 전체**를 1글자도 변경 없이 그대로 추출해 `use_sentence`를 선택한다.

2) "use_string": 9~20 bytes 사이의 짧은 단어장/키워드 배열 추출 (가장 흔함)
- 추출 길이 제한: 순수 문자열 기준 5글자 ~ 20글자 사이 (글자수는 5글자 이상이면 되고, 한글 기호 조합 시 9바이트 이상이면 모두 충족함. 예: `=이*영*아=` 는 7글자이며 10바이트이므로 완벽한 타겟 대상임!)

---
[INPUT DATA]
- 분석 대상 메시지 (공백 제거 상태): {match_text}
- 극단적 난독화(Garbage Obfuscation) 여부: {is_garbage_obfuscation}
- 위장 URL 방패막이(Safe URL Injection) 여부: {is_safe_url_injection}
- 복원된 난독화 도메인 (obfuscated_urls): {obfuscated_urls}

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
is_safe_url_injection: {is_safe_url_injection}
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
        is_garbage = 'true' if state.get("is_garbage_obfuscation", False) else 'false'
        is_safe_url_injection = 'true' if state.get("is_safe_url_injection", False) else 'false'
        obfuscated_urls = json.dumps(state.get("obfuscated_urls", []), ensure_ascii=False)
        
        if is_repair:
            system_prompt = self.REPAIR_SYSTEM_PROMPT
            user_prompt = self.REPAIR_USER_TEMPLATE.format(
                error_reason=state.get("error", "Unknown Error"),
                previous_output_json=json.dumps(state.get("final_result", {}), ensure_ascii=False),
                match_text=match_text,
                is_garbage_obfuscation=is_garbage,
                is_safe_url_injection=is_safe_url_injection,
                obfuscated_urls=obfuscated_urls,
                message_id=message_id
            )
        else:
            system_prompt = self.SYSTEM_PROMPT
            user_prompt = self.USER_TEMPLATE.format(
                message_id=message_id,
                match_text=match_text,
                is_garbage_obfuscation=is_garbage,
                is_safe_url_injection=is_safe_url_injection,
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
        # 만약 위장 방패막이 도메인이면, 절대로 강제 삽입 방어 로직을 실행하지 않고 LLM이 누락한 것을 존중함
        is_safe_url_injection = state.get("is_safe_url_injection", False)
        
        if identified_url in match_text and identified_url not in sig_text and not is_safe_url_injection:
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
