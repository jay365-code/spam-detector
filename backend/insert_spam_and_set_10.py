import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

# 기존 프로젝트 경로 인식
BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts = [
    "& 스포츠 ② 퍼 17:00~19:00 .",
    "+ % 25 so7989",
    "5% 네이버 썸티켓검색 3838yy",
    "5% 네이버 썸티켓검색 some8",
    "NEW 최 5N wk8912",
    "간단하게 kkss79",
    "긴 0/ 간 안 , 인",
    "별밤티켓 1 5% 4163bb",
    "비/상/금/비/대/면 :",
    "십에서백 문 의 칠육,93/육구,68",
    "o F 징 ㅌ레:",
    "울샨 한K 2차 ☎전화 590일6521",
    "울샨 한K 걸 ☎전화 6694팔859",
    "울샨 한K 걸 ☎전화 6862삼989",
    "울샨 한K 동양 ☎전화 6694팔859",
    "울샨 한K 동양 ☎전화 7425팔865",
    "울샨 한K 이차 ☎전화 6862삼989",
    "울샨 한K 테T ☎전화 5959구045",
    "울샨 한K 테T ☎전화 8252구565",
    "팟치 복받으세요 auaⓤ.kr",
    "호랑이티켓 1 5% tiger0583"
]

def insert_and_set_count_10():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts:
            clean_text = HistoryManager.get_clean_text(text)
            if not clean_text or len(clean_text) > int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30")):
                print(f"Skipped (length error): {clean_text}")
                continue
                
            cursor.execute('''
                INSERT INTO spam_history (normalized_text, count, last_updated)
                VALUES (?, 10, CURRENT_TIMESTAMP)
                ON CONFLICT(normalized_text) DO UPDATE SET 
                    count = 10,
                    last_updated = CURRENT_TIMESTAMP
            ''', (clean_text,))
            success_count += 1
            print(f"Success: {clean_text} (count: 10)")
            
        conn.commit()
    print(f"\n작업 완료! 정상 처리된 텍스트 수: {success_count}건")

if __name__ == '__main__':
    insert_and_set_count_10()
