import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.agents.url_agent.agent import isaa_agent_app

async def test_isaa(url_or_msg: str):
    print(f"\n[Test] Input: {url_or_msg}")
    
    # 메시지인지 URL인지 구분 (단순)
    if not url_or_msg.startswith("http"):
        msg = url_or_msg
        urls = [] # Extract node will handle
    else:
        msg = f"Check this url: {url_or_msg}"
        urls = []

    initial_state = {
        "sms_content": msg,
        "target_urls": urls,
        "visited_history": [],
        "scraped_data": {},
        "depth": 0,
        "max_depth": 1,
        "is_final": False
    }

    try:
        result = await isaa_agent_app.ainvoke(initial_state)
        
        print(f"  -> Is Spam: {result.get('is_spam')}")
        print(f"  -> Probability: {result.get('spam_probability')}")
        print(f"  -> Reason: {result.get('reason')}")
        print(f"  -> URLs Found: {result.get('target_urls')}")
        print(f"  -> Scraped Title: {result.get('scraped_data', {}).get('title', 'N/A')}")
        
    except Exception as e:
        print(f"  -> Error: {e}")

async def main():
    print("=== ISAA Standalone Verification ===")
    
    # 1. Normal Site
    await test_isaa("https://www.google.com")
    
    # 2. Suspicious URL (Simulated/Real check needed)
    # await test_isaa("http://example.com")
    
    # 3. Message with URL
    await test_isaa("무료 충전 이벤트! 지금 접속하세요: https://www.naver.com")

if __name__ == "__main__":
    asyncio.run(main())
