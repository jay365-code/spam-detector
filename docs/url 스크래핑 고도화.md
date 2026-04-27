# Bright Data 프록시 + CapSolver 캡차 솔버 도입

Playwright 기반 URL 스크래핑의 봇 탐지 차단 실패를 해결하기 위해, **Bright Data Residential Proxy**(IP 분산)와 **CapSolver**(CF Turnstile 토큰 생성)를 도입합니다.

- **현재 성공률**: ~60% (봇 탐지로 인한 timeout/CF 차단이 주 원인)
- **목표 성공률**: ~93%
- **예상 월 비용**: ~$64 (≈ 8.7만원, 일 5,000건 기준)

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

---

### 4. 의존성 및 문서

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
6. **문서 업데이트** (README)
7. **테스트**: CF 보호된 URL (`t.ly/Mer7J`)로 검증

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
