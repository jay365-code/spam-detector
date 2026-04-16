import os
import asyncio
import sys

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), "."))

from app.agents.ibse_agent.service import IBSEAgentService

async def main():
    service = IBSEAgentService()
    
    msg1 = "삼성 25년 감사 행사 삼성전자 100주 응모시 100% 무료제공 https://link24.kr/DEaNmiI"
    msg2 = "꾸움 바로줘"
    
    print("=== 테스트 1: 단축 주소 단독 추출 테스트 ===")
    res1 = await service.process_message(msg1)
    print(f"결과: {res1['decision']}")
    print(f"시그니처: {res1.get('signature')}")
    print(f"사유: {res1.get('reason')}")
    print(f"CP949 길이: {res1.get('byte_len')}")
    print("")
    
    print("=== 테스트 2: 극단적 악성 은어(초단문) 테스트 ===")
    res2 = await service.process_message(msg2)
    print(f"결과: {res2['decision']}")
    print(f"시그니처: {res2.get('signature')}")
    print(f"사유: {res2.get('reason')}")
    print(f"CP949 길이: {res2.get('byte_len')}")

if __name__ == "__main__":
    asyncio.run(main())
