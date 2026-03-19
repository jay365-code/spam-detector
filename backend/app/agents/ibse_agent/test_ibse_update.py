import asyncio
import os
import sys

# Add backend to PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from app.core.logging_config import setup_logging
from app.agents.ibse_agent.candidate import generate_candidates_node
from app.agents.ibse_agent.selector import select_signature_node
from app.agents.ibse_agent.state import IBSEState
from dotenv import load_dotenv

async def run_test():
    load_dotenv("backend/.env")
    setup_logging()

    text = "안녕하세요. 강남맛집 외식 체험신청 문의를 주셨던 분들께 안내드립니다. 3월 오픈 예정 캠폐인 내역 혜택 ▷ 2인 이상 고급레스토랑 식사권 ▷ 방문 후 사진 촬영 + 간단한 후기 작성 ▷ 2인 패키지 상품권 전액 무료 지원 + 파트너활동비 당일지급 ▷ 팔오워수,좋아요수 상관없이 초보자 가능 이용권 발송안내 하단 담당자 프로필 클릭 ! ▷ 담당자 성함 : 김현정 ▷ 카톡 연락처 추가 번호 : 010-8053-4132 ▷ 카톡 상단 사람플러스모양 클릭 > 연락처 클릭후 추가후 ▷ 카톡 연락처 친구추가 후 알림설정"
    # Basic normalization similar to utils
    import re
    normalized = re.sub(r'\s+', '', text)

    state: dict = {
        "message_id": "test_msg_01",
        "original_text": text,
        "match_text": normalized,
    }

    print("Generating candidates...")
    cand_state = generate_candidates_node(state)
    state.update(cand_state)

    print(f"Generated {len(state.get('candidates_20', []))} 20-byte and {len(state.get('candidates_40', []))} 40-byte candidates.")

    print("\nSelecting signature...")
    sel_result = await select_signature_node(state)
    state.update(sel_result)

    result = state.get("final_result", {})
    decision = result.get("decision")
    sig = result.get("signature")
    reason = result.get("reason")
    
    print("\n--- TEST RESULT ---")
    print(f"Decision : {decision}")
    print(f"Signature: {sig}")
    print(f"Reason   : {reason}")
    print("-------------------")

if __name__ == "__main__":
    asyncio.run(run_test())
