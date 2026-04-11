import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts12 = [
    "& ▶ 신년첫.NET",
    "& ▷ 신년첫.Net",
    ",000 ,000 888 muⓩ.so/ANi001g",
    "10 전 HD4949 문",
    "10/2000 / kbo0078 서류 간편",
    "15,000 + 8879 8779",
    "2 2 2% CDEC .NET",
    "②④ , jjgg5555",
    "A 888 muⓩ.so/an1c1s2",
    "A.N.Y = rⓑ.gy/cmsgom",
    "b 111 muⓩ.so/anicsn016a",
    "B.C.T 돌/무 발/한 01C-02c",
    "BANK( ) O7~O9 B K 7 4 0",
    "c 111 muⓩ.so/anicsn016a",
    "https://2 .es/1gGk8",
    "k 77 muⓩ.so/anicsn016a",
    "o 111 muⓩ.so/anicsn016a",
    "t 111 muⓩ.so/anicsn016a",
    "WON @#// rⓑ.gy/c07x9o",
    "고ZH R8-H8 ㅉㅋ 오늘 그날",
    "구) 현) 터 ok W 42",
    "당 상 른 담 른 비 면",
    "매일 꽁5~10지급 tel @mamoncs24",
    "발 ~ 시 까 한 % 애프 .",
    "상담 문의 mgw787 라 so2389",
    "스 L8-X8 ㅉㅋ 오늘 그날",
    "스@웨 @ 9685 9310",
    "ㅇF 까지! ㅌ pu7969",
    "ㅇF ㅌ pu7969",
    "재 대상ok +배 + 6",
    "쟈 머니 ic767",
    "쟈 머니 yaya83",
    "전 비 당 00 용 /누 epst",
    "즐 01 한 혈 상 음",
    "한 해 으로 진행 저 부 OO"
]

def insert_v12():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts12:
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
    insert_v12()
