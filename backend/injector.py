import os
import sqlite3
import sys

# 백엔드 모듈 경로 추가
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.agents.history_manager import DB_PATH, HistoryManager

messages = [
    "☆업글☆ -성부- ☎2184-9541",
    "2 @@@  9 8 % mn07",
    "2쟝 9 90쟝 .NET 코드KMEN",
    "l 6 l 9 l 5 0 c b - 2 0 2 5",
    "가 + 만+ 만 /tu038 /e3616",
    "가 비 + 만 + / KM7944",
    "가 시 1 만 + 만+ / KM7944",
    "급전~ 사 xxpopo9 라 xxpopo99",
    "기념 ⑨ 30%⑦ 337 . c s77",
    "달. 유 . 할 의 OIO 77358552",
    "만 % 지 문 은 만 @ 문 지 의",
    "면 절/안전 kkci",
    "비肪倍 친 /안 주",
    "소 B 문 의 ㄱ 0 1 0 8486 4138",
    "스 구 X O (3)(3)(7) ㅁ ⓝ③(7)(7)",
    "여기 결 사 금 8450 3970 저 후",
    "여기 한 결 사 금 8450 3970 저",
    "월평 포세 장미입니다 2955 3789",
    "장미 ↓ ↓ ↓ ☎2955 3789",
    "큼큼 펑3 바로지급"
]

def inject_seed_data():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        count_updated = 0
        for original_text in messages:
            clean_text = HistoryManager.get_clean_text(original_text)
            if not clean_text:
                continue
                
            # 카운트를 무조건 10으로 강제 세팅(또는 UPSERT)
            cursor.execute('''
                INSERT INTO spam_history (normalized_text, count, last_updated)
                VALUES (?, 10, CURRENT_TIMESTAMP)
                ON CONFLICT(normalized_text) DO UPDATE SET 
                    count = 10,
                    last_updated = CURRENT_TIMESTAMP
            ''', (clean_text,))
            print(f"[주입 완료] {clean_text} (count=10)")
            count_updated += 1
            
        conn.commit()
        print(f"\n총 {count_updated}건의 초기 블랙리스트 데이터가 SPAM 임계치(10건) 상태로 정상 적재되었습니다.")

if __name__ == "__main__":
    inject_seed_data()
