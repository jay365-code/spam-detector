import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts16 = [
    "ANi5 1111 ru①.kr/0uLWL4",
    "$$비상금$$ :",
    "$비상금$ :",
    "@ RED b tt00048",
    "_ 0000 00000 tw⑤3m.Com",
    "+ + 배민2 증 s 64",
    "2 지급 t진행중 2% CJAN .NET",
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
    "Fre222 시간 2용 부탁 nss63",
    "G2G갑 2 + t 진행 2% CJAN .NET",
    "sanDss 시간 2용 부탁 sasn777.",
    "개&금 https://v .im/신년복",
    "고ZH RHQ-QQ 오 늘 그 날",
    "까지 https://v .im/tkawn1",
    "면 요 자, , 부 g d",
    "ㅂr 大 dk41850",
    "바로 2 t 진행 2% CJAN .NET",
    "새해 https://v .im/dbwk4",
    "생활비 빠르게 필요하신분 텔",
    "소B 급하게 한분",
    "수동 개& https://v .im/신년복",
    "여성용먹는젤리러브그라.info",
    "오 창 신 규 하 21311221",
    "일 부 음 / 요 만 5666 0808",
    "주 포쉐 황금 민부 01083747360",
    "즉 , + BJ8879 BY8879",
    "지금 2 & t 진행 2% CJAN .NET",
    "추운겨울 전 곽실장 21990580"
]

def insert_v16():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts16:
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
    insert_v16()
