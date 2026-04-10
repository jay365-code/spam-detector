import os
import sqlite3
import re
from pathlib import Path
from dotenv import load_dotenv
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# .env 로드 및 환경변수 설정
load_dotenv()
MAX_HOLD_SHORT_LENGTH = int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30"))
HOLD_SPAM_THRESHOLD = int(os.getenv("HOLD_SPAM_THRESHOLD", "10"))

# DB 파일 경로 설정 (.env의 DB_DATA_DIR가 우선, 없으면 기존 data 디렉토리)
env_db_dir = os.getenv("DB_DATA_DIR")
if env_db_dir:
    DB_DIR = Path(env_db_dir).resolve()
else:
    DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"

DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "short_spam_history.db"

def init_db():
    """History DB 초기화 및 테이블 생성"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS spam_history (
                    normalized_text TEXT PRIMARY KEY,
                    count INTEGER DEFAULT 1,
                    last_updated TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')
            conn.commit()
            logger.info(f"[HistoryManager] Successfully connected to DB at: {DB_PATH}")
    except Exception as e:
        logger.error(f"[HistoryManager] Failed to connect or initialize DB: {e}")

# 모듈 로드 시 DB 상태 보장 및 클린업
init_db()

class HistoryManager:
    @staticmethod
    def cleanup_old_records(days: int = 3650):
        """지정된 기간(기본 3650일, 10년) 이전의 오래된 스팸 누적 히스토리를 자동 삭제합니다 (Storage Leak 방지)"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                # SQLite datetime은 기본 UTC지만, localtime 옵션으로 현지 시간 기준 계산
                cursor.execute(f'''
                    DELETE FROM spam_history 
                    WHERE last_updated < datetime('now', 'localtime', '-{days} days')
                ''')
                deleted_rows = cursor.rowcount
                conn.commit()
                if deleted_rows > 0:
                    logger.info(f"[HistoryManager] Cleaned up {deleted_rows} old records (older than {days} days) to prevent storage leak.")
        except Exception as e:
            logger.error(f"[HistoryManager] Cleanup Failed: {e}")


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
                VALUES (?, 1, datetime('now', 'localtime'))
                ON CONFLICT(normalized_text) DO UPDATE SET 
                    count = count + 1,
                    last_updated = datetime('now', 'localtime')
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

    @staticmethod
    def get_all_records() -> list:
        """프론트엔드 관리를 위한 전체 목록 조회 (최신 1000건)"""
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT normalized_text, count, last_updated FROM spam_history ORDER BY last_updated DESC LIMIT 1000')
            return [{"normalized_text": row[0], "count": row[1], "last_updated": row[2]} for row in cursor.fetchall()]

    @staticmethod
    def add_manual_record(text: str, count: int = 1) -> bool:
        """프론트엔드에서 수동으로 스팸 텍스트와 누적값을 추가/수정"""
        clean_text = HistoryManager.get_clean_text(text)
        if not clean_text:
            return False
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO spam_history (normalized_text, count, last_updated)
                    VALUES (?, ?, datetime('now', 'localtime'))
                    ON CONFLICT(normalized_text) DO UPDATE SET 
                        count = ?,
                        last_updated = datetime('now', 'localtime')
                ''', (clean_text, count, count))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"[HistoryManager] Add record failed: {e}")
            return False

    @staticmethod
    def delete_record(text: str) -> bool:
        """특정 스팸 텍스트 레코드 삭제"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM spam_history WHERE normalized_text = ?', (text,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[HistoryManager] Delete record failed: {e}")
            return False

# 모듈 로딩 시 과거 데이터 청소 1회 수행
HistoryManager.cleanup_old_records(days=3650)
