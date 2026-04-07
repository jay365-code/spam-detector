import asyncio
import sys
import os

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
sys.path.append(os.path.join(project_root, "backend"))

# Load Env
from dotenv import load_dotenv
env_path = os.path.join(project_root, "backend", ".env")
load_dotenv(env_path)

from app.agents.ibse_agent.service import IBSEAgentService

async def main():
    service = IBSEAgentService()
    
    messages = [
        "<지우&은우님입장이실패했습니다.확인바랍니다https://입장하기.kr/xyq",
        "☆서보름님싸부입니다방이동되어안내드립니다!https://입장하기.kr/xyq",
        "♡님싸부입니다방이동되어안내드립니다!https://입장하기.kr/xyq",
        "010-7192-0님싸부입니다방이동되어안내드립니다!https://입장하기.kr/xyq",
        "0김성민0님입장이실패했습니다.확인바랍니다https://입장하기.kr/xyq"
    ]
    
    print("\n==================================")
    print("스팸 메시지 캐시 테스트 시작 (동일 캠페인)")
    print("==================================\n")

    for i, msg in enumerate(messages, 1):
        def cb(status):
            # 상태 콜백 프린트 생략하여 깔끔하게 표시
            pass
            
        print(f"[{i}번째 메시지 입력]")
        print(f" - 원문: {msg}")
        
        result = await service.process_message(msg, status_callback=cb)
        
        reason = result.get('reason')
        is_cached = "캐시 매칭으로 LLM 호출 생략" in reason
        
        print(f" ▶ 추출 시그니처: {result.get('signature')}")
        if is_cached:
            print(f" ▶ 판정 결과: 🚀 성공 (LLM 호출 비용 0원, 캐시 자동 일치)")
        else:
            print(f" ▶ 판정 결과: 🤖 성공 (LLM 최초 1회 연산수행)")
            
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())
