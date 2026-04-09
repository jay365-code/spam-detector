import os
import sqlite3
import re
from pathlib import Path
from dotenv import load_dotenv

# .env 로드 및 환경변수 설정
load_dotenv()
MAX_HOLD_SHORT_LENGTH = int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30"))
HOLD_SPAM_THRESHOLD = int(os.getenv("HOLD_SPAM_THRESHOLD", "10"))

# DB 파일 경로 설정 (기존 data 디렉토리에 저장하여 보존되게 함)
DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "short_spam_history.db"

def init_db():
    """History DB 초기화 및 테이블 생성"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spam_history (
                normalized_text TEXT PRIMARY KEY,
                count INTEGER DEFAULT 1,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

# 모듈 로드 시 DB 상태 보장
init_db()

class HistoryManager:
    @staticmethod
    def get_clean_text(text: str) -> str:
        """
        사용자의 요구사항(Exact Match): 공백, 탭, 줄바꿈만 완벽히 제거
        """
        # 정규표현식으로 모든 화이트스페이스(공백, 탭, 줄바꿈) 제거
        return re.sub(r'\s+', '', text)
        
    @staticmethod
    def is_eligible_for_hold(text: str) -> bool:
        """
        파이썬 레벨 이중 방어: 정규화된 텍스트가 제한길이 이하인지 체크
        """
        clean_text = HistoryManager.get_clean_text(text)
        return len(clean_text) <= MAX_HOLD_SHORT_LENGTH

    @staticmethod
    def add_and_check_threshold(original_text: str) -> tuple[int, bool]:
        """
        주어진 텍스트의 뼈대(공백제거)를 만들어 SQLite 카운트를 올리고,
        Threshold(10건) 도달 여부(is_spam_lockon)를 반환합니다.
        
        Returns:
            (현재_누적_카운트, 스팸_격상_여부)
        """
        clean_text = HistoryManager.get_clean_text(original_text)
        
        # 길이가 거의 없는 0자 텍스트는 빈도 누적의 의미가 없으므로 제외
        if not clean_text:
            return 0, False

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # SQLite 3.24+ 문법 UPSERT
            cursor.execute('''
                INSERT INTO spam_history (normalized_text, count, last_updated)
                VALUES (?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(normalized_text) DO UPDATE SET 
                    count = count + 1,
                    last_updated = CURRENT_TIMESTAMP
            ''', (clean_text,))
            
            # 업데이트된 카운트 조회
            cursor.execute('SELECT count FROM spam_history WHERE normalized_text = ?', (clean_text,))
            result = cursor.fetchone()
            current_count = result[0] if result else 1
            
            conn.commit()

        is_spam_lockon = current_count >= HOLD_SPAM_THRESHOLD
        return current_count, is_spam_lockon

    @staticmethod
    def get_count(original_text: str) -> int:
        """단순 카운트 조회용 (기존 카운트 미증가)"""
        clean_text = HistoryManager.get_clean_text(original_text)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT count FROM spam_history WHERE normalized_text = ?', (clean_text,))
            result = cursor.fetchone()
            return result[0] if result else 0
