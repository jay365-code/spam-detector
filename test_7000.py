import asyncio
import os
import sys

# Set expected environment variables
os.environ["LLM_PROVIDER"] = "OPENAI"
os.environ["LLM_MODEL"] = "gpt-4o-mini"
os.environ["OPENAI_API_KEY"] = "dummy"

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from app.agents.url_agent.nodes import extract_node

async def main():
    msg = "안녕하세요 형님 항상 복 많이받으시고 아래 내용 참고하시어 잠시만 시간 내어주신다면 정말 감사 하겠습니다 → 태 ㅅr 자 는 7.0.0.0 명의 선생님들을 케.어 하고있는 메 E 저 입니다 이렇게 오.랜.기.간 함께할수 있었던 이유는 고객님들에게 석 나가는 행동은 절대로 하지 않으며 ♥ 보물 ♥ https://tvb.bz/1Q ♥ 지도 ♥ 805"
    
    # 1. pre_parsed_url is passed as ["7.0.0.0"]
    print("Test 1: pre_parsed = 7.0.0.0")
    state1 = {
        "sms_content": msg,
        "pre_parsed_urls": ["7.0.0.0"],
        "pre_parsed_only_mode": True,
        "content_context": {}
    }
    res1 = await extract_node(state1)
    print("Result 1:", res1.get("target_urls"))
    
    # 2. pre_parsed_url is empty, but URL is in text
    print("\nTest 2: pre_parsed is empty")
    state2 = {
        "sms_content": msg,
        "pre_parsed_urls": [],
        "pre_parsed_only_mode": False,
        "content_context": {}
    }
    res2 = await extract_node(state2)
    print("Result 2:", res2.get("target_urls"))

    # 3. pre_parsed is ["7.0.0.0"] and pre_parsed_only_mode = False
    print("\nTest 3: pre_parsed = 7.0.0.0, mode=False")
    state3 = {
        "sms_content": msg,
        "pre_parsed_urls": ["7.0.0.0"],
        "pre_parsed_only_mode": False,
        "content_context": {}
    }
    res3 = await extract_node(state3)
    print("Result 3:", res3.get("target_urls"))

if __name__ == "__main__":
    asyncio.run(main())
