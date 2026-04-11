import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts17 = [
    "- . 2사B 15ㅋ !",
    "$$비상금$$ :",
    "? 19 ㅌ ya9050",
    "_ 0000 00000 tw⑤3m.coM",
    "_ 0000 00000 tw⑤3m.Com",
    "_ 0000 00000 tw⑤3m.cOM",
    "> 17:00-18:00 30콩 gs25 2만",
    "3 O.O0O O0 LPL74 LPL745",
    "③③7 c M nS77 30 10",
    "40 까쥐 @ y a 9 0 5 0",
    "7698-7750 천 오 안 션 입니다",
    "ANi1 1111 muⓩ.so/aNirt1w",
    "ANi2 1111 muⓩ.so/aNirt1w",
    "ANi3 1111 glo①.in/ani1n2",
    "ANi3 1111 muⓩ.so/aNirt1w",
    "ANi4 1111 ru①.kr/0uLWL4",
    "ANi5 1111 ru①.kr/0uLWL4",
    "ANi6 1111 ru①.kr/0uLWL4",
    "ANi7 1111 ru①.kr/0uLWL4",
    "ANi7 3333 ru①.kr/0uLWL4",
    "ANi7 8888 ru①.kr/0uLWL4",
    "B똘 5시 C빨 7시까지 T",
    "Fre222 시간 2용 부탁 nss63",
    "G2G갑 2 + t 진행 2% CJAN .NET",
    "wk8912 2사쿱 5쿱",
    "가 방 적 좋 채 good",
    "급..문.의 라.인 : px234",
    "까지 https://v .im/tkawn1",
    "로 / 사 자 인 : mg853",
    "바로 2 t 진행 2% CJAN .NET",
    "肪 스피드 승인 . 가 7613 0",
    "병오 & https://v .im/신년복",
    "비 면 일 인 ~ 카 mk",
    "생활비 빠르게 필요하신분 텔",
    "수동 개& https://v .im/신년복",
    "아 나 누 가 / 카 문 8156 4843",
    "오 창 신 규 하 21311221",
    "요 한 저 한 문의 77",
    "유 앤 - 달토 미 - 7735 8552",
    "유 앤 - 미 - 7735",
    "유 앤 - 미 - 7735 5852",
    "유 앤 - 미 - 7735 8552",
    "유 앤 - 미 - 7735 8852",
    "자 의 일 한 woo6966",
    "전 단 / 한 인 : q e",
    "추운겨울 전 곽실장 21990580",
    "ㅋr 30 10 ③③7평 .C0m ns77",
    "편 바 ~ 지 -3924-9716 후",
    "혼 한국 01 즐 음"
]

def insert_v17():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts17:
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
    insert_v17()
