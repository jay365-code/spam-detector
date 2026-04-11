import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts11 = [
    "#유 #앤 #미 01077358552",
    "& ▶ 신년첫.NET",
    "& ▷ 신년첫.Net",
    "(ca) :OO/ O:OO o% 1 O BK74O",
    "(ca) :OO/ O:OO o% 1 O BK74O",
    "/ / /행 바로/ / 카/토/옥",
    "15,000 + 8879 8779",
    "②④ , jjgg5555",
    "3 O.O0O O0 ks784",
    "A 888 muⓩ.so/an1c1s2",
    "b 111 muⓩ.so/anicsn016a",
    "c 111 muⓩ.so/anicsn016a",
    "O.O0O O0 3 ks784",
    "t 111 muⓩ.so/anicsn016a",
    "가 입? 바로 포",
    "고ZH R8-H8 ㅉㅋ 오늘 그날",
    "뉴 ( ) 20:OO~ 3:3O O 1 O",
    "당 상 른 담 른 비 면",
    "매일 꽁5~10지급 tel @mamoncs24",
    "받구 ㅇF ㅌ pu7969",
    "밤 한국혼 꾸굿",
    "상담 문의 mgw787 라 so2389",
    "스 L8-X8 ㅉㅋ 오늘 그날",
    "스@웨 @ 9685 9310",
    "ㅇF 까지! ㅌ",
    "ㅇF 까지! ㅌ pu7969",
    "ㅇF 바로 ㅌ pu7969",
    "ㅇF 오대 까지! ㅌ",
    "ㅇF ㅌ pu7969",
    "월평포세 5574-2552",
    "인 시 한 한 jodo11",
    "전 비 당 00 용 /누 epst",
    "즐 01 한 혈 상 음",
    "쿠우움 즉시춤",
    "한 해 으로 진행 저 부 OO"
]

def insert_v11():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts11:
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
    insert_v11()
