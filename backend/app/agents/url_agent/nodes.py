import re
import unicodedata
import os
import json
import asyncio
import logging
from app.core.logging_config import get_logger
logger = get_logger(__name__)
import base64
from typing import Dict, Any, List
from urllib.parse import urlparse, quote
import idna  # Punycode 변환용

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

def get_llm():
    """
    .env 설정에 따른 LLM 인스턴스 반환
    """
    # Lazy imports for LLM providers
    from langchain_core.prompts import PromptTemplate
    
    provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    if provider == "GEMINI":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0, convert_system_message_to_human=True)
    elif provider == "CLAUDE":
        from langchain_anthropic import ChatAnthropic
        api_key = os.getenv("CLAUDE_API_KEY")
        return ChatAnthropic(model=model_name, anthropic_api_key=api_key, temperature=0)
    else:
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        return ChatOpenAI(model=model_name, api_key=api_key, temperature=0.1)


async def analyze_with_vision(screenshot_b64: str, url: str, title: str) -> Dict[str, Any]:
    """
    Gemini Vision API를 사용하여 스크린샷 기반 스팸 분석
    텍스트 분석이 Inconclusive일 때 호출됨
    """
    logger.info(f"[URL Agent] Starting Vision analysis for: {url}")
    
    try:
        # Lazy import gemini
        import google.generativeai as genai
        
        # Gemini API 설정
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        
        genai.configure(api_key=api_key)
        
        # 모델 선택 (환경변수에서 가져오거나 기본값 사용)
        model_name = os.getenv("LLM_MODEL", "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)
        
        # Base64 이미지를 바이트로 변환
        image_bytes = base64.b64decode(screenshot_b64)
        
        # 이미지 데이터 구성
        image_part = {
            "mime_type": "image/jpeg",
            "data": image_bytes
        }
        
        # Format code map for prompt (SPAM 코드만 사용, HAM 코드 제외)
        spam_codes_only = {k: v for k, v in SPAM_CODE_MAP.items() if not k.startswith("HAM")}
        code_list_str = "\n".join([f"    - '{k}': {v}" for k, v in spam_codes_only.items()])
        
        # Vision 프롬프트
        prompt = f"""
        You are a spam detection expert. Analyze this webpage screenshot and determine if it has **malicious/spam intent**.
        
        Page Title: {title}
        
        **Your task: Determine if this page has SPAM INTENT based on VISUAL CONTENT ONLY**
        
        SPAM INTENT (requires CLEAR visual evidence):
        - Illegal gambling (도박, 카지노, 토토, 바카라, 슬롯 - flashy casino imagery, betting interfaces, chips/cards)
        - Adult/prostitution (성인, 유흥 - provocative images, adult service ads)
        - Phishing (피싱 - fake login pages mimicking known brands, urgent security warnings asking credentials)
        - Illegal finance (불법 대출 - unlicensed loan offers, 급전, 무서류)
        - Fraud/Scam (사기 - fake prizes, too-good-to-be-true offers)
        
        NOT SPAM (legitimate purposes):
        - Delivery/shipping tracking pages (배송 조회, 배송 추적, 배송 완료)
        - Normal business marketing/advertising
        - E-commerce, product/service pages, order confirmations
        - Real estate/apartment promotional pages
        - Corporate websites, landing pages
        - News, information sites
        
        **CRITICAL RULES:**
        1. Judge ONLY by what you SEE in the screenshot, not by domain name or URL.
        2. Unknown or unusual domain names are NOT evidence of spam.
        3. Delivery tracking pages showing shipping timeline/status are LEGITIMATE.
        4. Real estate marketing pages with apartment info are LEGITIMATE advertising.
        5. If the page shows normal business content (배송, 주문, 분양, 상품 등), it is NOT spam.
        6. Only mark as SPAM if you see CLEAR malicious visual content.
        7. **CRITICAL - Inconclusive Conditions (include "Inconclusive" in reason if ANY of these apply):**
           - You cannot see meaningful content (blocked, loading, error page, etc.)
           - Page only shows redirect/link UI to external apps (KakaoTalk, Telegram, etc.) without actual service content
           - Page only shows "click to proceed" buttons without revealing what the destination offers
           - You CANNOT determine the TRUE INTENT of the final service from this screenshot alone
           - The page is just a landing/bridge page without actual service details
           
        **IMPORTANT**: If the screenshot does not clearly reveal the PURPOSE/INTENT of the service, mark it as Inconclusive - do NOT assume HAM just because no malicious content is visible.

        Classification Codes (use only if SPAM):
{code_list_str}
        
        Response (JSON):
        {{
            "is_spam": boolean,
            "classification_code": "string or null if HAM",
            "spam_probability": float (0.0-1.0),
            "reason": "Korean explanation based on visual content analysis"
        }}
        """
        
        # Generation config
        generation_config = genai.GenerationConfig(
            temperature=0,
            response_mime_type="application/json"
        )
        
        # Vision API 호출
        response = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: model.generate_content(
                [prompt, image_part],
                generation_config=generation_config
            )
        )
        
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
        
        logger.info(f"[URL Agent] Vision Analysis Result: is_spam={is_spam}, "
                   f"probability={prob}, code={classification_code}, "
                   f"reason={reason}")
        
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


async def extract_node(state: SpamState) -> Dict[str, Any]:
    """
    SMS 본문에서 URL 추출 (한글 도메인 지원)
    난독화된 텍스트가 있으면 디코딩된 텍스트에서 URL 추출
    """
    # 난독화 디코딩된 텍스트가 있으면 우선 사용
    message = state.get("decoded_text") or state.get("sms_content", "")
    
    # 한글 도메인을 포함한 URL 패턴
    # 한글 유니코드 범위: \uac00-\ud7a3 (가-힣), \u3131-\u3163 (ㄱ-ㅣ)
    url_pattern = r'(?:http[s]?://)?(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z가-힣]{2,}(?:/[^\s]*)?'
    
    # 1. 원본 텍스트에서 추출
    found_urls = re.findall(url_pattern, message)
    
    # 2. 정규화(NFKC)된 텍스트에서 추출 (난독화 대응)
    # 예: "dⓢlp①③7⑤.cc" -> "dslp1375.cc"
    try:
        normalized_message = unicodedata.normalize('NFKC', message)
        if normalized_message != message:
            logger.info(f"[URL Agent] Normalized text: {normalized_message}")
            found_urls_normalized = re.findall(url_pattern, normalized_message)
            found_urls.extend(found_urls_normalized)
    except Exception as e:
        logger.warning(f"[URL Agent] Normalization failed: {e}")
    
    urls = []
    for url in found_urls:
        # Filter out common false positives
        # 최소 도메인 길이 체크 (너무 짧은 것 제외)
        if len(url) < 4:
            continue
        
        # Prepend http:// if missing
        if not url.startswith("http"):
            url = "http://" + url
        
        # 한글 도메인을 Punycode로 변환
        url = convert_korean_domain_to_punycode(url)
        
        urls.append(url)
    
    # 중복 제거 (순서 유지)
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    urls = unique_urls
    
    logger.info(f"[URL Agent] Extracted URLs: {urls}")
    
    return {
        "target_urls": urls,
        "current_url": urls[0] if urls else None,
        "visited_history": [],
        "scraped_data": {},
        "depth": 0,
        "is_final": False if urls else True, # URL 없으면 종료
        "is_spam": False if not urls else None,
        "reason": "No URL found" if not urls else "URL extracted"
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
        manager = get_playwright_manager()
        result = await manager.scrape_url(url)
        
        # 스크래핑 결과 로깅
        logger.info(f"[URL Agent] Scrape Result: status={result.get('status')}, "
                   f"final_url={result.get('url')}, "
                   f"title={result.get('title', '')[:50]}, "
                   f"captcha={result.get('captcha_detected')}, "
                   f"text_len={len(result.get('text', ''))}")
        
        # 텍스트 일부 로깅 (디버깅용)
        text_preview = result.get('text', '')[:200].replace('\n', ' ')
        logger.info(f"[URL Agent] Content Preview: {text_preview}...")
        
    except Exception as e:
        logger.error(f"[URL Agent] Scrape Error: {e}")
        raise e
    
    # 방문 기록 추가
    history = state.get("visited_history", [])
    if url not in history:
        history.append(url)
        
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
        logger.info(f"Trusted domain 검출 | URL={current_url} → Auto HAM")
        return {
            "is_spam": False,
            "spam_probability": 0.0,
            "classification_code": None,
            "reason": f"리다이렉트 목적지가 신뢰할 수 있는 공식 도메인 ({current_url.split('/')[2]}) - 자동 HAM 처리",
            "is_final": True,
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
    
    **당신의 임무**: SMS 메시지와 URL 페이지 내용을 **종합적으로 연결**하여 스팸 의도를 판단하세요.
    
    핵심 질문: SMS가 URL을 통해 **유해한 목적(도박/피싱/사기 등)**으로 유도하려는 의도가 있는가?
    
    **SPAM 판단 기준**: URL이 도박/피싱/사기 등 **유해 목적**으로 유도하는 경우
    **HAM 판단 기준**: URL이 SMS 내용과 연관된 정상 비즈니스인 경우 (성인용품 포함)
    """
    
    prompt = f"""
    You are a spam detection expert. Analyze this webpage and determine if it has **malicious/spam intent**.
    {content_context_str}
    Title: {page_title}
    Captcha/Security Check Detected: {is_captcha}
    Content:
    {raw_text}
    
    **Your task: Determine if this page has SPAM INTENT based on CONTENT ONLY**
    
    SPAM INTENT (requires CLEAR evidence in content):
    - Illegal gambling (도박, 카지노, 토토, 바카라, 슬롯 - actual gambling content/interface)
    - Adult/prostitution services (성인, 유흥, 출장, 안마, 오피 - explicit adult content)
    - Phishing (가짜 로그인, 브랜드 사칭 - fake forms asking for passwords/credentials)
    - Illegal finance (불법 대출, 급전, 무서류 대출 - unlicensed loan offers)
    - Fraud/Scam (사기, 가짜 이벤트, 허위 당첨 - clear deception)
    
    NOT SPAM (legitimate purposes):
    - Delivery/shipping tracking pages (배송 조회, 배송 추적)
    - Normal business marketing/advertising
    - E-commerce, product sales, order confirmations
    - Service notifications, transaction alerts
    - News, blogs, information sites
    
    **CRITICAL RULES:**
    1. Judge ONLY by the actual PAGE CONTENT, not by domain name or URL format.
    2. Unknown or unusual domain names are NOT evidence of spam - focus on what the page SHOWS.
    3. Delivery tracking pages showing shipping status are legitimate even if domain seems unfamiliar.
    4. If content shows normal business activity (배송, 주문, 결제 등), it is NOT spam.
    5. Only mark as SPAM if you see CLEAR malicious content (gambling UI, adult content, fake login, etc.)
    6. **CRITICAL - Inconclusive Conditions (include "Inconclusive" in reason if ANY of these apply):**
       - Content is too short/empty or blocked by captcha
       - Page only redirects to external apps/messengers (KakaoTalk, Telegram, Line, etc.) without showing actual service content
       - Page only shows "click to proceed" or link buttons without revealing what the destination offers
       - You CANNOT determine the TRUE INTENT of the final service from this page's content alone
       - The page is just a landing/bridge page that doesn't show the actual service details
       
    **IMPORTANT**: If the page content does not clearly reveal the PURPOSE/INTENT of the service, you MUST mark it as Inconclusive - do NOT assume HAM just because no malicious content is visible.

    Classification Codes (use only if SPAM):
{code_list_str}
    
    Response (JSON):
    {{
        "is_spam": boolean,
        "classification_code": "string or null if HAM",
        "spam_probability": float (0.0-1.0),
        "reason": "Korean explanation. Include 'Inconclusive' if content insufficient."
    }}
    """
    
    try:
        # ========== 1차: 텍스트 기반 분석 ==========
        # logger.info(f"[URL Agent] Text Analysis Prompt:\n{prompt[:2000]}...")  # 프롬프트 로그 출력 제거
        logger.info(f"[URL Agent] Scraped Content Preview (100 chars): {raw_text[:100]}...")
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        content = response.content
        
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
            vision_result = await analyze_with_vision(screenshot_b64, current_url, page_title)
            
            # Vision 분석 성공 시 결과 사용
            if vision_result.get("analysis_type") == "vision" and vision_result.get("is_spam") is not None:
                logger.info("Vision 분석 완료 → Vision 결과 사용")
                return {
                    "is_spam": vision_result.get("is_spam"),
                    "spam_probability": vision_result.get("spam_probability", 0.0),
                    "classification_code": vision_result.get("classification_code"),
                    "reason": vision_result.get("reason"),
                    "is_final": True,
                    "analysis_type": "vision"
                }
            else:
                # Vision도 실패하면 원래 Inconclusive 결과 유지
                logger.warning("Vision 분석 실패/불확실 → Text 결과 유지")
                reason = f"{reason} | [Vision 분석 시도했으나 판단 불가]"
        
        # 1차 분석 결과 반환 (확정 판단 또는 Vision 실패 시)
        return {
            "is_spam": is_spam,
            "spam_probability": prob,
            "classification_code": classification_code,
            "reason": reason,
            "is_final": True,
            "analysis_type": "text"
        }
        
    except Exception as e:
        logger.exception("URL 분석 중 오류 발생")
        return {"reason": f"Analysis Error: {e}"}

async def select_link_node(state: SpamState) -> Dict[str, Any]:
    """
    추가 탐색이 필요한 경우 다음 링크 선정
    """
    # 현재는 구현 간소화를 위해 재귀 탐색 없이 종료 처리
    # 추후 LLM이 'a' 태그 목록 중 의심스러운 링크 선택 로직 추가 가능
    return {
        "is_final": True,
        "reason": "Max depth reached or no suspicious links found"
    }
