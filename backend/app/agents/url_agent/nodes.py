import re
import unicodedata
import os
import json
import asyncio
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, retry_if_exception, before_sleep_log
from app.core.logging_config import get_logger
from app.core.llm_manager import key_manager
logger = get_logger(__name__)
import base64
from typing import Dict, Any, List
from urllib.parse import urlparse, quote
import idna  # Punycode 변환용

import google.api_core.exceptions
from bs4 import BeautifulSoup

from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate


from .state import SpamState
from app.core.constants import SPAM_CODE_MAP

# 유명/신뢰 도메인 리스트 (리다이렉트 후 이 도메인이면 HAM)
# ※ 주의: 사용자 생성 콘텐츠(UGC) 도메인은 포함하면 안 됨
TRUSTED_DOMAINS = [
    # 앱 스토어 (공식 앱 다운로드)
    "play.google.com",
    "apps.apple.com",
    "onestore.co.kr",
    "galaxy.store",
    # 공공기관 (정부, 공공기관)
    "go.kr",
    "or.kr",
]

# 사용자 생성 콘텐츠(UGC) 도메인 - 신뢰할 수 없음, Inconclusive 처리 대상
# 이 도메인들은 스팸에 악용될 수 있으므로 자동 HAM 처리 금지
UGC_DOMAINS = [
    "open.kakao.com",     # 카카오톡 오픈채팅
    "t.me",               # 텔레그램
    "telegram.me",        # 텔레그램
    "line.me",            # 라인 메신저
    "bit.ly",             # 단축 URL
    "tinyurl.com",        # 단축 URL
]

def is_trusted_domain(url: str) -> bool:
    """리다이렉트된 URL이 유명/신뢰 도메인인지 확인"""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # 먼저 UGC 도메인인지 체크 - UGC면 신뢰 불가
        for ugc in UGC_DOMAINS:
            if domain == ugc or domain.endswith("." + ugc):
                return False
        
        for trusted in TRUSTED_DOMAINS:
            # 정확히 일치하거나 서브도메인인 경우
            if domain == trusted or domain.endswith("." + trusted):
                return True
        return False
    except:
        return False

# Lazy load PlaywrightManager
_playwright_manager = None
def get_playwright_manager():
    global _playwright_manager
    if _playwright_manager is None:
        from .tools import PlaywrightManager
        _playwright_manager = PlaywrightManager()
    return _playwright_manager

async def close_playwright():
    global _playwright_manager
    if _playwright_manager:
        await _playwright_manager.stop()
        _playwright_manager = None

# [Optimization] Event-Loop Bound Cache: (provider_key_model, loop) -> client
_loop_bound_clients = {}

def get_llm():
    """
    .env 설정에 따른 LLM 인스턴스 반환 (캐싱 처리 및 max_retries=0 적용)
    """
    # Lazy imports for LLM providers
    from langchain_core.prompts import PromptTemplate
    
    provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    api_key = key_manager.get_key(provider)
    
    if not api_key:
        logger.warning(f"[URL_LLM] No key found for {provider}. Check LLMKeyManager.")
        raise ValueError(f"No API key available for {provider}")

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    cache_key = f"{provider}_{api_key}_{model_name}"
    dict_key = (cache_key, current_loop)

    if dict_key in _loop_bound_clients:
        return _loop_bound_clients[dict_key]

    logger.info(f"⚡ [URL_LLM] Instantiating new LLM client for {provider} ({model_name})")

    if provider == "GEMINI":
        from langchain_google_genai import ChatGoogleGenerativeAI
        safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
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
        
    _loop_bound_clients[dict_key] = client
    return client

async def analyze_with_vision(screenshot_b64: str, url: str, title: str, content_context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Gemini Vision API를 사용하여 스크린샷 기반 스팸 분석
    텍스트 분석이 Inconclusive일 때 호출됨
    """
    logger.info(f"[URL Agent] Starting Vision analysis for: {url}")
    
    try:
        # Lazy import gemini
        
        # 모델 선택 (환경변수에서 가져오거나 기본값 사용)
        model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")

        
        # Format code map for prompt (SPAM 코드만 사용, HAM 코드 제외)
        spam_codes_only = {k: v for k, v in SPAM_CODE_MAP.items() if not k.startswith("HAM")}
        code_list_str = "\n".join([f"    - '{k}': {v}" for k, v in spam_codes_only.items()])
        
        if content_context:
            content_label = "HAM" if not content_context.get("is_spam") else "SPAM"
            content_reason = content_context.get("reason", "")
            content_context_str = f"""
        [SMS Context (Reference)]
        - SMS Text: {content_context.get('original_message', '') if content_context.get('original_message') else 'N/A'}
        - Content Agent Verdict: {content_label}
        - Reason: {content_reason}
        """
        else:
            content_context_str = "[SMS Context] Not available"

        # Vision 프롬프트
        prompt = f"""
        You are a spam detection expert. Analyze this webpage screenshot and determine if it has **malicious/spam intent** or is **evading detection**.
        
        Page Title: {title}
        {content_context_str}
        
        **Your task: Determine if this page has SPAM INTENT, is EVADING, or is INCONCLUSIVE based on VISUAL CONTENT**
        
        **CRITICAL: HANDLING MISMATCH (Intent-Based Reasoning)**:
        - If SMS Context and Screenshot are logically unrelated (Mismatch):
        - **DO NOT** automatically flag as SPAM.
        - **Analyze the Intent of the Screenshot**: Does the visual content itself show harmful intent (Gambling, Adult, Scam, Phishing)?
        - If the page is **Harmless but Unrelated** (e.g., generic landing page, domain notice), mark as **Inconclusive** or match the **Content Agent's Hammer verdict**.
        - Only flag as **SPAM** if the visual content itself is independently malicious or clearly fraudulent.

        SPAM INTENT (requires CLEAR visual evidence):
        - Illegal gambling (chips, cards, slots, betting)
        - Adult/prostitution
        - Phishing (fake logins)
        - Illegal finance (unlicensed loans)
        - Fraud/Scam
        
        NOT SPAM (legitimate purposes - BUT MUST MATCH CONTEXT):
        - Delivery tracking (IF SMS is about delivery)
        - Normal business page (IF SMS is about that business)
        
        **CRITICAL RULE**: If you cannot verify the relation between SMS Context and this Screenshot (e.g., totally different content), mark as **Inconclusive**.

        Classification Codes (use only if SPAM):
{code_list_str}
        
        Response (JSON):
        {{
            "is_spam": boolean,
            "classification_code": "string or null if HAM",
            "spam_probability": float (0.0-1.0),
            "reason": "Korean explanation based on visual content vs context match"
        }}
        """
        

        
        # Vision API 호출 with Retry
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception(lambda e: "No retry." not in str(e)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        async def call_vision_api():
            provider = "GEMINI"
            keys = key_manager._keys_pool.get(provider, [])
            # User Request: Retry exactly the number of available keys to test each key once on Quota 429.
            max_quota_tries = max(1, len(keys))
            
            for attempt in range(max_quota_tries):
                if key_manager.is_quota_exhausted(provider):
                    raise Exception(f"{provider} quota exhausted (all keys). No retry.")
                    
                # Check for rotation inside retry if possible, or just use current key
                api_key = key_manager.get_key(provider)
                cache_key = f"{provider}_VISION_{api_key}_{model_name}"
                
                import asyncio
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    current_loop = None
                    
                dict_key = (cache_key, current_loop)
                global _loop_bound_clients
                if dict_key in _loop_bound_clients:
                    llm = _loop_bound_clients[dict_key]
                else:
                    logger.info(f"[URL Agent] Instantiating new Vision LLM client for {provider} ({model_name})")
                    
                    from langchain_google_genai import HarmCategory, HarmBlockThreshold
                    safety_settings = {
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0,
                        convert_system_message_to_human=True,
                        max_retries=0,
                        safety_settings=safety_settings
                    )
                    _loop_bound_clients[dict_key] = llm
                
                try:
                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{screenshot_b64}"}
                        ]
                    )
                    try:
                        response = await asyncio.wait_for(llm.ainvoke([message]), timeout=45.0)
                        key_manager.report_success(provider)
                        return response
                    except asyncio.TimeoutError as timeout_e:
                        logger.warning(f"[URL Agent] Vision API Timeout Detected. Attempting Fallback to Sub Model.")
                        raw_sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-flash-lite-preview")
                        sub_model = raw_sub_model.strip().strip("'").strip('"') if raw_sub_model else "gemini-3.1-flash-lite-preview"
                        if not sub_model:
                            sub_model = "gemini-3.1-flash-lite-preview"
                            
                        fallback_key = key_manager.get_key("GEMINI")
                        if fallback_key:
                            from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
                            safety_settings = {
                                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                            }
                            fallback_llm = ChatGoogleGenerativeAI(
                                model=sub_model,
                                google_api_key=fallback_key,
                                temperature=0,
                                convert_system_message_to_human=True,
                                max_retries=0,
                                safety_settings=safety_settings
                            )
                            try:
                                response = await asyncio.wait_for(fallback_llm.ainvoke([message]), timeout=45.0)
                                if hasattr(response, 'content') and isinstance(response.content, str):
                                    response.content = f"__FALLBACK_{sub_model}__\n" + response.content
                                key_manager.report_success("GEMINI")
                                return response
                            except Exception as fallback_e:
                                logger.error(f"[URL Agent Vision Fallback] Sub model failed: {fallback_e}")
                                raise Exception("Vision API Timeout (Fallback failed)") from timeout_e
                        else:
                            raise Exception("Vision API Timeout (No fallback key)") from timeout_e
                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # [Fix] Explicit type check for Google API errors (Gemini)
                    is_google_quota_error = False
                    try:
                        import google.api_core.exceptions
                        if isinstance(e, (google.api_core.exceptions.ResourceExhausted, google.api_core.exceptions.TooManyRequests)):
                            is_google_quota_error = True
                    except ImportError:
                        pass

                    is_timeout = False

                    if is_timeout:
                        pass

                    if is_google_quota_error or "quota" in error_msg or "rate" in error_msg or "429" in error_msg or "limit" in error_msg or "resource exhausted" in error_msg:
                        logger.warning(f"[URL Agent] Vision API Quota Detected. Error: {error_msg}")
                        logger.warning(f"[URL Agent] Vision API {provider} issue. Rotating key...")
                        # [동시성 개선] 실패한 키 전달 및 글로벌 소진 확인
                        is_rotated = key_manager.rotate_key(provider, failed_key=api_key)
                        
                        if not is_rotated:
                            logger.error(f"[URL Agent] Vision API Global exhaustion reached for {provider}.")
                            raise Exception(f"{provider} vision quota globally exhausted. No retry.") from e
                        
                        if attempt < max_quota_tries - 1:
                            logger.info(f"[URL Agent] Switching to next {provider} key instantly (Attempt {attempt+1}/{max_quota_tries})...")
                            continue
                        else:
                            logger.error(f"[URL Agent] All {provider} keys exhausted.")
                            key_manager.mark_exhausted(provider)
                            raise Exception(f"All {provider} keys exhausted. No retry.") from e
                    
                    # Log full traceback only for non-quota errors to reduce noise
                    logger.exception(f"[URL Agent] Vision API Error (Network/Transient)")
                    raise e
                    
            raise Exception(f"All {provider} keys repeatedly failed.")

        try:
            response = await call_vision_api()
        except Exception as e:
            logger.error(f"[URL Agent] Vision API failed after retries: {e}")
            return {"is_spam": None, "reason": f"Vision API Fail: {e}"}
        except RuntimeError as e:
            if "after shutdown" in str(e):
                logger.info("[URL Agent] Vision analysis cancelled due to executor shutdown.")
                return {"is_spam": None, "reason": "Stopped (System Shutdown)", "analysis_type": "vision"}
            raise e
        
        content = response.text
        
        # JSON 파싱
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        result_json = json.loads(content.strip())
        
        is_spam = result_json.get("is_spam")
        prob = result_json.get("spam_probability", 0.0)
        reason = result_json.get("reason", "")
        classification_code = result_json.get("classification_code")
        
        logger.info(f"[URL Agent] [Vision] Result: IS_SPAM={is_spam} | Code={classification_code} | Reason={reason}")
        
        return {
            "is_spam": is_spam,
            "spam_probability": prob,
            "classification_code": classification_code,
            "reason": f"[Vision 분석] {reason}",
            "analysis_type": "vision"
        }
        
    except Exception as e:
        logger.error(f"[URL Agent] Vision Analysis Error: {e}")
        return {
            "is_spam": None,
            "reason": f"Vision Analysis Error: {e}",
            "analysis_type": "vision_error"
        }

def convert_korean_domain_to_punycode(url: str) -> str:
    """
    한글 도메인을 Punycode로 변환
    예: http://두산위브트레지움월산.vvc.kr -> http://xn--...vvc.kr
    """
    try:
        # URL 파싱
        if not url.startswith("http"):
            url = "http://" + url
        
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        
        # 한글이 포함된 경우 Punycode로 변환
        if any('\uac00' <= char <= '\ud7a3' or '\u3131' <= char <= '\u3163' for char in domain):
            # 도메인 부분만 Punycode로 변환
            parts = domain.split('.')
            encoded_parts = []
            for part in parts:
                try:
                    # 한글이 포함된 부분만 인코딩
                    if any('\uac00' <= char <= '\ud7a3' or '\u3131' <= char <= '\u3163' for char in part):
                        encoded_parts.append(idna.encode(part).decode('ascii'))
                    else:
                        encoded_parts.append(part)
                except:
                    encoded_parts.append(part)
            
            encoded_domain = '.'.join(encoded_parts)
            
            # URL 재구성
            if parsed.scheme:
                result = f"{parsed.scheme}://{encoded_domain}"
            else:
                result = f"http://{encoded_domain}"
            
            if parsed.path and parsed.path != '/':
                # 한글 경로도 URL 인코딩
                encoded_path = quote(parsed.path, safe='/')
                result += encoded_path
            if parsed.query:
                result += f"?{parsed.query}"
            
            logger.info(f"[URL Agent] Converted Korean domain: {url} -> {result}")
            return result
        
        return url
    except Exception as e:
        logger.warning(f"[URL Agent] Punycode conversion failed for {url}: {e}")
        return url


# 주요 TLD 리스트 (False Positive 방지용)
# 프로토콜(http/https)이 없을 때, 이 TLD로 끝나는 경우만 URL로 인정
# (오징어.오뎅탕 등 방지)
COMMON_TLDS = {
    'com', 'net', 'org', 'edu', 'gov', 'mil', 'int', 'kr', 'co.kr', 'or.kr', 'pe.kr', 'go.kr', 'ac.kr',
    'io', 'ai', 'me', 'info', 'biz', 'shop', 'site', 'top', 'xyz', 'club', 'online', 'pro',
    'id', 'vn', 'jp', 'cn', 'us', 'uk', 'de', 'fr', 'tv', 'cc', 'li', 'ly', 'be', 'it', 'to', 'gg',
    'ws', 'mobi', 'asia', 'name', 'store', 'news', 'app', 'dev', 'tech', 'so'
}

async def extract_node(state: SpamState) -> Dict[str, Any]:
    """
    SMS 본문에서 URL 추출 (한글 도메인 지원)
    난독화된 텍스트가 있으면 디코딩된 텍스트에서 URL 추출
    pre_parsed_urls가 있으면 (KISA TXT 배치) 본문 추출 대신 파싱된 URL 사용
    """
    # [Batch KISA TXT] 파일에서 파싱한 URL이 있으면 본문 추출 스킵
    # pre_parsed_only_mode: KISA TXT면 URL 없을 때 본문 추출도 스킵 (난독화 오추출 방지)
    pre_parsed = state.get("pre_parsed_urls") or []
    pre_parsed_only_mode = state.get("pre_parsed_only_mode", False)
    if pre_parsed_only_mode and not pre_parsed:
        # KISA TXT + URL 없음 → 본문 추출 안 함
        logger.info("[URL Agent] Pre-parsed only mode: no URL in file, skip extraction")
        return {
            "target_urls": [],
            "current_url": None,
            "visited_history": [],
            "scraped_data": {},
            "depth": 0,
            "is_final": True,
            "is_spam": False,
            "reason": "No URL in file (pre-parsed only mode)"
        }
    if pre_parsed:
        unique_urls = []
        seen = set()
        for raw_url in pre_parsed:
            if not raw_url or len(raw_url) < 4:
                continue
            url = raw_url.strip().rstrip('.,;!?)]}"\'')
            if not url.startswith(("http://", "https://")):
                url = "http://" + url
            if len(url) < 10:
                continue
            converted = convert_korean_domain_to_punycode(url)
            if converted not in seen:
                seen.add(converted)
                unique_urls.append(converted)
        max_urls = int(os.getenv("MAX_URLS_PER_MESSAGE", "3"))
        if len(unique_urls) > max_urls:
            unique_urls = unique_urls[:max_urls]
            logger.info(f"[URL Agent] Pre-parsed URLs limited to {max_urls}")
        logger.info(f"[URL Agent] Using pre-parsed URLs (skip extract): {unique_urls}")
        return {
            "target_urls": unique_urls,
            "current_url": unique_urls[0] if unique_urls else None,
            "visited_history": [],
            "scraped_data": {},
            "depth": 0,
            "is_final": False if unique_urls else True,
            "is_spam": False if not unique_urls else None,
            "reason": "No URL found" if not unique_urls else "Pre-parsed URL used"
        }
    
    # 난독화 디코딩된 텍스트가 있으면 우선 사용
    message = state.get("decoded_text") or state.get("sms_content", "")
    
    # 1. 프로토콜이 있는 URL 추출 (가장 확실, 한글 포함 가능)
    # http://오징어.오뎅탕 -> 허용
    protocol_pattern = r'(?:http|https)://[^\s\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]+'
    protocol_urls = re.findall(protocol_pattern, message)
    
    # 2. 프로토콜이 없는 도메인 패턴 추출 (엄격한 검증 필요)
    # 한글.한글 -> 오징어.오뎅탕 (제외되어야 함)
    # google.com -> 허용
    # 정규식: (문자열.문자열) 형태, 경로(/anicsn016a) 등 포함
    domain_pattern = r'(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]{2,}(?:/[^\s\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]*)?'
    raw_candidates = re.findall(domain_pattern, message)
    
    # 정규화(NFKC)된 텍스트에서도 추출
    try:
        normalized_message = unicodedata.normalize('NFKC', message)
        if normalized_message != message:
            protocol_urls.extend(re.findall(protocol_pattern, normalized_message))
            raw_candidates.extend(re.findall(domain_pattern, normalized_message))
    except Exception as e:
        logger.warning(f"[URL Agent] Normalization failed: {e}")
        
    # 공백이 모두 제거된 텍스트에서도 추출 (고의적인 띄어쓰기 난독화 방어, 예: b i t . l y / 1 2 3)
    try:
        spaceless_message = re.sub(r'\s+', '', message)
        if spaceless_message != message:
            sp_protocol_pattern = r'(?:http|https)://[^\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]+'
            sp_domain_pattern = r'(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]{2,}(?:/[^\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]*)?'
            
            sp_protocol_urls = re.findall(sp_protocol_pattern, spaceless_message)
            sp_raw_cands = re.findall(sp_domain_pattern, spaceless_message)
            
            # 필터링: 정상적으로 띄어쓰기가 반영되어 추출된 URL에, 앞뒤로 엉뚱한 단어가 스페이스가 없어져서 들러붙은 가짜(Superset) URL 방어
            for sp_u in sp_protocol_urls:
                if not any(u in sp_u for u in protocol_urls):
                    protocol_urls.append(sp_u)
                    
            for sp_c in sp_raw_cands:
                if not any(c in sp_c for c in raw_candidates):
                    raw_candidates.append(sp_c)
    except Exception as e:
        logger.warning(f"[URL Agent] Spaceless extraction failed: {e}")
    
    urls = []
    
    # 2-1. 프로토콜 URL 처리
    for url in protocol_urls:
         # 뒤에 붙은 구두점 제거
        url = url.rstrip('.,;!?)]}"\'')
        if len(url) > 7: # http://...
            urls.append(url)
            
    # 2-2. 도메인 후보 검증
    for cand in raw_candidates:
        cand = cand.rstrip('.,;!?)]}"\'')
        if not cand: continue
        
        # 이미 프로토콜 URL에 포함된 경우 스킵
        if any(cand in u for u in urls):
            continue

        # TLD 확인
        try:
            # 도메인과 경로를 분리 (TLD 검사 목적)
            domain_part = cand.split('/')[0]
            parts = domain_part.split('.')
            
            # [Sentence Gluing Filter]
            # 문자열에서 띄어쓰기가 누락되어 한글 문장이 도메인 서브도메인으로 강제 병합된 경우 방어
            # 예: "전해드립니다.preed.com" -> SLD(preed)가 영문이면 앞의 한글 파트를 잘라냄
            if len(parts) >= 3:
                if re.match(r'^[a-zA-Z0-9-]+$', parts[-2]):
                    cut_idx = -1
                    for i in range(len(parts) - 2):
                        if re.search(r'[\uac00-\ud7a3\u3131-\u3163]', parts[i]):
                            cut_idx = i
                    if cut_idx >= 0:
                        new_domain_part = ".".join(parts[cut_idx+1:])
                        # 경로 등 뒤쪽 문자는 살려둔 채 앞부분만 교체
                        cand = new_domain_part + cand[len(domain_part):]
                        domain_part = new_domain_part
                        parts = domain_part.split('.')
            
            if len(parts) < 2: continue
            
            tld = parts[-1].lower()
            domain_name = parts[-2]
            
            # [Heuristic Filter] 프로토콜이 명시적이지 않은데 도메인 이름 부분이 숫자단독인 경우 
            # (예: 1.TV, 2.net 등) -> 번호 매기기 목록화 후 띄어쓰기 누락 오타일 확률이 매우 높으므로 배제
            if domain_name.isdigit():
                continue
            
            # 한글이 포함된 TLD인 경우 (.한국 등)
            is_korean_tld = any('\uac00' <= char <= '\ud7a3' or '\u3131' <= char <= '\u3163' for char in tld)
            
            if is_korean_tld:
                # [Policy] 프로토콜 없는 한글 TLD는 스킵 (오징어.오뎅탕 방지)
                # 만약 .한국 등 공식 TLD를 지원하려면 Whitelist가 필요하나, 
                # 현재는 스팸 오탐 방지를 위해 프로토콜 필수 정책 적용
                continue
            
            # 영문 TLD인 경우: Whitelist(COMMON_TLDS)에 있어야 허용
            # (chicken.beer 같은 유효하지만 드문 TLD는 프로토콜 없으면 놓칠 수 있으나, 안전을 위해 보수적 접근)
            if tld not in COMMON_TLDS:
                 # punycode TLD (xn--) 은 허용
                 if not tld.startswith('xn--'):
                     continue
            
            # 통과된 경우 http:// 붙여서 추가
            urls.append(f"http://{cand}")
            
        except Exception:
            continue
            
    # 2-4. Short URL 특수 처리 (Garbage 튜닝)
    # bit.ly/abcd미납금액결제 -> bit.ly/abcd 만 뽑히도록 쓰레기값 정리
    shorteners = ['bit.ly', 'me2.do', 'vo.la', 'han.gl', 'url.kr', 'sbz.kr', 'cutt.ly', 'tinyurl.com', 'naver.me', 'kko.to', 't.ly', 't.co', 'g.co']
    cleaned_urls = []
    for url in urls:
        if any(s in url.lower() for s in shorteners):
            # 숏주소 뒤에 특수기호가 붙으면 거기서부터 잘라냄 (단, 한글 가-힣은 정상 커스텀 URL일 수 있으므로 추출에선 자르지 않음!)
            url = re.sub(r'[\[\]\(\)<>◆▶★♥+\-:\.].*$', '', url)
            # 쓰레기값을 잘라냈는데 파라미터가 비어버린다면 가짜 URL (예: bit.ly/)이므로 통과
            if url.endswith('/') and url.split('/')[-2] in shorteners:
                logger.info(f"[URL Agent] Dropping empty short URL: {url}")
                continue
        cleaned_urls.append(url)
    urls = cleaned_urls
        
    # 중복 제거 및 Punycode 변환
    unique_urls = []
    seen = set()
    
    for url in urls:
        # 최소 길이 체크
        if len(url) < 10: # http://a.com
            continue
            
        # Punycode 변환
        converted = convert_korean_domain_to_punycode(url)
        
        if converted not in seen:
            seen.add(converted)
            unique_urls.append(converted)
    
    # 메시지당 URL 상한 (처리 시간 단축, 자원 고갈 방지)
    max_urls = int(os.getenv("MAX_URLS_PER_MESSAGE", "3"))
    if len(unique_urls) > max_urls:
        original_count = len(unique_urls)
        unique_urls = unique_urls[:max_urls]
        logger.info(f"[URL Agent] URLs limited to {max_urls} (was {original_count})")
            
    logger.info(f"[URL Agent] Extracted URLs: {unique_urls}")
    
    return {
        "target_urls": unique_urls,
        "current_url": unique_urls[0] if unique_urls else None,
        "visited_history": [],
        "scraped_data": {},
        "depth": 0,
        "is_final": False if unique_urls else True, 
        "is_spam": False if not unique_urls else None,
        "reason": "No URL found" if not unique_urls else "URL extracted"
    }

async def scrape_node(state: SpamState) -> Dict[str, Any]:
    """
    현재 URL 스크래핑 (Playwright)
    """
    url = state.get("current_url")
    logger.info(f"[URL Agent] Scraping URL: {url}")
    if not url:
        return {"reason": "No URL to scrape"}
    
    # Playwright Manager 사용
    try:
        # [Infrastructure] Prefer local manager from state to avoid global loop conflicts
        manager = state.get("playwright_manager")
        if not manager:
            manager = get_playwright_manager()
            
        result = await manager.scrape_url(url)
        if not result:
            result = {"status": "failed", "error": "No result returned", "url": url}
            
        # [Fallback on 404/Error API - Trailing Garbage]
        try:
            status = result.get("status")
            title = str(result.get("title", ""))
            
            # 404 에러나 Not Found인 경우, 뒤에 붙은 쓰레기 문자열이 원인일 수 있음
            if status == "failed" or "404" in title or "not found" in title.lower():
                
                # 1단계: 쓰레기값 잘라내기 (Trailing Garbage Stripping)
                # 대괄호, 괄호, 꺾쇠, 한글이 처음 등장하는 지점부터 그 뒤 문자열을 싹둑 자름
                cleaned_url = re.sub(r'[\[\]\(\)<>가-힣◆▶★♥]+.*$', '', url)
                
                # 방어 코드: 만약 다 잘라냈는데 남은 게 파라미터 없는 메인 도메인(http://bit.ly/) 뿐이라면 
                # 메인 페이지를 스크래핑해봤자 의미가 없으므로 재시도 중단!
                parsed_parts = cleaned_url.rstrip('/').split('/')
                if len(parsed_parts) > 3:
                    if cleaned_url != url and len(cleaned_url) > 8:
                        logger.warning(f"⚠️ [URL Agent] 404/Failed detected. Stripping trailing garbage and retrying: {url} -> {cleaned_url}")
                        retry_result = await manager.scrape_url(cleaned_url)
                        if retry_result and retry_result.get("status") == "success":
                            retry_title = str(retry_result.get("title", ""))
                            if "404" not in retry_title and "not found" not in retry_title.lower():
                                logger.info(f"✅ [URL Agent] Retry successful with cleaned URL!")
                                result = retry_result
                                url = cleaned_url # Update tracking URL
                                
                # 2단계: 띄어쓰기로 인해 끊긴 URL 복원 (Space-obfuscation Expansion)
                current_status = result.get("status")
                current_title = str(result.get("title", ""))
                # 아직도 404라면, 스페이스로 인해 끊겼을 가능성을 고려해 최대 3단어 확장 (사용자 요청)
                if current_status == "failed" or "404" in current_title or "not found" in current_title.lower():
                    sms_content = state.get("sms_content", "")
                    if url in sms_content:
                        parts = sms_content.split(url, 1)
                        if len(parts) == 2:
                            following_text = parts[1].strip()
                            if following_text:
                                tokens = following_text.split()
                                expanded_url = url
                                
                                for i in range(min(3, len(tokens))):
                                    expanded_url += tokens[i]
                                    
                                    # 확장된 문자열 뒤쪽의 스팸 기호나 정리
                                    check_url = re.sub(r'[\[\]\(\)<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]+.*$', '', expanded_url)
                                    
                                    if check_url != url and len(check_url) > 10:
                                        logger.warning(f"⚠️ [URL Agent] 404 detected. Expanding cut-off URL (+{i+1} word): {url} -> {check_url}")
                                        exp_result = await manager.scrape_url(check_url)
                                        exp_status = exp_result.get("status", "")
                                        exp_title = str(exp_result.get("title", ""))
                                        
                                        if exp_status == "success" and "404" not in exp_title and "not found" not in exp_title.lower():
                                            logger.info(f"✅ [URL Agent] Expansion successful!")
                                            result = exp_result
                                            url = check_url
                                            break
        except Exception as retry_e:
            logger.error(f"[URL Agent] Retry fallback error: {retry_e}")
        
        # 스크래핑 결과 로깅
        logger.info(f"[URL Agent] Scrape Result: status={result.get('status')}, "
                   f"final_url={result.get('url')}, "
                   f"title={result.get('title', '')[:50]}, "
                   f"captcha={result.get('captcha_detected')}, "
                   f"text_len={len(result.get('text', ''))}")
        
        # 텍스트 일부 로깅 (디버깅용)
        text_preview = result.get('text', '').strip()
        if "403" in text_preview[:100] and ("Forbidden" in text_preview[:100] or "denied" in text_preview[:100].lower()):
             logger.warning(f"⚠️ [URL Agent] Scraper Blocked (403 Forbidden)! Site may have bot protection.")
        
        display_preview = text_preview[:200].replace('\n', ' ')
        logger.info(f"[URL Agent] Content Preview: {display_preview}...")
        
    except Exception as e:
        logger.error(f"[URL Agent] Scrape Error: {e}")
        raise e
    
    # 방문 기록 추가
    original_url = state.get("current_url")
    history = state.get("visited_history", [])
    if original_url and original_url not in history:
        history.append(original_url)
        
    return {
        "scraped_data": result,
        "visited_history": history
    }

async def analyze_node(state: SpamState) -> Dict[str, Any]:
    """
    수집된 데이터를 기반으로 스팸 여부 판단 (LLM)
    1차: 텍스트 기반 분석
    2차: Inconclusive일 경우 Vision 분석 (스크린샷)
    """
    scraped = state.get("scraped_data", {})
    sms_content = state.get("sms_content", "")
    
    # 분석 시작 로그
    logger.info(f"URL 분석 시작 | msg={sms_content[:80]}{'...' if len(sms_content) > 80 else ''}")
    
    if scraped.get("status") != "success":
        # 스크래핑 실패 시 TLD 검사 등 폴백 로직 (간소화)
        logger.warning(f"스크래핑 실패: {scraped.get('error')}")
        return {
            "is_spam": None, 
            "reason": f"Scraping failed: {scraped.get('error')}"
        }

    # 프롬프트 구성
    raw_text = scraped.get("text", "")[:3000] # 길이 제한
    page_title = scraped.get("title", "")
    current_url = scraped.get("url", "")  # 리다이렉트 후 최종 URL
    screenshot_b64 = scraped.get("screenshot_b64", "")
    
    # 스크래핑 결과 로그
    logger.info(f"스크래핑 결과: URL={current_url} | Title={page_title[:50]} | Text길이={len(raw_text)}자")
    
    # 신뢰 도메인 체크 (Google, Naver, Play Store 등)
    if is_trusted_domain(current_url):
        logger.info(f"Trusted domain 검출 | URL={current_url} → Auto HAM (Continuing to next URL)")
        return {
            "is_spam": False,
            "spam_probability": 0.0,
            "classification_code": None,
            "reason": f"리다이렉트 목적지가 신뢰할 수 있는 공식 도메인 ({current_url.split('/')[2]})",
            "is_final": False, # 다른 URL도 확인해야 하므로 계속 진행
            "analysis_type": "trusted_domain"
        }
    
    # Format code map for prompt (SPAM 코드만 사용, HAM 코드 제외)
    spam_codes_only = {k: v for k, v in SPAM_CODE_MAP.items() if not k.startswith("HAM")}
    code_list_str = "\n".join([f"    - '{k}': {v}" for k, v in spam_codes_only.items()])

    is_captcha = scraped.get("captcha_detected", False)
    
    # Content Agent 분석 결과 가져오기 (연관성 확보)
    content_context = state.get("content_context", {})
    sms_content = state.get("sms_content", "")
    content_context_str = ""
    if content_context:
        content_label = "HAM" if not content_context.get("is_spam") else "SPAM"
        content_reason = content_context.get("reason", "")
        content_context_str = f"""
    [SMS 메시지 원문]
    {sms_content}
    
    [Content Agent의 SMS 분석 결과]
    - 판정: {content_label}
    - 근거: {content_reason}
    
    **당신의 임무**: SMS 메시지와 URL 페이지 내용을 **비교 분석(Crosscheck)**하여 **문맥 일치(Consistency)** 여부와 **스팸 의도**를 판단하세요.
    
    **핵심 판단 기준**: 
    1. SMS가 주장하는 내용(예: 대출, 배송, 상품)과 URL 페이지 내용이 **일치**하는가?
    2. URL 페이지가 SMS 내용을 숨기기 위한 **회피용(Evasion)** 페이지(단축기, 봇 체크 등)인가?
    """
    
    prompt = f"""
    당신은 SMS 메시지와 웹페이지 콘텐츠를 비교 분석하여 스팸 여부를 판단하는 전문가입니다.

    [입력 데이터]
    {content_context_str}
    - 페이지 제목: {page_title}
    - 봇 감지 여부: {is_captcha}
    - 웹 페이지 콘텐츠 (증거):
    {raw_text}
    
    [임무]
    웹 페이지(증거)가 SMS 내용(주장)과 일치하는지 검증하여 최종 판단을 내리세요.
    
    [핵심 판단 기준]
    1. **문맥 일치 (Consistency) - 최우선 기준**:
       - URL이 연결된 사이트의 성격(예: 성인, 쇼핑, 금융 등)이 무엇이든, SMS 메시지에서 안내하는 특정 목적(배송 조회, 결제 내역 확인, 본인 인증 등)을 **실제로 수행할 수 있는 합당한 페이지**라면 **HAM(정상)**으로 판단하세요.
       - 사이트의 일반적인 평판이나 카테고리보다, **"SMS가 주장하는 트랜잭션이 해당 페이지에서 실제로 일어날 수 있는가?"**를 기준으로 삼으세요.

    2. **Content Agent 가설 검증**:
       - Content Agent가 텍스트만으로 판단한 결과("스미싱 의심" 등)에 얽매이지 마세요. URL 페이지가 **실제 서비스의 정상적인 기능(예: 구체적인 청구 내역 표시, 공식적인 서비스 UI)**을 제공하고 있다면, 텍스트 기반의 의심을 기각(Override)하고 **HAM**으로 확정하세요.

    3. **목적 불일치 시의 판단 (Handling Mismatch)**:
       - SMS 내용과 URL 페이지 내용이 무관할 때, **무조건 SPAM으로 처리하지 마세요.**
       - **핵심 질문**: "이 불일치하는 페이지가 수신자에게 해를 끼치는(도박, 성인, 사기, 개인정보 탈취 등) 유해한 의도를 가진 페이지인가?"
       - **유해한 의도가 명확할 때만 SPAM**으로 분류하고 적절한 코드를 부여하세요.
       - 만약 페이지가 단순히 범용 서비스 안내, 서비스 준비 중, 혹은 기타 해롭지 않은 내용이라면 **판단 보류(30)** 혹은 **Content Agent의 결과(HAM)**를 유지하세요.
       
    [오판 방지 가이드 (Bias Correction)]
    - **성급한 일반화 금지**: "성인 사이트", "관리비 미납 안내"라는 키워드만으로 무조건 SPAM이라고 단정하지 마세요. 반드시 **"SMS가 안내한 목적(배송, 고지서 확인)을 수행하는가?"**를 확인해야 합니다.
    - **도메인 편향 제거**: URL 도메인이 낯선 단축 URL(bit.ly 등)이나 생소한 도메인이라도, 최종 착지 페이지가 정상적인 기능을 제공하면 HAM입니다.

    [피싱 (Phishing)]
    - 정부 기관, 금융사를 사칭하여 개인정보 입력을 유도하는 가짜 사이트는 무조건 **SPAM**입니다.

    Classification Codes (use only if SPAM):
{code_list_str}
    
    Response (JSON):
    {{
        "is_spam": boolean,
        "classification_code": "string or null if HAM",
        "spam_probability": float (0.0-1.0),
        "reason": "한글 서술 (판단 근거 상세히 기재. 특히 SMS와 URL의 관계를 중심으로 서술)"
    }}
    """
    
    try:
        # ========== 1차: 텍스트 기반 분석 ==========
        # logger.info(f"[URL Agent] Text Analysis Prompt:\n{prompt[:2000]}...")  # 프롬프트 로그 출력 제거
        preview_text = raw_text[:100].strip()
        if "403" in preview_text and ("Forbidden" in preview_text or "denied" in preview_text.lower()):
            logger.warning(f"⚠️ [URL Agent] Scraper Blocked (403 Forbidden)! Site may have bot protection. Falling back to content-only analysis where possible.")
        logger.info(f"[URL Agent] Scraped Content Preview (100 chars): {preview_text}...")
        llm = get_llm()
        
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception(lambda e: "No retry." not in str(e)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        async def call_llm():
            provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
            if key_manager.is_quota_exhausted(provider):
                raise Exception(f"{provider} quota globally exhausted. No retry.")
                
            api_key = key_manager.get_key(provider) # 실패 시 대조를 위해 키 보관
            llm = get_llm() # Get fresh LLM (uses the same key)
            try:
                # [Phase 1] 45s Timeout added to prevent hangs
                response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=45.0)
                key_manager.report_success(provider)
                return response
            except asyncio.TimeoutError as e:
                logger.warning(f"[URL Agent] {provider} LLM Timeout occurred (45s). Attempting Fallback to Sub Model.")
                raw_sub_model = os.getenv("LLM_SUB_MODEL", "gemini-3.1-flash-lite-preview")
                sub_model = raw_sub_model.strip().strip("'").strip('"') if raw_sub_model else "gemini-3.1-flash-lite-preview"
                if not sub_model:
                    sub_model = "gemini-3.1-flash-lite-preview"
                
                fallback_key = key_manager.get_key("GEMINI")
                if fallback_key:
                    # _get_cached_client is not directly exposed here, we need ChatGoogleGenerativeAI
                    try:
                        from langchain_google_genai import ChatGoogleGenerativeAI
                        fallback_llm = ChatGoogleGenerativeAI(
                            model=sub_model,
                            google_api_key=fallback_key,
                            temperature=0,
                            convert_system_message_to_human=True,
                            max_retries=0
                        )
                        response = await asyncio.wait_for(fallback_llm.ainvoke(prompt), timeout=45.0)
                        if hasattr(response, 'content') and isinstance(response.content, str):
                            response.content = f"__FALLBACK_{sub_model}__\n" + response.content
                        return response
                    except Exception as fallback_e:
                        logger.error(f"[URL Agent Fallback] Sub model failed: {fallback_e}")
                        raise Exception("Async LLM Timeout (Fallback failed)") from e
                else:
                    raise Exception("Async LLM Timeout (No fallback key)") from e
            except Exception as e:
                error_msg = str(e).lower()
                
                # [Fix] Explicit type check for Google API errors (Gemini)
                is_google_quota_error = False
                if provider == "GEMINI":
                    try:
                        import google.api_core.exceptions
                        if isinstance(e, (google.api_core.exceptions.ResourceExhausted, google.api_core.exceptions.TooManyRequests)):
                            is_google_quota_error = True
                    except ImportError:
                        pass

                if is_google_quota_error or "quota" in error_msg or "429" in error_msg or "rate" in error_msg or "limit" in error_msg or "resource exhausted" in error_msg:
                    logger.warning(f"[URL Agent] {provider} Quota Detected. Error: {error_msg}")
                    logger.warning(f"[URL Agent] {provider} Quota Exceeded. Rotating key...")
                    # [동시성 개선] 실패한 키 전달 및 글로벌 소진 감지
                    is_rotated = key_manager.rotate_key(provider, failed_key=api_key)
                    
                    if not is_rotated:
                            logger.error(f"[URL Agent] URL Text Analysis Global exhaustion reached for {provider}.")
                            raise Exception(f"{provider} text quota globally exhausted. No retry.") from e
                    
                    # 쿨다운 대기 없이 즉시 재시도/포기 진행
                    pass
                raise e
            
        response = await call_llm()
        content = response.content
        
        fallback_model = None
        if isinstance(content, str) and content.startswith("__FALLBACK_"):
            parts = content.split("__\n", 1)
            if len(parts) == 2:
                fallback_info = parts[0].replace("__FALLBACK_", "")
                fallback_model = fallback_info
                content = parts[1]
        
        # Handle structured content (List of dicts) if LLM returns it
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            content = "".join(text_parts)
        
        # JSON 파싱
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        result_json = json.loads(content.strip())
        
        is_spam = result_json.get("is_spam")
        prob = result_json.get("spam_probability", 0.0)
        reason = result_json.get("reason", "")
        if fallback_model and reason:
            result_json["reason"] = f"[URL_Fallback: {fallback_model}] " + reason
            reason = result_json["reason"]
        classification_code = result_json.get("classification_code")
        
        # URL Agent 1차 분석 결과 로깅
        verdict = "SPAM" if is_spam else ("INCONCLUSIVE" if is_spam is None else "HAM")
        logger.info(f"LLM 분석결과 | {verdict} | code={classification_code} | prob={prob}")
        logger.debug(f"Reason: {reason[:150]}{'...' if len(reason) > 150 else ''}")
        
        # ========== 2차: Inconclusive 체크 → Vision 분석 ==========
        reason_lower = reason.lower()
        is_inconclusive = "inconclusive" in reason_lower
        
        if is_inconclusive and screenshot_b64:
            logger.info("Text분석 Inconclusive → Vision 분석 시도")
            
            # Vision 분석 호출
            vision_result = await analyze_with_vision(screenshot_b64, current_url, page_title, content_context)
            
            # Vision 분석 성공 시 결과 사용
            if vision_result.get("analysis_type") == "vision" and vision_result.get("is_spam") is not None:
                logger.info("Vision 분석 완료 → Vision 결과 사용")
                is_spam = vision_result.get("is_spam")
                
                return {
                    "is_spam": is_spam,
                    "spam_probability": vision_result.get("spam_probability", 0.0),
                    "classification_code": vision_result.get("classification_code"),
                    "reason": vision_result.get("reason"),
                    "is_final": True if is_spam else False, # SPAM이면 즉시 종료, 아니면 다음 URL
                    "analysis_type": "vision"
                }
            else:
                # Vision도 실패하면 원래 Inconclusive 결과 유지
                logger.warning("Vision 분석 실패/불확실 → Text 결과 유지")
                reason = f"{reason} | [Vision 분석 시도했으나 판단 불가]"
        
        # 1차 분석 결과 반환 (확정 판단 또는 Vision 실패 시)
        # SPAM이면 즉시 종료 (is_final=True)
        # HAM/Inconclusive면 다음 URL 확인 (is_final=False)
        return {
            "is_spam": is_spam,
            "spam_probability": prob,
            "classification_code": classification_code,
            "reason": reason,
            "is_final": True if is_spam else False,
            "analysis_type": "text"
        }
        
    except Exception as e:
        error_msg = str(e).lower()
        if "quota exhausted" in error_msg or "429" in error_msg:
            # Re-raise quota errors to let the higher layer handle it (e.g. process_message fallback)
            logger.error(f"[URL Agent] Fatal Quota Error: {e}")
            raise e
            
        logger.exception("URL 분석 중 오류 발생")
        return {"reason": f"Analysis Error: {e}", "is_final": False}

async def select_link_node(state: SpamState) -> Dict[str, Any]:
    """
    모든 URL을 순회하며 확인하기 위한 로직
    """
    target_urls = state.get("target_urls", [])
    visited = state.get("visited_history", [])
    depth = state.get("depth", 0)
    
    # 무한 루프 방지 장치 (안전망)
    if depth >= 3:
        logger.error("[URL Agent] Max depth (3) reached! Potential infinite loop aborted.")
        return {
            "is_final": True,
            "reason": "Max depth reached (Loop aborted)"
        }
    
    # 1. 아직 방문하지 않은 URL 찾기
    next_url = None
    for url in target_urls:
        if url not in visited:
            next_url = url
            break
            
    if next_url:
        logger.info(f"[URL Agent] Next URL selected: {next_url}")
        return {
            "current_url": next_url,
            "depth": depth + 1,
            "is_final": False # 계속 진행
        }
    else:
        # 2. 모든 URL 방문 완료
        logger.info("[URL Agent] All URLs visited. No SPAM found.")
        return {
            "is_final": True,
            "reason": "All URLs scanned (No SPAM detected)"
        }
