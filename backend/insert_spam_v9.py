import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

# 콘솔 출력 인코딩 오류 방지
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts9 = [
    "& ▶ 신년첫.NET",
    "& ▷ 신년첫.Net",
    ",000 ,000 888 muⓩ.so/ANi001g",
    "a 333 muⓩ.so/anicsn016a",
    "b 111 muⓩ.so/anicsn016a",
    "B.C.T 돌/무 발/한 01C-02c",
    "c 111 muⓩ.so/anicsn016a",
    "k 111 muⓩ.so/anicsn016a",
    "o 111 muⓩ.so/anicsn016a",
    "t 111 muⓩ.so/anicsn016a",
    "고ZH R8-H8 ㅉㅋ 오늘 그날",
    "꼬오우움 즉시춤",
    "당 상 른 담 른 비 면",
    "배로 cv-ve",
    "사/주말가능 /항시대기",
    "스 L8-X8 ㅉㅋ 오늘 그날",
    "울산 모든국적 01080962476",
    "정말 굿마인드 O대"
]

def insert_v9():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts9:
            clean_text = HistoryManager.get_clean_text(text)
            if not clean_text or len(clean_text) > int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30")):
                print(f"Skipped (length error): {clean_text}")
                continue
                
            # UPSERT 로직 (기존 +1, 신규 10)
            cursor.execute('''
                INSERT INTO spam_history (normalized_text, count, last_updated)
                VALUES (?, 10, CURRENT_TIMESTAMP)
                ON CONFLICT(normalized_text) DO UPDATE SET 
                    count = count + 1,
                    last_updated = CURRENT_TIMESTAMP
            ''', (clean_text,))
            
            # 갱신 후 현재 카운트 확인
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
    insert_v9()
