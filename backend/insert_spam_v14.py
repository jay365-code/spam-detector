import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

texts14 = [
    "①등조합 dokdo.in/fYRH",
    "\" \" ☞ 59②cYZ.COM",
    "/ / /행 바로/ / 카/토/옥",
    "/ X :@ _ 서류제출",
    "~ 3 O % ~! 63186 vox28.",
    "1 2 + t 2% CJAN .NET",
    "100% ! ☞8⑦2rzy.com",
    "100% 922ⓧzⓒ.CoM",
    "24 ㄷ.H. kaka axax12",
    "5 1+1~10+10 입 이 보 체 good",
    "ANi 1 muⓩ.so/ANinn1n",
    "New (CA) 19 ~21 NH505",
    "꺼어어엄 즉시춤",
    "껌껌 바로줘요",
    "꼼꼼 바로줘요",
    "ㄴ P 10 WA4449 T",
    "ㄷH ka nana59",
    "면 전 단 5783 1890",
    "ㅂ1 30.0 tjd123456",
    "븐 NH1245 빨간맛 출 타고 목 성",
    "비/S/금/비/D/면 :",
    "사/생계자금 /야간가능",
    "사고O타사O간단O v 11aa",
    "새해 이 &하이 블릭 5686 6330",
    "생활비 급하게 필요하신분 텔",
    "슐- 20% 오후 1 9③⑤cub.ⓒOM",
    "아 나 누 가 / 문 8156 4843",
    "와 ㅌ pu7969",
    "와여 @ ya9050",
    "자/ 인 전 사 @gorani",
    "쟈 머니 tuner50",
    "전 자 인 1 문의 2386 5182",
    "쮸 와 ㅌ ya9050",
    "커우우움 즉시춤",
    "하구 ㅌ pu7969"
]

def insert_v14():
    success_count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for text in texts14:
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
    insert_v14()
