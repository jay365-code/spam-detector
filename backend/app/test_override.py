import asyncio
import os
import sys

# Setting paths properly
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from core.llm_manager import key_manager
# Initialize keys


from graphs.batch_flow import process_message

async def run():
    msg = "(광고) 이음통신 통신영업 박진형팀장 010-8480-0375 대표전화 1661-0588 안녕하세요 24번가 이사 제휴업체 인터넷 전국1등 이음통신입니다. 고객님, 이사 준비 중이시라면 인터넷 설치 절대 미루시면 안 됩니다. 현재 이사철이라 설치 예약이 하루 단위로 마감되고 있어 조금만 늦어도 인터넷 없이 3~5일씩 지연되는 경우가 매우 많습니다. 기존인터넷 이전설치시 혜택X 설치비만 청구되는걸 알고 계실까요? 저희 이음통신에서는 이사 고객 전용으로 오늘 접수 기준 최고 지원 혜택을 드리고 있습니다. 가능한 혜택 안내 휴대폰 + 인터넷 + 유심 진행시 최대100만원 지원혜택 인터넷+TV 최저 월 11,000원 구성 가능 통신 3사 요금 비교 후 가장 저렴한 조합 즉시 안내 인터넷 + TV 결합 시 추가 지원 최신 와이파이 무상 제공 설치비 절감 혜택 휴대폰 결합 할인 100% 적용 사전예약 시 원하는 날짜 우선 설치 !설치 가능 시간 !실제 납부 요금 !지원금 최대치 !즉시 확인하여 안내드리겠습니다. 혜택은 오늘 접수 기준으로만 보장되며, 늦어지면 동일 조건 유지가 어렵습니다. 이사할 땐 신규 설치가 혜택 최고! 인터넷+TV 11,000원 + 사은품최대 100만원 정"

    print("Running pipeline for the message...")
    res = await process_message(msg, "test_ibse_msg_1", [])
    
    print("\n--- 파이프라인 최종 결과 ---")
    print(f"IS_SPAM:     {res.get('is_spam')}")
    print(f"REASON:      {res.get('reason')}")
    print(f"CODE:        {res.get('code')}")
    print(f"IBSE_SIG:    {res.get('ibse_signature')}")
    print(f"IBSE_DECIS:  {res.get('ibse_category')}")

if __name__ == "__main__":
    asyncio.run(run())
