import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts15 = [
    "①등조합 dokdo.in/fYRH",
    "\" \" ☞ 59②cYZ.COM",
    "ANi 1 muⓩ.so/ANinn1n",
    "www. 9.life",
    "개인돈문의 d",
    "고ZH RHQ-QQ 오 늘 그 날",
    "면 요 자, , 부 g d",
    "ㅂr 大 dk41850",
    "부작용이없는불개미환.info",
    "비 인 ~ 카 문 q",
    "새해 https://v .im/dbwk4",
    "소B 급하게 한분",
    "아 나 누 가 / 문 8156 4843",
    "여성용먹는젤리러브그라.info",
    "자/ 인 전 사 @gorani",
    "전 자 인 1 문의 2386 5182",
    "쮸 와 ㅌ ya9050",
    "프리 nss63 ㅈ ㅜ소변경 참고"
]

def insert_v15():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts15:
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
    insert_v15()
