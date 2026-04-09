import asyncio
import os
import sys

# Add backend to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.agents.content_agent.agent import ContentAnalysisAgent
from app.agents.history_manager import HistoryManager

async def run_simulation():
    msg = "3ㅋㅈl급 십+⑩ 6+⑹ 삼+3 [] 567"
    print(f"[{msg}] 시뮬레이션 시작...")
    
    # 1. 길이 검사
    clean_text = HistoryManager.get_clean_text(msg)
    print(f"1. 뼈대 추출: '{clean_text}' (길이: {len(clean_text)})")
    is_eligible = HistoryManager.is_eligible_for_hold(msg)
    print(f"2. HOLD 룰 조건 통과(30자 이하) 여부: {'True' if is_eligible else 'False'}")

    # 2. LLM Call
    agent = ContentAnalysisAgent()
    print("3. LLM 요원 분석 중...")
    try:
        res = agent.check(msg, {})
    except Exception as e:
        print(f"LLM Error: {e}")
        return
        
    label = "HOLD_SHORT" if res.get('is_spam') == "HOLD_SHORT" else ("SPAM" if res.get('is_spam') else "HAM")
    print(f"4. LLM 리턴 객체: 라벨={label}, 확률={res.get('spam_probability')}, 사유={res.get('reason')}")

    # 3. BatchFlow & DB 시뮬레이션
    final_is_spam = res.get('is_spam')
    final_reason = res.get('reason')
    final_code = res.get('classification_code')
    
    if final_is_spam == "HOLD_SHORT":
        if not is_eligible:
            final_is_spam = False
            final_code = None
            final_reason = f"[HOLD 거부] 설정 글자수 초과. 안전을 위해 HAM으로 오버라이드. | {final_reason}"
        else:
            current_count, is_locked_on = HistoryManager.add_and_check_threshold(msg)
            print(f"5. DB 통계 반영! 해당 뼈대의 현재 누적 발송 횟수: {current_count}")
            if is_locked_on:
                final_is_spam = True
                final_code = "2"
                final_reason = f"🚫 [상습 난독화 스팸] 동일 뼈대 패턴 초과 누적 (현재 {current_count}건, Lock-on) | {final_reason}"
                print(">>> 🚨 10회 도달! 임계점 폭발 (SPAM 차단)")
            else:
                final_is_spam = False
                final_code = None
                final_reason = f"🛡️ [HOLD 관찰 중] 의도 불명 반복 문자 (누적 {current_count}회) | {final_reason}"
                print(">>> 🛡️ 임계점 미달. 억울한 오탐 방지를 위해 임시 HAM 통과 (로그 관찰)")

    print("-" * 50)
    print(f"최종 반환 is_spam: {final_is_spam}")
    print(f"최종 반환 code: {final_code}")
    print(f"최종 반환 reason: {final_reason}")

if __name__ == '__main__':
    asyncio.run(run_simulation())
