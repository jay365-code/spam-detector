import sys
import os
import asyncio

# Ensure backend imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.agents.content_agent.agent import ContentAnalysisAgent

def run_tests():
    agent = ContentAnalysisAgent()
    stage1 = {"detected_pattern": "None"}
    
    test_cases = [
        # 1. 샌드위치 오분류(기존에 Type A로 뚫렸던 케이스) -> Type B(is_normal_layout: True) 방어 목표
        ("♨♨3월 신규 회원 스페셜 ♨♨ 안녕하세요. 3월도 어느덧 중순을 지나 마무리로 향하고 있는 시점입니다. 바쁜 일정 속에서도 잠시 참고하실 수 있도록 정리된 안내 전달드립니다. 첫입금 플러스 파워볼 요율 지급 성공길.com 아래에서 참조바랍니다. 감사합니다.", "Sandwich Spam (Target: Type B)"),
        
        # 2. 난독화 오분류(기존에 Type A로 뚫렸던 케이스) -> Type B(is_garbage_obfuscation: True) 방어 목표
        ("목요일이네요 십오퍼받고 오늘도화이팅 cd-a905 코온도르", "Obfuscation Spam (Target: Type B)"),
        
        # 3. 고질량 스팸 유실 방어(기존에 멍청하게 Type B로 버려졌던 것들) -> Type A 유지 목표 (is_normal_layout: False)
        ("울산 남구 1차2차 20대 한태중 ☎ 010-8146-1369", "Dense Keywords Spam (Target: Type A)"),
        ("FOMC 금리동결 발표 지금은 정보와 타이밍 싸움입니다 핵심만 보셔야 합니다 카카오톡 7 회신", "Stock Economic Spam (Target: Type A)"),
        
        # 4. 순수 정상 안내 문자 (대표님 우려 사항: HAM이 풍선효과로 스팸이 되는지) -> HAM 유지 목표
        ("[Web발신] 이지원님, 주문하신 쿠팡 로켓배송 상품이 오늘 14~16시 사이에 문 앞 도착 예정입니다. 감사합니다. 배송조회: bit.ly/test", "Pure HAM (Target: HAM, No Signals)")
    ]
    
    print("=== NEW PROMPT VERIFICATION TEST ===")
    for msg, category in test_cases:
        print(f"\n[Test Group: {category}]")
        print(f"Text: {msg[:60]}...")
        try:
            res = agent.check(msg, stage1)
            is_spam = res.get('is_spam')
            
            semantic_class = "Type_A" if is_spam else "HAM"
            signals = res.get('signals', {})
            active_signals = [k for k, v in signals.items() if v and k not in ('harm_anchor', 'route_or_cta')]
            
            if is_spam and active_signals:
                semantic_class = "Type_B (SIGNALS CAUGHT)"
                
            print(f" -> Result Label: {'SPAM' if is_spam else 'HAM'}")
            print(f" -> Semantic Class: {semantic_class}")
            print(f" -> Active B Signals: {active_signals}")
            print(f" -> Reason: {res.get('reason')}")
        except Exception as e:
            print(f" -> Error: {e}")

if __name__ == "__main__":
    run_tests()
