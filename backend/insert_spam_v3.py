import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts3 = [
    "①등조합 https://sbz.kr/LIlRp",
    "26년새해1등복권 dokdo.in/fYRH",
    ",000 0,000 11 ①et②.kr/hpeUc",
    ",000 0,000 11 ①ⓔt②.kr/hpeUc",
    "◆NEW◆ 14:30~16:30 .com",
    "12 신년 이용감사 12(레오)",
    "15000 fK8865 fK53",
    "8253 .com 8253",
    "AB -> ANi ①ⓔt②.kr/hpeUc",
    "CA O 섭스 100ㅋ 드가자 ⓒ - .",
    "ZI 능10 쿠 RR3993",
    "긴 0/ 간 안 , 인",
    "리_모_콘 도_바 ㄹ_ㄹ 3ㅅ1~7ㅅ1",
    "면필요 오 상 /문 0",
    "ㅂ ㅣ대면 / hy10230",
    "비 샹 금 깨에w 주십쇼 dr59",
    "비/상/금/비/대/면 :",
    "새해 자금 총알 大출 - 4-",
    "새해꽁 만 환",
    "셔츠 & 하퍼 010 2473 9865",
    "셔츠 & 하퍼 010 5649 9971",
    "울샨 한K 동양 ☎전화 6694팔859",
    "울샨 한K 테T ☎전화 8252구565",
    "접속 3만 환전",
    "팟치 복받으세요 auaⓤ.kr",
    "평생남 . T 3+ 5+ 1 + 4 드 2"
]

def insert_v3():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts3:
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
            print(f"Processed: {clean_text} (Current count: {current_count})")
            
        conn.commit()
    print(f"\n작업 완료! 정상 처리된 텍스트 수: {success_count}건")

if __name__ == '__main__':
    insert_v3()
