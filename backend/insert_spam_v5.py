import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts5 = [
    ",000 ,000 888 muⓩ.so/ANi001g",
    "[ ]-[상]-[ ]-[ ]-[ ]",
    "[ANi] muⓩ.so/ANi001g",
    "> :30- :30 3O 충 맥DO날드",
    "100,000 출 WA4449",
    "2 2 2% CDEC .NET",
    "2026 달라진 지급 중 33 T1",
    "5@@ 1@@ :R O  2 5",
    "A -> A muⓩ.so/ANi001g",
    "lOO~6OO cv67",
    "ok vip po3314",
    "OI 1OOOO 5O'/․ 7474",
    "가 드입 레 건콤 .",
    "면 자 자, , 부 가 @",
    "불금엔 대 고--Ma",
    "울산 모든국적 01080962476",
    "첫 전 지 인트 문 -66.",
    "타 이 자 하 분 당 인 g",
    "푸 곽실장 21990580"
]

def insert_v5():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts5:
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
    insert_v5()
