import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from app.agents.ibse_agent.agent import ibse_graph

async def run_test():
    messages = [
        "안녕하세요 회원님! 오늘 단 하루만 진행하는 가입시 10만 p 지급! a.to/25zTcms 서둘러 가입하세요. (광고)수신거부111",
        "[Web발신] (광고) 저희 VIP 방에 초대합니다. 급등주 정보 제공. 무료거부 080-xxx t.ly/k3pbB 확인바랍니다.",
        "▶특별 이벤트 안내◀ 본문 내용을 확인해주세요 https://vvd.im/proky 혜택 받아가세요",
        "신규회원 첫충전 30% 매일매일 터지는 잭팟! bit.ly/3PLZCrx 로 접속하세요."
    ]
    
    for i, msg in enumerate(messages):
        print(f"\n[{i+1}/4] 분석 중...")
        # IBSE 파이프라인은 공백이 제거된 압축 문자열을 인풋으로 받으므로 공백 제거
        match_text = msg.replace(" ", "")
        
        state = {
            "message_id": f"TEST_{i+1}",
            "match_text": match_text,
            "obfuscated_urls": [],
            "error": None,
            "extracted_signature": None,
            "extraction_type": None,
            "final_result": None
        }
        
        try:
            result = await ibse_graph.ainvoke(state)
            print(f"  - 원문: {msg}")
            print(f"  - 압축 본문: {match_text}")
            print(f"  ▶ 추출 시그니처: {result.get('extracted_signature')}")
            print(f"  ▶ 이유: {result.get('final_result', {}).get('reason', 'N/A')}")
        except Exception as e:
            print(f"  - 에러 발생: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env")))
    asyncio.run(run_test())
