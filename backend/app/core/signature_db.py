import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# .env 로드
load_dotenv()

# DB 파일 경로 설정 (.env의 DB_DATA_DIR 우선 적용)
env_db_dir = os.getenv("DB_DATA_DIR")
if env_db_dir:
    DB_DIR = Path(env_db_dir).resolve()
else:
    DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"

DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "signatures.db"

def init_db():
    """Signature DB를 초기화합니다."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signatures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signature TEXT UNIQUE NOT NULL,      
                    byte_length INTEGER,                 
                    category TEXT DEFAULT 'spam',        
                    source TEXT DEFAULT 'manual',        
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    hit_count INTEGER DEFAULT 0,
                    last_hit TIMESTAMP
                )
            ''')
            # 부분 일치 검색 속도를 미세하게 올리고 시그니처 정렬 조회를 돕기 위한 인덱스
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_signature_text ON signatures (signature)')
            conn.commit()
            logger.info(f"[SignatureDB] Successfully connected and initialized DB at: {DB_PATH}")
    except Exception as e:
        logger.error(f"[SignatureDB] Failed to connect or initialize DB: {e}")

# 모듈 로드 시 DB 상태 보장
init_db()

class SignatureDBManager:
    @staticmethod
    def find_matching_signature(clean_msg: str) -> str:
        """
        주어진 메시지 텍스트(공백 제거 원본 권장) 내에 
        DB에 저장된 시그니처들 중 서브스트링(Substring)으로 일치하는 패턴이 있는지 
        초고속 SQLite C엔진(instr)으로 검색합니다.
        
        Args:
            clean_msg (str): 검사할 스팸 메시지 원본 (가급적 띄어쓰기 제거 권장)
            
        Returns:
            str: 매칭된 시그니처 원문. 매칭이 없을 경우 빈 문자열("") 반환
        """
        if not clean_msg:
            return ""

        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                # instr(?, signature) > 0 은 `signature` 문자열이 `?` 문자열 안에 부분 수록되어 있는지를 검사합니다.
                cursor.execute('''
                    SELECT signature 
                    FROM signatures 
                    WHERE instr(?, signature) > 0 
                    ORDER BY created_at DESC, length(signature) DESC
                    LIMIT 1
                ''', (clean_msg,))
                
                result = cursor.fetchone()
                if result:
                    matched_sig = result[0]
                    # 적중 카운트 안전하게 1 증가
                    cursor.execute('''
                        UPDATE signatures 
                        SET hit_count = hit_count + 1, last_hit = CURRENT_TIMESTAMP 
                        WHERE signature = ?
                    ''', (matched_sig,))
                    conn.commit()
                    return matched_sig
                    
        except Exception as e:
            logger.error(f"[SignatureDB] Failed to scan matching sequence: {e}")
            
        return ""

    @staticmethod
    def get_signatures(page: int = 1, limit: int = 500, search_query: str = "", sort_col: str = "hit_count", sort_order: str = "desc") -> dict:
        """
        프론트엔드 조회를 위한 서버사이드 페이징 및 정렬 기능 포함 조회 메서드
        """
        offset = (page - 1) * limit
        safe_cols = {"signature", "byte_length", "category", "source", "created_at", "hit_count", "last_hit"}
        sort_col = sort_col if sort_col in safe_cols else "hit_count"
        sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"
        
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                
                base_query = "FROM signatures"
                params = []
                
                if search_query:
                    base_query += " WHERE signature LIKE ?"
                    params.append(f"%{search_query}%")
                
                # 전체 개수 파악
                cursor.execute(f"SELECT COUNT(*) {base_query}", params)
                total_count = cursor.fetchone()[0]
                
                # 데이터 추출
                query = f"SELECT signature, byte_length, source, hit_count, created_at, last_hit {base_query} ORDER BY {sort_col} {sort_order} LIMIT ? OFFSET ?"
                cursor.execute(query, (*params, limit, offset))
                
                rows = cursor.fetchall()
                data = []
                for r in rows:
                    data.append({
                        "signature": r[0],
                        "byte_length": r[1],
                        "source": r[2],
                        "hit_count": r[3] or 0,
                        "created_at": r[4],
                        "last_hit": r[5]
                    })
                    
                return {
                    "total": total_count,
                    "page": page,
                    "limit": limit,
                    "data": data
                }
        except Exception as e:
            logger.error(f"[SignatureDB] Failed to get signatures: {e}")
            return {"total": 0, "page": page, "limit": limit, "data": []}

    @staticmethod
    def delete_signature(signature: str) -> bool:
        """단건 시그니처 삭제"""
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM signatures WHERE signature = ?", (signature,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"[SignatureDB] Failed to delete signature: {e}")
            return False

    @staticmethod
    def add_signature(signature: str, category: str = "spam", source: str = "manual") -> bool:
        """단건 시그니처 개별 추가"""
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO signatures (signature, byte_length, category, source) 
                    VALUES (?, ?, ?, ?)
                ''', (signature, len(signature.encode('utf-8')), category, source))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"[SignatureDB] Failed to add signature: {e}")
            return False

    @staticmethod
    def bulk_insert_signatures(entries: list) -> dict:
        """
        시그니처 일괄 인서트 (INSERT OR IGNORE)
        UNIQUE 제약 위반(중복) 시 자동 무시하고, 삽입/무시 건수를 반환합니다.
        
        Args:
            entries: [{"signature": str, "byte_length": int, "category": str, "source": str}, ...]
            
        Returns:
            {"inserted": int, "ignored": int}
        """
        inserted = 0
        ignored = 0
        
        try:
            with sqlite3.connect(DB_PATH, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.cursor()
                
                for entry in entries:
                    sig = entry.get("signature", "")
                    if not sig:
                        continue
                    
                    cursor.execute('''
                        INSERT OR IGNORE INTO signatures 
                        (signature, byte_length, category, source) 
                        VALUES (?, ?, ?, ?)
                    ''', (
                        str(sig),
                        entry.get("byte_length"),
                        str(entry.get("category", "spam")),
                        entry.get("source", "excel_import")
                    ))
                    
                    if cursor.rowcount > 0:
                        inserted += 1
                    else:
                        ignored += 1
                
                conn.commit()
                logger.info(f"[SignatureDB] Bulk insert completed: {inserted} inserted, {ignored} ignored")
                
        except Exception as e:
            logger.error(f"[SignatureDB] Bulk insert failed: {e}")
            
        return {"inserted": inserted, "ignored": ignored}
