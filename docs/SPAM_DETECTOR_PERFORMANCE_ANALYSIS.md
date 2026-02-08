# Spam Detector 성능 분석 보고서

**작성일**: 2026-02-07  
**분석 대상**: 배치 처리 파이프라인, URL 분석 병목, 큐 로딩 전략

---

## 1. 현재 설정 요약

| 설정 | 값 | 설명 |
|------|-----|------|
| `LLM_BATCH_SIZE` | 50 | URL 없는 메시지 동시 처리 상한 |
| `MAX_BROWSER_CONCURRENCY` | 20 | URL 있는 메시지(Playwright) 동시 처리 상한 |
| `batch_chunk_size` | 1000 | excel_handler에서 한 번에 로드·처리하는 메시지 수 |

---

## 2. URL 세마포어 동작 확인

### 2.1 "20개가 다 끝나야 새로운 20개를 수행"하는가?

**결론: 아니요.** 세마포어는 **슬라이딩 윈도우** 방식으로 동작합니다.

- `asyncio.Semaphore(20)`은 **동시에 20개만** 실행 가능하다는 의미입니다.
- 하나가 끝나면 → 즉시 대기 중인 다음 태스크가 시작됩니다.
- 따라서 "20개 전부 끝날 때까지 기다린 뒤, 새 20개"가 아니라, **항상 최대 20개가 돌아가며 순차적으로 교체**됩니다.

```python
# main.py - sem_task 내부
async with selected_sem:  # acquire
    idx, res = await process_single_item(...)
    return idx, res       # release (완료 시)
```

### 2.2 세마포어 이중 구조

| 위치 | 변수 | 한계 | 역할 |
|------|------|------|------|
| `main.py` | `sem_browser` | 20 | URL 메시지 전체 처리(Content→URL→Aggregator) |
| `PlaywrightManager` | `_semaphore` | 20 | `scrape_url()` 내부(브라우저 컨텍스트·페이지 생성) |

두 세마포어 모두 `MAX_BROWSER_CONCURRENCY`로 설정되며, 효과적으로 동일한 병목을 만듭니다.

### 2.3 실제 병목 원인

Playwright URL 분석이 느린 이유는 세마포어가 아니라 **다음 요소들**입니다.

1. **페이지 로드 대기**: `page.goto()` 타임아웃 10초
2. **봇 방어 대기**: Cloudflare 등 최대 15초 대기
3. **네트워크 지연**: 외부 URL 접속 시간
4. **동시 브라우저 리소스**: 20개 컨텍스트/탭 동시 실행 시 메모리·CPU 사용

로그에서 `Scraping Timeout (likely bot protection)` 등이 반복되면, 병목은 **Playwright 작업 자체**에 있습니다.

---

## 3. 배치 큐 로딩 방식 분석

### 3.1 현재 동작 (1000개 청크)

```
[파일 로드] → rows (전체 메시지)
     ↓
[batch_buffer 1000개] → flush_batch() → process_message_with_hitl(1000개)
     ↓
asyncio.gather(1000개 태스크) → 모두 완료 대기
     ↓
[batch_buffer 500개] → flush_batch() → process_message_with_hitl(500개)  (1500개 파일 예시)
     ↓
완료
```

- `excel_handler.process_kisa_txt` / `process_file`:
  - 파일 전체를 `rows`로 먼저 로드
  - `batch_buffer`가 1000개가 되면 `flush_batch()` 호출
  - `flush_batch()`가 끝나야 다음 1000개를 처리

즉, **1차 배치 1000개가 모두 끝나야 2차 배치(나머지)가 시작**됩니다.

### 3.2 예시: 1500개 메시지 (URL 600, LLM-only 900)

| 구간 | 동작 |
|------|------|
| 1차 배치 (1000개) | URL 400 + LLM-only 600 → gather 실행 |
| 완료 조건 | 가장 느린 URL 400개가 전부 끝나야 1차 배치 완료 |
| 2차 배치 (500개) | 그 이후에 URL 200 + LLM-only 300 시작 |

따라서 2차 배치의 LLM-only 300개는, 1차 배치의 느린 URL 태스크들 때문에 **늦게 시작**하게 됩니다.

---

## 4. 전체 메시지를 큐에 올리는 방식 검토

### 4.1 제안 내용

- 현재: 1000개씩 나누어 처리
- 제안: 800~1500개 수준의 파일이면 **전체를 한 번에 큐에 올려 처리**

### 4.2 장점

1. **배치 경계 제거**: 1000개가 끝나기를 기다리지 않고, 세마포어로 자연스럽게 스로틀링
2. **부하 분산 개선**: 1차 배치 URL 태스크가 오래 걸려도, 2차 배치 LLM-only가 이미 대기열에 있어 즉시 진입
3. **구현 단순화**: `batch_chunk_size`만 조정하면 됨

### 4.3 고려 사항

| 항목 | 검토 |
|------|------|
| 메모리 | 1500개 메시지 텍스트는 수 MB 수준으로 부담 거의 없음 |
| 취소 | 세마포어/태스크 구조 유지 시 동일하게 동작 가능 |
| 진행률 | `asyncio.gather`로 스트리밍 유지 시 그대로 사용 가능 |
| 엑셀 저장 | 현재는 `flush_batch`마다 저장 → 전체 처리 시 한 번만 저장하거나, 별도 주기 저장 로직 추가 필요 |

### 4.4 권장 변경

**조건부 전체 로드** 방식:

- 메시지 수 ≤ 2,000: `batch_chunk_size = total_rows` (전체 한 번에 처리)
- 메시지 수 > 2,000: 기존처럼 `batch_chunk_size = 1000` 유지 (대용량 대비)

이렇게 하면 800~1500개 규모에서는 항상 전체가 한 번에 큐에 올라가고, 2000개 이상일 때만 청크 단위로 처리합니다.

---

## 5. 권장 개선 사항 요약

| 우선순위 | 항목 | 내용 |
|----------|------|------|
| 1 | 배치 크기 조정 | `batch_chunk_size = min(2000, total_rows)`로 전체 로드 적용 |
| 2 | URL 병목 완화 | Playwright 타임아웃·재시도 정책 검토 (현재 10초) |
| 3 | 세마포어 동작 | 현 구조 유지, 슬라이딩 윈도우로 이미 올바르게 동작 중 |
| 4 | 모니터링 | URL vs LLM-only 처리 비율, 평균 소요 시간 로깅 강화 |

---

## 6. 코드 변경 위치 참고

### 6.1 배치 크기 변경

- **파일**: `backend/app/main.py`
- **위치**: `batch_chunk_size = 1000` 설정 부분 (line 952 근처)
- **변경 예**:
  - TXT: `excel_handler.process_kisa_txt` 호출 전에 `total_rows`를 알 수 있다면 `batch_chunk_size = min(2000, total_rows)` 사용
  - Excel: `process_file` 호출 시 `total_rows`를 반영한 `batch_size` 전달

### 6.2 PlaywrightManager 세마포어

- **파일**: `backend/app/agents/url_agent/tools.py`
- **위치**: `PlaywrightManager.start()` 내 `self._semaphore = asyncio.Semaphore(max_concurrency)`
- **환경변수**: `MAX_BROWSER_CONCURRENCY`로 이미 제어 중
