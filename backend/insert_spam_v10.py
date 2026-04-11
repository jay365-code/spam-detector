import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts10 = [
    "파티 2- 6 많참부",
    "& ▶ 신년첫.NET",
    "/ / /행 바로/ / 카/토/옥",
    "? 20 500 appa1313",
    "> 3:00-4:00 30콩충 파바 2만",
    "10 전 HD4949 문",
    "15,000 + 8879 8779",
    "15000 @LK4422",
    "3~5 / 100 tell p 9 tok P 6",
    "A 77 muⓩ.so/anicsn016a",
    "A 888 muⓩ.so/an1c1s2",
    "ANi muⓩ.so/an1c1s2",
    "c 111 muⓩ.so/anicsn016a",
    "E ➂⑩ ⑩ ➂➂7 .ⓒ0ⓜ : NS77",
    "k 111 muⓩ.so/anicsn016a",
    "t 111 muⓩ.so/anicsn016a",
    "가 입? 바로 포",
    "고ZH R8-H8 ㅉㅋ 오늘 그날",
    "꾸우움 즉시춤",
    "들발2O 연초 건승기원 코난",
    "면 친절 문의 /",
    "새해 새로운 오푼 쟝",
    "월평포세 5574-2552",
    "재 대상 +배 + 6"
]

def insert_v10():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts10:
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
    insert_v10()
