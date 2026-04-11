import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts7 = [
    ",000 ,000 888 muⓩ.so/ANi001g",
    ". + 상담문의 77",
    "2 2 2% CDEC .NET",
    "2 t 2% CJAN .NET",
    "2026새해 지급 중 33 T1",
    "20-500 qp71",
    "38 새 해 기 념 3 8 S M 9 7 72",
    "a 333 muⓩ.so/anicsn016a",
    "A 77 muⓩ.so/anicsn016a",
    "ANi muⓩ.so/anicsn016a",
    "b 111 muⓩ.so/anicsn016a",
    "c 111 muⓩ.so/anicsn016a",
    "k 111 muⓩ.so/anicsn016a",
    "k 77 muⓩ.so/anicsn016a",
    "o 111 muⓩ.so/anicsn016a",
    "O.O0O 2회 LGU000",
    "t 111 muⓩ.so/anicsn016a",
    "금 대출 28 톡",
    "당실 식사 q 7",
    "대전 피시 문의 2397 2404 용",
    "신 +5 +8 링 0 S 0",
    "위고88배민진행중",
    "청주 70 용암동 01026445520쭈",
    "팔라완 . 매일 출발 ..건승 기원"
]

def insert_v7():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts7:
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
    insert_v7()
