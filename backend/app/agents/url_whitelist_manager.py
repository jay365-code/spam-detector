import os
import sqlite3
import re
from urllib.parse import urlparse
from pathlib import Path
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# DB 파일 경로 설정 (기존 data 디렉토리에 저장하여 보존되게 함)
DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "url_whitelist.db"

# 주요 단축 URL 서비스 도메인 목록 (DB 체크 우회용)
SHORTENER_DOMAINS = {
    "bit.ly", "goo.gl", "buly.kr", "vo.la", "han.gl", 
    "ko.gl", "tuney.kr", "sbz.kr", "me2.do", "vvd.bz", 
    "url.kr", "m.site.naver.com", "vdo.kr", "t.co",
    "tinyurl.com", "is.gd", "buff.ly", "ow.ly"
}

def init_db():
    """URL Whitelist DB 초기화 및 테이블 생성"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS safe_urls (
                domain_path TEXT PRIMARY KEY,
                status TEXT DEFAULT 'SAFE',
                hit_count INTEGER DEFAULT 1,
                last_updated TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
            )
        ''')
        conn.commit()

# 모듈 로드 시 DB 상태 보장 및 클린업
init_db()

class UrlWhitelistManager:
    @staticmethod
    def cleanup_old_records(days: int = 365):
        """지정된 기간(기본 1년) 이전의 오래된 화이트리스트 자동 삭제"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    DELETE FROM safe_urls 
                    WHERE last_updated < datetime('now', 'localtime', '-{days} days')
                ''')
                deleted_rows = cursor.rowcount
                conn.commit()
                if deleted_rows > 0:
                    logger.info(f"[UrlWhitelist] Cleaned up {deleted_rows} old records (older than {days} days)")
        except Exception as e:
            logger.error(f"[UrlWhitelist] Cleanup Failed: {e}")

    @staticmethod
    def is_short_url(url_str: str) -> bool:
        """단축 URL 여부 판별 (단축 URL은 최종 목적지를 모르므로 DB 사전검색 우회)"""
        try:
            test_url = url_str if "://" in url_str else "http://" + url_str
            parsed = urlparse(test_url)
            domain = parsed.netloc.lower().split(':')[0]
            if domain.startswith("www."):
                domain = domain[4:]
            
            # 완전 일치 또는 서브도메인 포함 일치
            for sd in SHORTENER_DOMAINS:
                if domain == sd or domain.endswith("." + sd):
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def get_clean_domain_path(url_str: str) -> str:
        """
        URL 파라미터(? 쿼리)를 제거하고 순수하게 [메인도메인/경로] 까지만 추출
        예: https://www.lotteon.com/display/plan?mall_no=2 -> lotteon.com/display/plan
        """
        if not url_str or url_str == "Unknown":
            return ""
            
        test_url = url_str if "://" in url_str else "http://" + url_str
        try:
            parsed = urlparse(test_url)
            domain = parsed.netloc.lower().split(':')[0]
            if domain.startswith("www."):
                domain = domain[4:]
                
            path = parsed.path.rstrip("/")
            if not domain:
                return ""
            
            return f"{domain}{path}"
        except Exception:
            return ""

    @staticmethod
    def check_safe_url(url_str: str) -> bool:
        """
        주어진 URL이 안전한 화이트리스트 DB에 있는지 확인
        단축 URL일 경우 무조건 False 반환 (사전 검사 무의미)
        """
        if not url_str or url_str == "Unknown":
            return False
            
        if UrlWhitelistManager.is_short_url(url_str):
            # 단축 URL은 도착지 확인 전까지는 알 수 없음
            return False
            
        clean_dp = UrlWhitelistManager.get_clean_domain_path(url_str)
        if not clean_dp:
            return False

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT status FROM safe_urls WHERE domain_path = ?', (clean_dp,))
            result = cursor.fetchone()
            
            if result and result[0] == 'SAFE':
                # 캐시 히트 시 hit_count 증가
                cursor.execute('''
                    UPDATE safe_urls 
                    SET hit_count = hit_count + 1, last_updated = datetime('now', 'localtime')
                    WHERE domain_path = ?
                ''', (clean_dp,))
                conn.commit()
                return True
                
        return False

    @staticmethod
    def add_safe_url(url_str: str) -> bool:
        """
        CONFIRMED SAFE 판정을 받은 최종 URL을 화이트리스트에 영구 등재
        """
        if not url_str or url_str == "Unknown":
            return False
            
        clean_dp = UrlWhitelistManager.get_clean_domain_path(url_str)
        if not clean_dp:
            return False
            
        # 단축 도메인 자체를 화이트리스트에 맹목적으로 넣는 것 방지 
        # (예: bit.ly 자체를 안전하다고 넣으면 모든 bit.ly 통과됨)
        if UrlWhitelistManager.is_short_url(url_str):
            logger.warning(f"[UrlWhitelist] Attempted to whitelist a short domain directly: {clean_dp}. Ignored.")
            return False

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO safe_urls (domain_path, status, hit_count, last_updated, created_at)
                    VALUES (?, 'SAFE', 1, datetime('now', 'localtime'), datetime('now', 'localtime'))
                    ON CONFLICT(domain_path) DO UPDATE SET 
                        status = 'SAFE',
                        hit_count = hit_count + 1,
                        last_updated = datetime('now', 'localtime')
                ''', (clean_dp,))
                conn.commit()
                logger.info(f"[UrlWhitelist] Added/Updated SAFE URL: {clean_dp}")
                return True
        except Exception as e:
            logger.error(f"[UrlWhitelist] Error adding URL {clean_dp}: {e}")
            return False
