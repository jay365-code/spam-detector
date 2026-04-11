import sqlite3
import random

def generate_test_message():
    conn = sqlite3.connect(r'd:\Projects\spam-detector\backend\data\signatures.db')
    cursor = conn.cursor()
    
    # 길이가 12~20 사이이고 너무 특수문자만 있지 않은 비교적 정상적인 한글 시그니처 하나 랜덤 추출
    cursor.execute("""
        SELECT signature 
        FROM signatures 
        WHERE length(signature) > 10 
        AND signature NOT LIKE '%?%' 
        AND signature NOT LIKE '%!%' 
        ORDER BY RANDOM() LIMIT 1
    """)
    res = cursor.fetchone()
    
    if not res:
        print("시그니처를 찾을 수 없습니다.")
        return
        
    sig = res[0]
    
    msg = f"""(광고) 회원님만을 위한 특별한 혜택 안내!

다음 내용을 확인하시고 VIP 전용 입장권 받아가세요.

{sig}

위 내용은 이번 주까지만 유효합니다.
아래 링크에서 지금 바로 확인!
http://pf.kakao.com/_IQmuT

신청코드: VVIP300
무료수신거부: 080-111-2222"""

    with open("test_message.txt", "w", encoding="utf-8") as f:
        f.write(msg)
        
    print("테스트 메시지를 test_message.txt 에 생성했습니다.")
    print("추출된 테스트용 시그니처:", sig)

if __name__ == "__main__":
    generate_test_message()
