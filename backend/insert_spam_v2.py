import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

# 기존 프로젝트 경로 인식
BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts2 = [
    "리_모_콘 도_바 ㄹ_ㄹ 3ㅅ1~7ㅅ1",
    "상담문의 d 84 d 85",
    "새해 곽실장 21990580",
    "새해 자금 총알 大출 - 4-",
    "오시는 길 ca-na1",
    "울샨 한K 걸 ☎전화 6694팔859",
    "울샨 한K 동양 ☎전화 6694팔859",
    "울샨 한K 테T ☎전화 5959구045",
    "접속 3만 환전",
    "즉시 지급 30,000 TPL78",
    "평생남 . T 3+ 5+ 1 + 4 드 2"
]

def insert_10_or_increment():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts2:
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
    insert_10_or_increment()
