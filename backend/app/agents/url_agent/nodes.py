import re
import os
import json
import asyncio
from typing import Dict, Any, List

from .state import SpamState
from .tools import PlaywrightManager
from app.core.constants import SPAM_CODE_MAP

# LLM 관련 (기존 filter_rag.py 참조 또는 직접 호출)
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic

manager = PlaywrightManager()

def get_llm():
    """
    .env 설정에 따른 LLM 인스턴스 반환
    """
    provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    if provider == "GEMINI":
        api_key = os.getenv("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0, convert_system_message_to_human=True)
    elif provider == "CLAUDE":
        api_key = os.getenv("CLAUDE_API_KEY")
        return ChatAnthropic(model=model_name, anthropic_api_key=api_key, temperature=0)
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        return ChatOpenAI(model=model_name, api_key=api_key, temperature=0)

async def extract_node(state: SpamState) -> Dict[str, Any]:
    """
    SMS 본문에서 URL 추출
    """
    message = state.get("sms_content", "")
    
    # Updated URL Pattern: Supports http/https optional, and common domain structures
    # Matches: http://example.com, https://example.com, www.example.com, example.com/path
    url_pattern = r'(?:http[s]?://)?(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?'
    
    found_urls = re.findall(url_pattern, message)
    
    urls = []
    for url in found_urls:
        # Filter out common false positives if necessary (e.g., file extensions not acting as urls)
        # For now, just accept them.
        
        # Prepend http:// if missing
        if not url.startswith("http"):
            url = "http://" + url
        urls.append(url)
    
    # 중복 제거
    urls = list(set(urls))
    
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
    print(f"[Nodes] Entering scrape_node for URL: {url}")
    if not url:
        return {"reason": "No URL to scrape"}
    
    # Playwright Manager 사용
    print(f"[Nodes] Calling manager.scrape_url({url})...")
    try:
        result = await manager.scrape_url(url)
        print(f"[Nodes] manager.scrape_url returned. Status: {result.get('status')}")
    except Exception as e:
        print(f"[Nodes] manager.scrape_url raised Exception: {e}")
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
    """
    scraped = state.get("scraped_data", {})
    if scraped.get("status") != "success":
        # 스크래핑 실패 시 TLD 검사 등 폴백 로직 (간소화)
        return {
            "is_spam": None, 
            "reason": f"Scraping failed: {scraped.get('error')}"
        }

    # 프롬프트 구성
    raw_text = scraped.get("text", "")[:3000] # 길이 제한
    page_title = scraped.get("title", "")
    current_url = scraped.get("url", "")
    
    # Format code map for prompt
    code_list_str = "\n".join([f"    - '{k}': {v}" for k, v in SPAM_CODE_MAP.items()])

    is_captcha = scraped.get("captcha_detected", False)
    
    prompt = f"""
    Analyze the following webpage content to determine if it is SPAM (Phishing, Illegal Gambling, Smishing) or HAM (Legitimate).
    
    URL: {current_url}
    Title: {page_title}
    Captcha/Security Check Detected: {is_captcha}
    Content Snippet:
    {raw_text}
    
    Spam Criteria:
    - Asking for personal info (Social security, card numbers) implies Phishing.
    - Gambling keywords (Casino, Betting) implies Spam.
    - Illegal content.
    - **IMPORTANT**: If 'Captcha/Security Check Detected' is True AND the content is just a security page (e.g. "Just a moment", "antiphishing.biz", "Cloudflare"):
      - It is highly suspicious if it's hiding the final destination behind a short link.
      - **DO NOT** hallicinate that the page contains gambling or phishing unless you see it in the text.
      - If you cannot verify the destination, classify it as 'Suspicious' or 'Spam' (Code '1' or '9' depending on context, usually '1' for hiding intent).
      - Reason should be: "Blocked by Bot Check/Security Page (Destination Hidden)".

    Valid Classification Codes:
{code_list_str}
    
    Result Format (JSON):
    {{
        "is_spam": boolean,
        "classification_code": "string (Must be one of the Valid Classification Codes, e.g. '1', '9')",
        "spam_probability": float (0.0-1.0),
        "reason": "string (Korean)"
    }}
    """
    
    try:
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
        # (실제론 JsonOutputParser 사용 권장)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        result_json = json.loads(content.strip())
        
        is_spam = result_json.get("is_spam")
        prob = result_json.get("spam_probability", 0.0)
        
        # 판단 완료 조건: 확실한 스팸(>0.8)이거나 확실한 햄(<0.2)
        is_final = False
        if prob > 0.8 or prob < 0.2:
            is_final = True
            
        return {
            "is_spam": is_spam,
            "spam_probability": prob,
            "classification_code": result_json.get("classification_code"),
            "reason": result_json.get("reason"),
            "is_final": is_final
        }
        
    except Exception as e:
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
