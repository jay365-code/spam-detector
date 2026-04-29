"""
단축 URL 도메인 관리 — 단일 소스 (Single Source of Truth)

모든 모듈(nodes.py, url_whitelist_manager.py, excel_handler.py,
batch_flow.py, main.py)은 이 모듈의 SHORTENER_DOMAINS set과
is_short_url() 함수를 참조합니다.

저장소: url_whitelist.db → shortener_domains 테이블
초기 시딩: 하드코딩 목록 + shorteners_list.txt → INSERT OR IGNORE
"""

import os
import re
import sqlite3
from pathlib import Path
from app.core.logging_config import get_logger

logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()

# ── DB 경로 (url_whitelist.db와 동일 파일) ──
env_db_dir = os.getenv("DB_DATA_DIR")
if env_db_dir:
    _DB_DIR = Path(env_db_dir).resolve()
else:
    _DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"

_DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DB_DIR / "url_whitelist.db"

# ── 하드코딩 기본 도메인 (초기 시딩용) ──
_BUILTIN_DOMAINS = {
    "a.to", "abit.ly", "adf.ly", "adfoc.us", "agshort.link", "aka.ms", "amzn.to", "apple.co", "asq.kr",
    "bit.do", "bit.ly", "bitly.com", "bitly.cx", "bitly.kr", "bl.ink", "blow.pw", "buff.ly", "buly.kr",
    "c11.kr", "clic.ke", "cogi.cc", "coupa.ng", "cutt.it", "cutt.ly",
    "di.do", "dokdo.in", "dub.co",
    "fb.me",
    "gmarket.it", "goo.gl", "goo.su", "gooal.kr",
    "han.gl", "horturl.at",
    "ii.ad", "iii.ad", "instagr.am", "is.gd",
    "j.mp",
    "kakaolink.com", "kko.to", "ko.fm", "ko.gl", "koe.kr",
    "link24.kr", "linktr.ee", "lrl.kr",
    "mcaf.ee", "me2.do", "muz.so", "myip.kr",
    "naver.me",
    "ouo.io", "ow.ly",
    "qrco.de",
    "rb.gy", "rebrand.ly", "reurl.kr", "rul.kr",
    "sbz.kr", "short.io", "shorter.me", "shorturl.at", "shrl.me", "shrtco.de",
    "t.co", "t.ly", "t.me", "t2m.kr", "tiny.cc", "tinyurl.com", "tne.kr", "tny.im", "tr.ee", "tuney.kr",
    "url.kr", "uto.kr",
    "v.gd", "vdo.kr", "vo.la", "vvd.bz", "vvd.im",
    "wp.me",
    "youtu.be", "yun.kr",
    "zrr.kr",
    "tnia.cc", "2.lnkme.net", "lnkme.net", "alie.kr", "bz.kr", "booly.kr", "qaa.kr",
    "m.site.naver.com", "g.co",
    # nodes.py에만 있던 도메인 통합
    "kko.to",
    # url_whitelist_manager.py에만 있던 도메인 통합  
    "vdo.kr", "m.site.naver.com",
}


def _load_txt_domains() -> set:
    """shorteners_list.txt에서 도메인 로드"""
    domains = set()
    try:
        list_path = os.path.join(os.path.dirname(__file__), "shorteners_list.txt")
        if os.path.exists(list_path):
            with open(list_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip().lower()
                    if line and not line.startswith("#"):
                        domains.add(line)
    except Exception as e:
        logger.warning(f"Failed to load shorteners_list.txt: {e}")
    return domains


def _init_table():
    """shortener_domains 테이블 생성 + 초기 시딩"""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS shortener_domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT UNIQUE NOT NULL,
                    source TEXT DEFAULT 'manual',
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_shortener_domain ON shortener_domains (domain)')

            # 기존 데이터가 없으면 초기 시딩
            cursor = conn.execute("SELECT COUNT(*) FROM shortener_domains")
            count = cursor.fetchone()[0]
            if count == 0:
                logger.info("[ShortenerUtils] 초기 시딩 시작...")
                all_seed = _BUILTIN_DOMAINS | _load_txt_domains()
                for d in all_seed:
                    source = 'builtin' if d in _BUILTIN_DOMAINS else 'txt_file'
                    conn.execute(
                        "INSERT OR IGNORE INTO shortener_domains (domain, source) VALUES (?, ?)",
                        (d, source)
                    )
                conn.commit()
                logger.info(f"[ShortenerUtils] {len(all_seed)}개 도메인 시딩 완료")
            else:
                logger.info(f"[ShortenerUtils] DB에 {count}개 도메인 로드됨")
    except Exception as e:
        logger.error(f"[ShortenerUtils] 테이블 초기화 실패: {e}")


def _load_from_db() -> set:
    """DB에서 전체 도메인 로드"""
    domains = set()
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.execute("SELECT domain FROM shortener_domains")
            for row in cursor.fetchall():
                domains.add(row[0])
    except Exception as e:
        logger.error(f"[ShortenerUtils] DB 로드 실패: {e}")
        # DB 실패 시 하드코딩 + txt 폴백
        domains = _BUILTIN_DOMAINS | _load_txt_domains()
    return domains


# ── 모듈 초기화 ──
_init_table()
SHORTENER_DOMAINS: set = _load_from_db()
logger.info(f"[ShortenerUtils] SHORTENER_DOMAINS 초기화 완료: {len(SHORTENER_DOMAINS)}개")


def is_short_url(url: str) -> bool:
    """URL이 단축 URL 서비스에 속하는지 판별 (호스트 정확 일치)"""
    if not url:
        return False
    try:
        clean_url = re.sub(r'^https?://', '', url.lower())
        clean_url = re.sub(r'^www\.', '', clean_url)
        host = clean_url.split('/')[0].split('?')[0].split(':')[0]
        return host in SHORTENER_DOMAINS
    except Exception:
        return False


def reload():
    """DB에서 도메인을 다시 로드하여 메모리 set 갱신"""
    global SHORTENER_DOMAINS
    SHORTENER_DOMAINS = _load_from_db()
    logger.info(f"[ShortenerUtils] 도메인 리로드 완료: {len(SHORTENER_DOMAINS)}개")


def add_domain(domain: str) -> bool:
    """도메인 추가 (DB + 메모리)"""
    domain = domain.strip().lower()
    if not domain:
        return False
        
    # URL 형태(경로, 프로토콜 포함)로 입력된 경우 베어 도메인(Host)만 추출
    clean_url = re.sub(r'^https?://', '', domain)
    clean_url = re.sub(r'^www\.', '', clean_url)
    domain = clean_url.split('/')[0].split('?')[0].split(':')[0]
    
    if not domain:
        return False
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO shortener_domains (domain, source) VALUES (?, 'manual')",
                (domain,)
            )
            conn.commit()
        SHORTENER_DOMAINS.add(domain)
        logger.info(f"[ShortenerUtils] 도메인 추가: {domain}")
        return True
    except Exception as e:
        logger.error(f"[ShortenerUtils] 도메인 추가 실패: {e}")
        return False


def delete_domain(domain: str) -> bool:
    """도메인 삭제 (DB + 메모리)"""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.execute("DELETE FROM shortener_domains WHERE domain = ?", (domain,))
            conn.commit()
            if cursor.rowcount > 0:
                SHORTENER_DOMAINS.discard(domain)
                logger.info(f"[ShortenerUtils] 도메인 삭제: {domain}")
                return True
        return False
    except Exception as e:
        logger.error(f"[ShortenerUtils] 도메인 삭제 실패: {e}")
        return False


def get_domains(page: int = 1, limit: int = 500, search_query: str = "",
                sort_col: str = "domain", sort_order: str = "asc") -> dict:
    """페이징 조회 (UI용)"""
    offset = (page - 1) * limit
    safe_cols = {"domain", "source", "created_at"}
    sort_col = sort_col if sort_col in safe_cols else "domain"
    sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"

    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            base_query = "FROM shortener_domains"
            params = []

            if search_query:
                base_query += " WHERE domain LIKE ?"
                params.append(f"%{search_query}%")

            cursor = conn.execute(f"SELECT COUNT(*) {base_query}", params)
            total_count = cursor.fetchone()[0]

            query = f"SELECT domain, source, created_at {base_query} ORDER BY {sort_col} {sort_order} LIMIT ? OFFSET ?"
            cursor = conn.execute(query, (*params, limit, offset))

            data = []
            for r in cursor.fetchall():
                data.append({
                    "domain": r[0],
                    "source": r[1],
                    "created_at": r[2]
                })

            return {"total": total_count, "page": page, "limit": limit, "data": data}
    except Exception as e:
        logger.error(f"[ShortenerUtils] 조회 실패: {e}")
        return {"total": 0, "page": page, "limit": limit, "data": []}
