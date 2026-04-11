import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts8 = [
    "코크B돌E발T vo.la/0103",
    "& ▶ 신년첫.NET",
    "& ▷ 신년첫.Net",
    ",000 ,000 888 muⓩ.so/ANi001g",
    "10 전 HD4949 문",
    "20/500 ko907",
    "3 레 KR7999",
    "3만 SST2026",
    "A 77 muⓩ.so/anicsn016a",
    "ANi muⓩ.so/anicsn016a",
    "b 111 muⓩ.so/anicsn016a",
    "c 111 muⓩ.so/anicsn016a",
    "CA O 섭스 15ㅋ 테레casamo365",
    "k 77 muⓩ.so/anicsn016a",
    "o 111 muⓩ.so/anicsn016a",
    "O.O0O 3 QR399",
    "OI 1OOOO 5O'/․ 7474",
    "t 111 muⓩ.so/anicsn016a",
    "기분 새 식 당 0% JS 7",
    "꼬오우움 즉시춤",
    "꾸우움 즉시춤",
    "당 상 른 담 른 비 면",
    "대전 피시 문의 2397 2404 용",
    "더블로 888 yb-01.",
    "면 편 / 시 사 / 가 /",
    "스@웨 5927 5800",
    "연초 건승기원 -들발2O평 - 코난",
    "울 한K 테T 여신들 ☎ 67329952",
    "위고88배민진행중",
    "정말 굿마인드 O대",
    "청주 70 용암동 01026445520쭈",
    "쿠우움 즉시춤",
    "타 이 자 하 분 당 인 g",
    "텔 τ 697 꽁 2만",
    "팔팔 20충 치 ㅡ낀 17 18"
]

def insert_v8():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts8:
            clean_text = HistoryManager.get_clean_text(text)
            if not clean_text or len(clean_text) > int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30")):
                print(f"Skipped (length error): {clean_text}")
                continue
                
            cursor.execute('''
                INSERT INTO spam_history (normalized_text, count, last_updated)
                VALUES (?, 10, CURRENT_TIMESTAMP)
                ON CONFLICT(normalized_text) DO UPDATE SET 
                    count = count + 1,
                    last_updated = CURRENT_TIMESTAMP
            ''', (clean_text,))
            
            cursor.execute('SELECT count FROM spam_history WHERE normalized_text = ?', (clean_text,))
            result = cursor.fetchone()
            current_count = result[0] if result else 10
            
            success_count += 1
            try:
                print(f"Processed: {clean_text} (Current count: {current_count})")
            except UnicodeEncodeError:
                print(f"Processed: [텍스트 출력 인코딩 오류 회피] (Current count: {current_count})")
            
        conn.commit()
    print(f"\n작업 완료! 정상 처리된 텍스트 수: {success_count}건")

if __name__ == '__main__':
    insert_v8()
