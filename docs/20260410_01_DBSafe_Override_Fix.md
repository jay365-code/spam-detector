# Implementation Plan: URL DB Safe Fast-Pass 누락 (오탐) 수정

## Issue 명세 (4월 9일자 C 분석 결과)
- **현상:** Content Agent가 정상적인 구매/판매 의도나 특정 URL(`mual-mall.shop` 등)을 "키워드 기반"으로 피싱(SPAM)이라 오판함. (Code: 2)
- **모순점:** URL Agent는 해당 도메인이 `[DB Safe]`(검증된 안전 도메인)라고 정확히 식별하고 초고속 패스(Fast-Pass)를 발동시킴.
- **최종 결과:** 파이프라인에서 URL Agent의 "안전판정 오버라이드(Override)"가 발동하지 않고, 그대로 Content Agent의 오탐 결과(SPAM)가 채택되어 버리는 심각한 로직 누수가 발생함.

## 구조적 원인 분석 (Root Cause in Pipeline)
조사 결과, `app/graphs/batch_flow.py`의 Aggregator 노드에서 발생하는 데이터 소실 버그가 원인입니다.

1. **`url_node`의 누락:** URL Agent가 `[DB Safe]`로 조기 종료할 때, 반환 객체의 `details` 안에 `extracted_url` 및 `attempted_urls` 값을 넣지 않고 비운 채로 반환하고 있습니다. (약 150라인 부근)
2. **`aggregator_node`의 폐기 로직:** Aggregator는 `extracted_url`이 비어 있으면 "본문과 매칭되는 유효한 URL 파편이 없다"고 판단하여 전체 URL 분석 객체(`u_res`)를 빈 딕셔너리(`{}`)로 날려버립니다. (약 420라인 부근 `u_res = {}`)
3. **오버라이드 무산:** 그 결과, 아래에 준비되어 있던 억울함 방어 로직(`[URL: CONFIRMED SAFE & Content Matched (오탐 방어 Override)]`)이 통째로 스킵되어버립니다.

---

## 🛠️ 제안하는 코드 개선책 (Proposed Changes)

개발 서버 환경에서 아래의 내용을 따라 `app/graphs/batch_flow.py` 코드를 수정하십시오.

### 1. `app/graphs/batch_flow.py` - URL 노드 반환 데이터 수정
**수정 위치:** `url_node` 함수 내 `[DB Safe]` 초고속 패스 구간 (대략 149~155 라인 부근)

```diff
             if UrlWhitelistManager.check_safe_url(lock_url):
                 if cb: await cb(f"⚡ [DB Whitelist] 검증된 안전망. 초고속 HAM 오버라이드. ({lock_url})")
                 return {"url_result": {
                     "is_spam": False,
                     "is_confirmed_safe": True,
                     "reason": "⚡ [DB Safe] 검증된 안전 도메인 (초고속 패스)",
-                    "details": {"final_url": lock_url}
+                    "details": {
+                        "final_url": lock_url,
+                        "extracted_url": lock_url,
+                        "attempted_urls": [lock_url]
+                    }
                 }}
```

### 2. 기대 효과 (Expected Behavior)
- 위 코드 추가 시 강제 주입된 `extracted_url` 값을 통해 Aggregator 노드가 정상적으로 URL 객체(`u_res`)를 인식합니다.
- 이에 따라 `is_confirmed_safe == True` 조건문으로 진입하여, Content Agent가 실수로 SPAM 처리를 하더라도 최종적으로 `HAM (오탐 방어 Override)` 판정으로 뒤집게 됩니다!
- 결과적으로 시스템의 화이트리스트 기능과 오탐 방어 기능이 100% 정상 가동하게 됩니다.

---

## Verification Plan (검증 및 테스트 계획)
개발 서버에서 적용 후 테스트:
1. `mual-mall.shop` 등 DB Safe에 등록된 도메인이 포함된 텍스트를 테스트로 전송합니다.
2. Content Agent가 중고거래/사기 등 민감 키워드에 타격을 입어 SPAM이라 답하더라도, URL Agent가 DB Safe를 내어주었을 때 최종 판정이 **✅ HAM (정상)**으로 뒤집히는지 확인합니다.
3. 파이프라인 최종 의사결정 로그에 `- [URL: CONFIRMED SAFE & Content Matched (오탐 방어 Override)]` 가 출력되는지 확인합니다.
