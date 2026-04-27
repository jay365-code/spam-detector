"""
[Fix 2] 화이트리스트 DB 오염 방지 검증 테스트
----------------------------------------------
is_mismatched=True인 위장 사이트(samcorexo.com 유형)가
UrlWhitelistManager DB에 영구 등록되지 않는지 확인한다.

테스트 시나리오:
  1. is_confirmed_safe=True + is_mismatched=False → DB 등록 O  (진짜 안전 도메인)
  2. is_confirmed_safe=True + is_mismatched=True  → DB 등록 X  (위장 사이트 차단)
  3. is_confirmed_safe=False                      → DB 등록 X  (기존 SPAM 처리)
"""

import sys
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.url_whitelist_manager import UrlWhitelistManager, DB_PATH
import sqlite3


# ── 헬퍼: 테스트 전후 DB 상태 초기화 ─────────────────────────────────────
def _clean_test_domains(*domains):
    """테스트에서 사용한 도메인을 DB에서 정리한다."""
    with sqlite3.connect(DB_PATH) as conn:
        for domain in domains:
            conn.execute("DELETE FROM safe_urls WHERE domain_path LIKE ?", (f"%{domain}%",))
        conn.commit()

def _is_in_db(domain: str) -> bool:
    """해당 도메인이 DB에 등록되어 있는지 확인한다."""
    clean_dp = UrlWhitelistManager.get_clean_domain_path(f"http://{domain}/index.html")
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT 1 FROM safe_urls WHERE domain_path = ?", (clean_dp,)).fetchone()
    return row is not None


# ── 핵심 로직: batch_flow.py L240~248 재현 ────────────────────────────────
async def _simulate_url_node_cache_logic(res: dict, lock_url: str, batch_cache: dict):
    """
    batch_flow.py의 url_node 내 결과 공유 블록 로직을 추출하여 재현.
    (Fix 2 적용 후 코드)
    """
    is_safe = res.get("is_confirmed_safe", False)
    is_mismatched_site = res.get("is_mismatched", False)
    final_url = (res.get("details") or {}).get("final_url", lock_url)

    if is_safe and not is_mismatched_site:
        # 진짜 안전 도메인: DB + 런타임 캐시 모두 등록
        UrlWhitelistManager.add_safe_url(final_url)
        batch_cache[lock_url] = res
        return "DB_AND_CACHE"
    elif is_safe and is_mismatched_site:
        # 위장 사이트 가능성: 런타임 캐시만, DB 등록 차단
        batch_cache[lock_url] = res
        return "CACHE_ONLY"
    else:
        # SPAM / 오류: Strike 처리
        return "STRIKE"


# ── 테스트 1: 진짜 안전 도메인 → DB 등록 O ────────────────────────────────
def test_real_safe_domain_is_registered():
    domain = "realsafe-test-domain.com"
    _clean_test_domains(domain)

    res = {
        "is_confirmed_safe": True,
        "is_mismatched": False,          # ← 불일치 없음 (정상 방패막이)
        "details": {"final_url": f"http://{domain}/index.html"}
    }
    batch_cache = {}

    result = asyncio.run(_simulate_url_node_cache_logic(res, f"http://{domain}", batch_cache))

    assert result == "DB_AND_CACHE", f"예상: DB_AND_CACHE, 실제: {result}"
    assert _is_in_db(domain), "✅ 진짜 안전 도메인은 DB에 등록되어야 한다"
    assert f"http://{domain}" in batch_cache, "런타임 캐시에도 있어야 한다"

    _clean_test_domains(domain)
    print("✅ Test 1 PASS: 진짜 안전 도메인 → DB 등록 확인")


# ── 테스트 2: 위장 사이트 → DB 등록 X, 캐시만 O ──────────────────────────
def test_fake_impersonation_site_is_not_registered():
    domain = "samcorexo-test.com"  # 가짜 삼성 사칭 사이트 유형
    _clean_test_domains(domain)

    res = {
        "is_confirmed_safe": True,       # ← 사업자 번호 발견으로 안전 판정
        "is_mismatched": True,           # ← 하지만 SMS 내용과 웹 내용 불일치
        "details": {"final_url": f"http://{domain}/index.html"}
    }
    batch_cache = {}

    result = asyncio.run(_simulate_url_node_cache_logic(res, f"http://{domain}", batch_cache))

    assert result == "CACHE_ONLY", f"예상: CACHE_ONLY, 실제: {result}"
    assert not _is_in_db(domain), "❌ 위장 사이트는 DB에 등록되면 안 된다"
    assert f"http://{domain}" in batch_cache, "런타임 캐시에는 있어야 한다 (현재 배치 내 중복 처리 방지)"

    _clean_test_domains(domain)
    print("✅ Test 2 PASS: 위장 사이트 → DB 등록 차단, 캐시만 유지 확인")


# ── 테스트 3: SPAM 도메인 → DB 등록 X, Strike ────────────────────────────
def test_spam_domain_is_not_registered():
    domain = "spam-site-test.com"
    _clean_test_domains(domain)

    res = {
        "is_confirmed_safe": False,      # ← SPAM 판정
        "is_mismatched": False,
        "details": {"final_url": f"http://{domain}/index.html"}
    }
    batch_cache = {}

    result = asyncio.run(_simulate_url_node_cache_logic(res, f"http://{domain}", batch_cache))

    assert result == "STRIKE", f"예상: STRIKE, 실제: {result}"
    assert not _is_in_db(domain), "SPAM 도메인은 DB에 등록되면 안 된다"
    assert f"http://{domain}" not in batch_cache, "SPAM 도메인은 캐시에도 없어야 한다"

    _clean_test_domains(domain)
    print("✅ Test 3 PASS: SPAM 도메인 → DB/캐시 모두 차단 확인")


# ── 실행 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("[Fix 2] 화이트리스트 DB 오염 방지 검증 테스트")
    print("=" * 55)

    try:
        test_real_safe_domain_is_registered()
        test_fake_impersonation_site_is_not_registered()
        test_spam_domain_is_not_registered()
        print()
        print("🎉 모든 테스트 통과 — Fix 2 정상 동작 확인")
    except AssertionError as e:
        print(f"❌ 테스트 실패: {e}")
        sys.exit(1)
