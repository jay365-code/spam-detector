from app.agents.url_agent.nodes import extract_node
import asyncio

async def test_extraction():
    # 1. 오탐(1.TV) 문자열 테스트
    state1 = {
        "message_id": "test_1",
        "sms_content": "(광고)[LG전자 베스트샵](광고)아산본점 새단장 오픈 세일! 1.TV 제품 정상가 대비 최대 50% SALE! 2.냉장고 제품 정상가 30% SALE! 114.kr 도메인 없음",
        "chat_mode": "Unified"
    }
    
    # 2. 정상 URL 문자열 테스트
    state2 = {
        "message_id": "test_2",
        "sms_content": "진짜 인터넷 주소입니다. http://1.tv 또는 1.tv 접속하세요. 그리고 naver.com 도 있습니다.",
        "chat_mode": "Unified"
    }

    print("--- Test 1 (오타 검출 방지) ---")
    result1 = await extract_node(state1)
    print(f"Extracted URLs: {result1['target_urls']}")
    
    print("\n--- Test 2 (정상 URL 추출) ---")
    result2 = await extract_node(state2)
    print(f"Extracted URLs: {result2['target_urls']}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
