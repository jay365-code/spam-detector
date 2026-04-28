# Bright Data 프록시 + CapSolver 캡차 솔버 도입

Playwright 기반 URL 스크래핑의 봇 탐지 차단 실패를 해결하기 위해, **Bright Data Residential Proxy**(IP 분산)와 **CapSolver**(CF Turnstile 토큰 생성)를 도입합니다.

- **현재 성공률**: ~60% (봇 탐지로 인한 timeout/CF 차단이 주 원인)
- **목표 성공률**: ~93%
- **예상 월 비용**: ~$64 (≈ 8.7만원, 일 5,000건 기준)

## 비용 산출 근거 (일 5,000건 기준)

> 실제 배치 데이터(`kisa_20260422_A`, 1,061건) 비율을 기반으로 산출

### 트래픽 프로파일

| 항목 | 비율 | 건수/일 | 건수/월 |
|------|------|---------|--------|
| 총 메시지 | 100% | 5,000 | 150,000 |
| URL 포함 메시지 | 34.5% | 1,725 | 51,750 |
| 단축URL (CF 보호 높음) | 26.8% of URL | 462 | 13,860 |
| 일반 도메인 중 CF 사용 (~15%) | | 123 | 3,690 |
| **CF 대응 필요 합계** | | **585** | **17,550** |

### 서비스별 월 비용

| 서비스 | 단가 | 산출 | 월 비용 |
|--------|------|------|--------|
| **CapSolver** (CF Turnstile) | $1.2/1K건 | 17,550건 × $1.2/1K | **$21** |
| **Bright Data** (Residential Proxy) | $5.04/GB | 1,725건/일 × 0.5MB × 30일 ≈ 8.6GB | **$43** |
| **합계** | | | **$64 (≈ 8.7만원)** |

### 속도 영향

| 항목 | 지연 | 비고 |
|------|------|------|
| 프록시 경유 | +0.5~1초/요청 | 모든 요청에 적용 |
| CapSolver API | +1~5초/요청 | CF 챌린지 실패 시에만 |
| **순효과** | **오히려 빨라짐** | 현재 실패(10초 낭비) → 프록시로 성공(3~5초) |

> 배치 1,000건 기준: 현재 ~25분 → 도입 후 ~22분 (약 3분 단축)

## User Review Required

> [!IMPORTANT]
> **Bright Data 계정 생성 및 Zone 설정이 선행되어야 합니다.**
> 1. [brightdata.com](https://brightdata.com) 에서 계정 생성
> 2. Residential Proxy Zone 생성 → `username`, `password` 획득
> 3. [capsolver.com](https://capsolver.com) 에서 계정 생성 → API Key 획득
> 4. 위 정보를 `.env` 에 입력

> [!WARNING]
> **프록시 비활성화 옵션 필수**: 프록시/솔버 서비스 장애 시 기존 Direct 방식으로 자동 fallback 해야 합니다. `.env`에서 ON/OFF 제어가 가능하도록 설계합니다.

## Proposed Changes

### 1. 환경 변수 추가

#### [MODIFY] [.env](file:///Users/jay/Projects/spam-detector/backend/.env)

```env
# ===== 스크래핑 외부 서비스 설정 =====
# Bright Data Residential Proxy (봇 탐지 IP 분산)
PROXY_ENABLED=0
PROXY_SERVER=http://brd.superproxy.io:33335
PROXY_USERNAME=brd-customer-XXXXXX-zone-YYYYYY
PROXY_PASSWORD=ZZZZZZZZZZ

# CapSolver CAPTCHA Solver (Cloudflare Turnstile 우회)
CAPSOLVER_ENABLED=0
CAPSOLVER_API_KEY=CAP-XXXXXXXXXXXXXXXXXXXXXXXX
```

- `PROXY_ENABLED=0` / `CAPSOLVER_ENABLED=0`: 기본값 비활성화 (계정 없이도 기존대로 동작)
- 서비스 준비 완료 후 `1`로 변경

---

### 2. CapSolver 클라이언트 모듈 (신규)

#### [NEW] [capsolver_client.py](file:///Users/jay/Projects/spam-detector/backend/app/agents/url_agent/capsolver_client.py)

CapSolver API 호출을 담당하는 독립 모듈. `tools.py`의 복잡도를 줄이기 위해 분리합니다.

```python
"""
CapSolver API 클라이언트
- Cloudflare Turnstile 토큰 생성
- 비동기(aiohttp 또는 requests in executor) 호출
"""

class CapSolverClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.capsolver.com"
    
    async def solve_turnstile(self, page_url: str, site_key: str) -> str | None:
        """
        Cloudflare Turnstile 토큰 생성
        1. createTask API 호출
        2. getTaskResult 폴링 (최대 30초)
        3. 토큰 반환 (실패 시 None)
        """
        ...
    
    @staticmethod
    def extract_sitekey(html_content: str) -> str | None:
        """
        HTML에서 Turnstile siteKey 추출
        - data-sitekey 속성
        - window._cf_chl_opt.chlApiSitekey
        - turnstile.render({sitekey: '...'})
        """
        ...
```

**주요 설계 결정**:
- `aiohttp` 대신 `requests` + `asyncio.to_thread()` 사용 (추가 의존성 없이 비동기화)
- 토큰 만료 시간이 ~2분이므로, 토큰 획득 후 즉시 주입
- API 호출 실패 시 `None` 반환 → 기존 로직 그대로 진행 (graceful degradation)

---

### 3. PlaywrightManager 수정

#### [MODIFY] [tools.py](file:///Users/jay/Projects/spam-detector/backend/app/agents/url_agent/tools.py)

#### 변경 1: 프록시 설정 추가 (브라우저 컨텍스트)

**현재** (L519-536): `browser.new_context()`에 프록시 없음

**변경 후**: `PROXY_ENABLED=1`이면 Bright Data 프록시를 컨텍스트에 주입

```python
# __init__에 프록시 설정 로드
def __init__(self, headless=True):
    ...
    self.proxy_enabled = os.getenv("PROXY_ENABLED", "0") == "1"
    self.proxy_config = None
    if self.proxy_enabled:
        self.proxy_config = {
            "server": os.getenv("PROXY_SERVER", ""),
            "username": os.getenv("PROXY_USERNAME", ""),
            "password": os.getenv("PROXY_PASSWORD", ""),
        }

# new_context() 호출 시 proxy 파라미터 추가
context = await self.browser.new_context(
    user_agent="...",
    proxy=self.proxy_config if self.proxy_enabled else None,  # ← 추가
    ...
)
```

**영향 범위**: Desktop(카카오) 컨텍스트와 Mobile 컨텍스트 **모두**에 동일 적용

#### 변경 2: CapSolver fallback 추가 (봇 방어 실패 시)

**현재** (L577-592): CF 감지 → Stealth 대기 → 클릭 시도 → 실패 시 포기

**변경 후**: 실패 시 CapSolver API로 토큰 생성 → 주입

```python
if is_bot_protected:
    # [기존] Stealth 자동 대기 + 클릭 시도
    protection_passed = await self.wait_for_bot_protection(page, max_wait=5)
    if not protection_passed:
        await self.attempt_captcha_bypass(page)
        await page.wait_for_timeout(3000)
        
        # [신규] CapSolver fallback
        if self.capsolver_enabled:
            html = await page.content()
            site_key = CapSolverClient.extract_sitekey(html)
            if site_key:
                token = await self.capsolver.solve_turnstile(page.url, site_key)
                if token:
                    # 토큰 주입
                    await page.evaluate(f'''
                        document.querySelector("[name=cf-turnstile-response]").value = "{token}";
                        // Turnstile callback 트리거
                        if (window.turnstile) turnstile.getResponse = () => "{token}";
                    ''')
                    await page.wait_for_timeout(3000)
                    # 재확인
                    text = await page.evaluate("document.body.innerText")
                    if not any(ind in text.lower() for ind in bot_protection_indicators):
                        logger.info("✅ CapSolver bypass successful!")
```

#### 변경 3: __init__에 CapSolver 초기화

```python
def __init__(self, headless=True):
    ...
    self.capsolver_enabled = os.getenv("CAPSOLVER_ENABLED", "0") == "1"
    self.capsolver = None
    if self.capsolver_enabled:
        from app.agents.url_agent.capsolver_client import CapSolverClient
        api_key = os.getenv("CAPSOLVER_API_KEY", "")
        if api_key:
            self.capsolver = CapSolverClient(api_key)
```

#### 변경 4: SNS 도메인 Desktop 전환 (deep-link 방지)

**현재** (L516-536): 카카오(`kakao.com`)만 Desktop context 사용

**변경 후**: deep-link를 발동하는 모든 SNS 도메인에 Desktop context 적용

```python
# 현재
is_kakao = "kakao.com" in url.lower()

# 변경
DESKTOP_DOMAINS = ["kakao.com", "t.me", "telegram.me", "instagram.com", "band.us"]
use_desktop = any(d in url.lower() for d in DESKTOP_DOMAINS)
```

**변경 이유**:
- `t.me`: 모바일 접속 시 "Open in Telegram" 앱 리다이렉트 → 스크래핑 실패
- `instagram.com`: 모바일 접속 시 "앱에서 열기" 모달이 콘텐츠 차단
- `band.us`: Band 앱 리다이렉트
- SNS 플랫폼은 콘텐츠가 Desktop/Mobile 동일 (스패머가 모바일 전용 콘텐츠 생성 불가)
- Desktop이 오히려 더 풍부한 메타데이터(구독자 수, 프로필 등) 제공
- Stealth `platform=Win32`와 Desktop UA가 일치하여 CF 탐지 확률 감소

> **스패머 자체 도메인(도박/피싱 사이트)은 기존대로 Mobile context 유지** — 실제 피해자(SMS 수신자)가 보는 모바일 화면 수집 필요

---

### 5. 의존성 및 문서

#### [MODIFY] [requirements.txt](file:///Users/jay/Projects/spam-detector/backend/requirements.txt)

추가 패키지 **없음**. `requests`는 이미 포함되어 있고, `asyncio.to_thread()`는 Python 표준 라이브러리입니다.

#### [MODIFY] [README.md](file:///Users/jay/Projects/spam-detector/docs/README.md)

스크래핑 아키텍처 섹션에 프록시/솔버 관련 설명 추가.

---

## 전체 흐름도

```
scrape_url(url) 호출
    │
    ├─ browser.new_context(proxy=Bright Data)  ← 🆕 IP 분산
    │
    ├─ page.goto(url, timeout=10s)
    │   └─ Bright Data 프록시 경유 → CF 입장에서 일반 사용자 IP
    │       └─ CF JS Challenge 자동 통과 확률 대폭 증가 ✅
    │
    ├─ CF 감지?
    │   ├─ NO → 정상 스크래핑 계속
    │   └─ YES → Stealth 대기 (5초)
    │       ├─ 통과 → 정상 스크래핑 계속
    │       └─ 실패 → 클릭 시도
    │           ├─ 통과 → 정상 스크래핑 계속
    │           └─ 실패 → CapSolver API 호출  ← 🆕
    │               ├─ siteKey 추출 → 토큰 생성 → 주입
    │               │   └─ 통과 → 정상 스크래핑 계속 ✅
    │               └─ 실패 → 기존대로 포기 (bot_protection_active=True)
    │
    └─ 텍스트/스크린샷/메타데이터 수집
```

## 구현 순서 (원자적 단계)

1. **`.env`에 환경 변수 추가** (비활성화 상태)
2. **`capsolver_client.py` 신규 모듈 생성**
3. **`tools.py` 수정**: `__init__`에 프록시/솔버 설정 로드
4. **`tools.py` 수정**: `new_context()`에 프록시 파라미터 추가
5. **`tools.py` 수정**: 봇 방어 실패 시 CapSolver fallback 추가
6. **`tools.py` 수정**: SNS 도메인 Desktop 전환 (`is_kakao` → `DESKTOP_DOMAINS`)
7. **문서 업데이트** (README)
8. **테스트**: CF 보호 URL + t.me 채널 URL로 검증

## Verification Plan

### 자동 테스트
```bash
# capsolver_client.py 단위 테스트
python -m pytest tests/test_capsolver_client.py -v

# siteKey 추출 테스트 (실제 CF 페이지 HTML 샘플)
python -c "from app.agents.url_agent.capsolver_client import CapSolverClient; ..."
```

### 수동 테스트
1. `PROXY_ENABLED=0`, `CAPSOLVER_ENABLED=0` → 기존과 동일하게 동작하는지 확인
2. `PROXY_ENABLED=1` → Bright Data 프록시 경유 확인 (IP 변경 로그)
3. `CAPSOLVER_ENABLED=1` → CF 보호 URL 통과 확인
4. 실제 배치 1회 돌려서 성공률 비교 (Before/After)

### 실패 시 안전장치
- 프록시 연결 실패 → Direct 접속으로 자동 fallback
- CapSolver API 에러 → `None` 반환, 기존 로직 유지
- 환경 변수 미설정 → 기능 비활성화 (기존 동작 보장)

---

## 예외 처리 정밀 분석

구현 시 반드시 처리해야 할 5가지 예외 시나리오입니다.

### 1. 🔴 프록시 연결 실패 → Direct fallback (필수)

| 시나리오 | 에러 패턴 | 처리 |
|---------|----------|------|
| 프록시 서버 다운 | `ERR_PROXY_CONNECTION_FAILED` | Direct 모드로 자동 전환 후 재시도 |
| 인증 실패 (비밀번호 오류) | `407 Proxy Authentication Required` | 로그 경고 + 세션 내 프록시 비활성화 |
| Bright Data 잔액 소진 | `403` 또는 연결 거부 | 로그 경고 + Direct fallback |

**구현 위치**: `tools.py` L701 `except Exception` 블록에 분기 추가

```python
if "err_proxy" in err_str or "proxy" in err_str or "407" in err_str:
    logger.warning(f"프록시 연결 실패 — Direct 모드로 fallback: {e}")
    self.proxy_enabled = False  # 이번 세션은 프록시 비활성화
    continue  # 재시도 (Direct로)
```

### 2. 🔴 CapSolver 잔액 소진 → 세션 내 비활성화 (필수)

| 시나리오 | 에러 코드 | 처리 |
|---------|----------|------|
| API 키 무효/만료 | `ERROR_KEY_DOES_NOT_EXIST` | `None` 반환 + 세션 내 비활성화 |
| 잔액 부족 | `ERROR_ZERO_BALANCE` | `None` 반환 + 세션 내 비활성화 |
| 네트워크 에러 | `requests` 예외 | `None` 반환 (일시적, 다음 건은 재시도) |
| 토큰 생성 타임아웃 | 폴링 30초 초과 | `None` 반환 |

**구현 위치**: `capsolver_client.py` 내부

```python
class CapSolverClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self._disabled = False  # 잔액 소진 시 이후 호출 전부 스킵
    
    async def solve_turnstile(self, ...):
        if self._disabled:
            return None
        ...
        if "ZERO_BALANCE" in error_code or "KEY_DOES_NOT_EXIST" in error_code:
            logger.error(f"⚠️ CapSolver 비활성화: {error_code}")
            self._disabled = True
            return None
```

### 3. 🟡 토큰 주입 시 null 엘리먼트 체크 (중요)

| 시나리오 | 원인 | 처리 |
|---------|------|------|
| `cf-turnstile-response` 없음 | CF 버전 변경, 비표준 구현 | `querySelector` null 체크 |
| 토큰 만료 (2분 초과) | CapSolver 폴링 지연 | 주입 전 시간 체크 |
| JS callback 미트리거 | 사이트별 다른 구현 | 여러 패턴 시도 |

**구현**: 안전한 토큰 주입 JS

```javascript
(() => {
    const el = document.querySelector("[name=cf-turnstile-response]");
    if (!el) return "NO_ELEMENT";
    el.value = "{token}";
    try { if (window.turnstile) turnstile.getResponse = () => "{token}"; } catch(e) {}
    try { if (window._cf_chl_opt?.chlApiCallback) window._cf_chl_opt.chlApiCallback("{token}"); } catch(e) {}
    return "OK";
})()
```

### 4. 🟡 siteKey 추출 실패 → graceful skip (중요)

| 시나리오 | 원인 | 빈도 |
|---------|------|------|
| `data-sitekey` 속성 없음 | CF Managed Challenge | 높음 |
| 난독화된 JS에 숨겨진 키 | CF inline 삽입 | 보통 |
| iframe 내부에 존재 | Turnstile iframe 로드 | 보통 |

**구현**: 3가지 패턴 순차 매칭

```python
patterns = [
    r'data-sitekey=["\']([0-9x][A-Za-z0-9_-]+)["\']',
    r'sitekey\s*:\s*["\']([0-9x][A-Za-z0-9_-]+)["\']',
    r'chlApiSitekey\s*:\s*["\']([0-9x][A-Za-z0-9_-]+)["\']',
]
# 모두 실패 시 None → CapSolver 호출 자체를 스킵
```

### 5. 🟢 프록시 에러 로그 구분 (권장)

기존 에러 로그(`Timeout`, `ERR_NAME_NOT_RESOLVED` 등)와 프록시 에러를 구분하여,
운영 중 프록시 문제를 빠르게 식별할 수 있도록 합니다.

```python
# 기존 에러 분류에 추가
if "proxy" in err_str:
    result["error"] = f"PROXY_ERROR: {e}"
    result["status"] = "proxy_error"
```
