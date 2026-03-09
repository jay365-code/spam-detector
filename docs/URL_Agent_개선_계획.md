# URL 분석 에이전트 개선 계획

> **참조**: [Vibe coding 지침.md](./Vibe%20coding%20지침.md)  
> **분석 출처**: Gemini 로그 분석 (Batch Job 정지 원인)  
> **작성일**: 2026-03-09

---

## 1. 문제 요약 (Gemini 분석 결과)

### 1.1 브라우저 컨텍스트 비정상 종료 (TargetClosedError)
- **증상**: `playwright._impl._errors.TargetClosedError: Target page, context or browser has been closed`
- **원인**: Headless 브라우저가 OOM 또는 시스템 리소스 부족으로 강제 종료됨
- **영향**: 브라우저 소멸 후 예외 처리·세션 복구 미흡 → 후속 URL 스크래핑 노드들이 **무한 대기** → 전체 프로세스 정지

### 1.2 안티봇(Bot Protection) 차단 및 타임아웃 누적
- **증상**: `Scraping Timeout (likely bot protection)`, `Bot protection detected. Waiting for auto-resolution...`
- **원인**: 스팸 도메인들이 안티봇 사용 → `wait_until="domcontentloaded"` + `timeout=10000`(10초) 내 DOM 미완료
- **영향**: 리소스 반환 지연 반복 → 브라우저 충돌 가속화

### 1.3 네트워크 접근 실패 (ERR_ABORTED)
- **증상**: `net::ERR_ABORTED` (예: `https://tosto.re/aitutorplu` 등 악성/차단 사이트)
- **원인**: 유효하지 않거나 이미 차단된 스팸 링크 접근 시도

---

## 2. 현재 구현 상태 (2026-03-09 반영)

| 항목 | 현재 상태 | 위치 |
|------|----------|------|
| Stealth | 수동 `ENHANCED_STEALTH_SCRIPT` 적용됨 | `tools.py` L13-152 |
| 타임아웃 | `page.goto(..., timeout=10000)` (조정 없음) | `tools.py` L510 |
| 재시도 | `range(3)` + 에러 유형별 분기 (TargetClosed 3회, 그 외 2회) | `tools.py` |
| TargetClosedError | **처리 완료** (stop → 재시도) | `tools.py` |
| page/context 정리 | `page.close()` + `context.close()` (명시적) | `tools.py` |
| ERR_ABORTED | **처리 완료** (즉시 반환) | `tools.py` |
| User-Agent/Viewport | 고정 (iPhone 14 Pro) | `tools.py` L377-384 |

---

## 3. 개선 방안 (우선순위)

### Phase 1: 브라우저 인스턴스 자동 복구 (필수)

**목표**: TargetClosedError 발생 시 기존 브라우저를 파기하고 새 인스턴스로 재시작

**변경 대상**: `backend/app/agents/url_agent/tools.py` - `PlaywrightManager.scrape_url()`

**구현 내용**:
1. `playwright._impl._errors.TargetClosedError` import 및 명시적 예외 처리
2. TargetClosedError 발생 시:
   - `await self.stop()` 호출로 기존 브라우저/컨텍스트 완전 파기
   - `self.browser = None`, `self.playwright = None` 강제 초기화
   - 다음 attempt에서 `await self.start()`로 새 인스턴스 생성
3. 재시도 횟수: `range(2)` → `range(3)` (최대 2회 재시도, 브라우저 재시작 1회 포함)

**이유**: OOM 등으로 브라우저가 죽은 뒤, 같은 객체로 재시도하면 무한 대기 발생. 새 인스턴스로 교체해야 복구 가능.

---

### Phase 2: 타임아웃 유연성 및 메모리 누수 방지 (필수)

**목표**: 악성 스팸 URL의 리다이렉션·난독화 특성 반영 + 좀비 프로세스 방지

**변경 대상**: `backend/app/agents/url_agent/tools.py`

**구현 내용**:

1. **타임아웃 조정**
   - `page.goto(..., timeout=10000)` → `timeout=18000` (18초)
   - 환경변수 `SCRAPE_NAVIGATION_TIMEOUT` 추가 (기본 18000)

2. **명시적 page 해제**
   - `try` 블록 내 `page = await context.new_page()` 직후 `page` 변수 추적
   - `finally` 블록에서:
     - `if page and not page.is_closed(): await page.close()` (안전하게)
     - 그 다음 `await context.close()`
   - `context`가 이미 닫혀 있으면 `TargetClosedError` 가능 → `try/except`로 무시

3. **ERR_ABORTED 등 네트워크 오류 처리**
   - `page.goto()` 실패 시 `net::ERR_ABORTED` 문자열 검사
   - 해당 시 즉시 실패 반환 (재시도 불필요, 리소스 낭비 방지)

**이유**: 10초는 안티봇 사이트에서 부족할 수 있음. 15~20초 권장에 따라 18초로 조정. page를 명시적으로 닫아 좀비 프로세스 방지.

---

### Phase 3: Stealth 강화 (선택)

**목표**: 봇 탐지율 저하 (User-Agent·Viewport 동적 변경)

**변경 대상**: `backend/app/agents/url_agent/tools.py`

**구현 내용**:
1. User-Agent 풀 정의 (3~5종: iPhone, Android, Desktop Chrome 등)
2. Viewport 풀 정의 (390x844, 412x915, 1920x1080 등)
3. `new_context()` 호출 시 `random.choice()`로 조합 선택
4. `playwright-stealth` 라이브러리는 현재 API 호환성 문제로 **미도입** (기존 수동 스크립트 유지)

**이유**: 고정 UA/Viewport는 패턴 학습에 취약. 동적 변경으로 탐지 회피 가능성 향상.

---

## 4. 작업 순서 (원자적 단계)

| 단계 | 작업 | 파일 | 검증 |
|------|------|------|------|
| 1 | TargetClosedError 처리 + 브라우저 자동 재시작 | `tools.py` | 단위 테스트 또는 수동 재현 |
| 2 | 타임아웃 18초 + 환경변수 | `tools.py` | 기존 배치 실행 |
| 3 | page/context 명시적 close + 안전한 finally | `tools.py` | 메모리 프로파일링 |
| 4 | ERR_ABORTED 조기 실패 | `tools.py` | 악성 URL 테스트 |
| 5 | (선택) User-Agent/Viewport 동적 변경 | `tools.py` | 봇 방어 사이트 테스트 |

---

## 5. 예상 코드 변경 요약

### 5.1 tools.py - scrape_url() 변경 포인트

```python
# TargetClosedError: Playwright 공개 API에 없음. 에러 메시지로 판별 권장.
# 예: "Target page, context or browser has been closed" in str(e)

# scrape_url 내부
for attempt in range(3):  # 2 → 3
    try:
        await self.start()
        async with self._semaphore:
            context = await self.browser.new_context(...)
            try:
                page = await context.new_page()
                # ...
                timeout_ms = int(os.getenv("SCRAPE_NAVIGATION_TIMEOUT", "18000"))
                response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # ...
            finally:
                try:
                    if page and not page.is_closed():
                        await page.close()
                except Exception:
                    pass
                try:
                    await context.close()
                except (TargetClosedError, Exception):
                    pass
    except Exception as e:
        err_str = str(e).lower()
        # TargetClosedError: 브라우저 재시작 후 재시도
        if "target page" in err_str or "context or browser has been closed" in err_str or "targetclosed" in err_str:
            logger.warning(f"[PlaywrightManager] TargetClosedError: {e}. Restarting browser...")
            await self.stop()
            continue  # 다음 attempt에서 새 브라우저로 재시도
        # ERR_ABORTED: 즉시 실패 반환 (재시도 무의미)
        if "err_aborted" in err_str or "net::err_aborted" in err_str:
            result["error"] = "ERR_ABORTED (Blocked)"
            result["status"] = "error"
            return result
        # Timeout, 기타 오류
        if "timeout" in err_str and "page.goto" in err_str:
            result["error"] = "Timeout (Bot Protection?)"
            result["status"] = "timeout"
        else:
            result["error"] = str(e)
            result["status"] = "error"
```

---

## 6. 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SCRAPE_NAVIGATION_TIMEOUT` | 18000 | `page.goto()` 타임아웃 (ms) |
| `MAX_BROWSER_CONCURRENCY` | 10 | (기존) 동시 브라우저 컨텍스트 수 |

---

## 7. Phase 4: 강제 종료 처리 (배치 정지 시)

### 7.1 문제

- **증상**: 스팸 source text 로드 후 중간에 강제 종료(Ctrl+C 또는 UI 취소)해도 프로세스가 종료되지 않음
- **원인**:
  1. `asyncio.gather(*tasks)`에 타임아웃 없음 → 한 태스크가 `page.goto` 등에서 멈추면 전체가 무한 대기
  2. 취소 확인(`manager.is_cancelled`)이 세마포어 획득 전/후에만 있음 → `process_single_item` 내부 장시간 작업 중에는 확인 안 함
  3. 배치가 `run_in_executor`의 별도 스레드에서 실행 → Ctrl+C(SIGINT)가 해당 스레드로 전달되지 않을 수 있음

### 7.2 해결 방안

| 방안 | 설명 |
|------|------|
| **Per-task timeout** | `process_single_item`을 `asyncio.wait_for(..., timeout=300)`으로 감싸서, 한 항목이 5분 이상 멈추면 TimeoutError로 조기 종료 후 다음 항목 계속 |
| **취소 모니터** | 5초마다 `manager.is_cancelled(client_id)` 확인. 취소 시 모든 미완료 태스크 `task.cancel()` 후 `CancellationException` 발생 |
| **Ctrl+C 전파** | `SIGINT` 핸들러에서 전역 `shutdown_requested` 설정. 취소 모니터에서 함께 확인 → 배치 조기 종료 |
| **CancellationException 재전파** | `excel_handler.flush_batch`에서 `CancellationException`을 잡지 않고 재전파하여 상위에서 처리 |

### 7.3 구현 상태

| 항목 | 상태 | 파일 |
|------|------|------|
| Per-task timeout (300s) | 구현 | `main.py` |
| 취소 모니터 (5초 주기) | 구현 | `main.py` |
| SIGINT → shutdown_requested | 구현 | `main.py` |
| CancellationException 재전파 | 구현 | `excel_handler.py` |

---

## 8. 승인 요청

Vibe Coding 지침에 따라 **코드 수정 전 명시적 승인**을 요청합니다.

- **Phase 1** (TargetClosedError + 브라우저 재시작): 필수
- **Phase 2** (타임아웃 18초 + page/context 정리 + ERR_ABORTED): 필수
- **Phase 3** (User-Agent/Viewport 동적 변경): 선택
- **Phase 4** (강제 종료 처리): 필수

승인해 주시면 Phase 1 → Phase 2 순으로 원자적 단계로 구현하겠습니다.
