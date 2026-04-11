import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts13 = [
    "0000 진행 .com",
    "1 2 + t 2% CJAN .NET",
    "24 ㄷ.H. kaka axax12",
    "A.N.Y = rⓑ.gy/cmsgom",
    "ANi muⓩ.so/an1c1s2",
    "BHC 오후➂~오후➄시 케이카",
    "E ➂⑩ ⑩ ➂➂7 .ⓒ0ⓜ : NS77",
    "STOP 73 2@@@ ㅋr : vc98",
    "개인돈 승인금액안내 >",
    "꺼어어엄 즉시춤",
    "매이 칭용 슐 넛콤 .",
    "복주머니 https://v .im/cjsfyd4",
    "비/S/금/비/D/면 :",
    "새로운 픈 곽실 장 21990580",
    "생활비 급하게 필요하신분 텔",
    "심심하죠? blackpoker25",
    "쟈 머니 yaya83",
    "전 비 당 00 용 /누 epst",
    "즐 01 한 혈 상 음",
    "커우우움 즉시춤"
]

def insert_v13():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts13:
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
    insert_v13()
