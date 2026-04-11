import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts4 = [
    "26년새해1등복권 dokdo.in/fYRH",
    "& +5 +8 % SEH",
    ",000 0,000 11 ①et②.kr/hpeUc",
    ",000 0,000 11 ①ⓔt②.kr/hpeUc",
    "[비]-[상]-[금]-[문]-[의]",
    "24 X X 20~5000 :Dodo655",
    "8253 .com 8253",
    "CA O 섭스 100ㅋ 드가자 ⓒ - .",
    "UI 한K 테T 여인들 ☎ 68623989",
    "면 요 분 담 라 / 자 0 0",
    "면필요 오 상 /문 0",
    "비 샹 금 깨에w 주십쇼 dr59",
    "새해 자금 총알 大출 - 4-",
    "새해 자금 총알 大출 카",
    "새해꽁 만 환",
    "새해꽁 만 환 SST2026",
    "셔츠룸 010 5649 9971",
    "울샨 한K 2차 ☎전화 590일6521",
    "울샨 한K 동양 ☎전화 6694팔859",
    "울샨 한K 이차 ☎전화 6862삼989",
    "팟치 복받으세요 auaⓤ.kr",
    "팟치 복받으세요 aⓤau.kr",
    "평생남 . T 3+ 5+ 1 + 4 드 2",
    "호랑이티켓 1 5% tiger0583"
]

def insert_v4():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts4:
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
    insert_v4()
