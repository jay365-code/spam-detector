# Red Group 처리 로직 상세 분석

> **분석 기준 파일**
> - `backend/app/graphs/batch_flow.py` (L344 ~ L865)
> - `backend/app/utils/excel_handler.py` (전체)
> - `frontend/src/App.tsx` (red_group 관련 구간)

---

## 1. Red Group이란?

**Red Group**은 "텍스트 본문은 정상(HAM)이지만, 첨부된 URL이 악성(SPAM)으로 판정된" 메시지를 별도로 분류하는 특수 그룹입니다.

- **엑셀 시각 표현**: 핑크색(`FFCCCC`) 배경 강조
- **구분 컬럼**: 빈칸 (일반 SPAM의 `"o"`와 달리 공란 유지)
- **통계 카운트**: 스팸 개수(`spam_count`)에는 합산됨
- **목적**: 텍스트-URL 이분리 탐지를 명시적으로 관리자에게 알리기 위한 경보 체계

---

## 2. 전체 데이터 흐름 (Pipeline)

```
[Input KISA TXT / Excel]
        │
        ▼
  content_node  ──────→ (텍스트 의도 분석 / HAM or SPAM)
        │
        ▼ (router: has_url=True → url_node 진입)
   url_node     ──────→ (URL 접속 스크래핑 / 악성 여부 판정)
        │
        ▼ (url_to_ibse_router)
  [ibse_node]   ──────→ (시그니처 추출 - 조건부 지연 호출)
        │
        ▼
 aggregator_node ──────→ ★ Red Group 판정 ★
        │
        ▼
   final_result  ──────→ Excel / JSON Report / Frontend UI
```

---

## 3. `aggregator_node` - Red Group 판정 핵심 로직

### 파일: `batch_flow.py` L487~L515

```python
# Red Group (붉은색 채우기) 발동 여부 검사
# [수정] Red Group 판정 및 URL 스팸 통째로 덮어쓰기는
#        KISA 원본(입력 파라미터)에 URL 필드가 명시적으로
#        존재할 때만 발동
has_input_url = (
    bool(state.get("pre_parsed_url"))
    and not u_res.get("pre_parsed_url_invalidated")
)

force_red_group = False

# Case 1: 완전 정상 텍스트 + 악성 단검(URL)
if has_input_url and is_pure_content_ham and url_is_spam:
    # [수정] 텍스트가 정상(배송 등)이고 URL도 그에 연관된
    #        정상적인 상거래(성인용품점 등)라면 면책 발동.
    if u_res.get("is_consistently_transactional") == True:
        force_red_group = False
        url_is_spam = False  # 방어: SPAM으로 넘어가지 않도록 변경
        final["reason"] = (
            f"{existing_reason} | "
            "[정보성/거래성 완전 일치: 면책특권 발동되어 URL 정상(HAM) 처리]"
        )
    else:
        force_red_group = True  # ← Red Group 트리거
```

### 발동 조건 (3가지 모두 만족 시)

| 조건 | 변수 | 설명 |
|------|------|------|
| ① KISA 입력 URL 존재 | `has_input_url` | `pre_parsed_url` 필드가 있고 파손되지 않음 |
| ② 텍스트 본문이 HAM | `is_pure_content_ham` | `content_node` 판정 결과 `is_spam=False` |
| ③ URL이 SPAM | `url_is_spam` | `url_node` 판정 결과 `is_spam=True` |

### 면책 예외 (Red Group 미발동)

| 예외 조건 | 설명 |
|-----------|------|
| `is_consistently_transactional == True` | URL Agent가 "본문과 URL이 상거래 맥락에서 완전히 일치한다"고 판단한 경우 → HAM으로 처리 |

---

## 4. Red Group 발동 후 플래그 설정

### 파일: `batch_flow.py` L509~L515

```python
if force_red_group:
    # 붉은색 채우기 그룹 특수 처리 로직 (단순 URL 스팸 처리)
    final["is_spam"] = True                   # 최종 판정은 SPAM
    final["reason"] = (
        f"{existing_reason} | "
        f"[텍스트 HAM + 악성 URL 분리 감지: "
        f"단순 URL 스팸 격리 ({url_reason[:30]})]"
    )
    final["malicious_url_extracted"] = True   # URL 추출 성공 마커
    final["url_spam_code"] = url_code          # URL Agent의 분류 코드
    final["red_group"] = True                  # ★ Red Group 명시 플래그 ★
```

### 설정되는 `final` 딕셔너리 키 목록

| 키 | 값 | 의미 |
|----|-----|------|
| `is_spam` | `True` | 전체 판정을 SPAM으로 격상 |
| `reason` | `"...[텍스트 HAM + 악성 URL 분리 감지...]"` | 판정 근거 텍스트 (UI/엑셀에 표시) |
| `malicious_url_extracted` | `True` | 악성 URL이 본문에서 발견되었음을 표시 |
| `url_spam_code` | URL Agent 분류 코드 | URL 분류 코드 보존 |
| `red_group` | `True` | **Red Group 핵심 플래그** (엑셀/UI 표현에 사용) |

---

## 5. `is_separated` vs `red_group` 의 관계

```python
# batch_flow.py L740
is_separated = "[텍스트 HAM + 악성 URL 분리 감지" in str(final.get("reason", ""))
```

| 변수 | 판단 방식 | 취약점 |
|------|----------|--------|
| `is_separated` | `reason` 문자열 파싱 | 텍스트 변경 시 오탐 가능 (레거시) |
| `red_group` | boolean 플래그 직접 확인 | 신뢰성 높음 (현재 주력 방식) |

> **주의**: `excel_handler.py`의 정렬/서식 로직은 두 변수를 **OR** 조건으로 모두 체크합니다.
> `is_separated or is_red_group` → 둘 중 하나만 `True`여도 Red Group 처리됩니다.
> 이는 구형 JSON 리포트(플래그 없음) 호환을 위한 이중 안전장치입니다.

---

## 6. drop_url과 Red Group의 상호작용

### 파일: `batch_flow.py` L764~L770

```python
# 단독 도메인 URL 처리 시 Red Group 여부에 따른 예외
if all_are_bare_or_corrupt:
    # 명백히 스팸으로 판정된 증거이거나 데드링크라면 예외적으로 보존
    if (final.get("red_group") or final.get("is_spam")
            or final.get("malicious_url_extracted") or is_dead_domain):
        pass  # URL 유지
    else:
        final["drop_url"] = True
        final["drop_url_reason"] = "bare_or_corrupt_domain_sync"
```

> **Red Group의 URL 보존 특권**: 단독 도메인이나 파손된 URL이라도 `red_group=True`이면 엑셀 URL 컬럼에서 강제 삭제(drop_url)하지 않고 보존합니다.

---

## 7. `excel_handler.py` - 엑셀 출력 처리

### 7-1. KISA TXT 처리 (`process_kisa_txt`) - L1172~L1180

```python
is_red_group = bool(result.get("red_group"))
if is_separated or is_red_group:
    # 구분 열: "빈칸" 유지 (일반 스팸의 "o"와 다름)
    gubun_val = ""
    # 통계 카운트는 스팸과 동일하게 합산
    stats["spam_count"] += 1
    # 분류 코드는 URL Agent 코드 사용
    raw_code = str(result.get("classification_code", ""))
    match = re.search(r'\d+', raw_code)
    code_val = match.group(0) if match else raw_code
```

### 7-2. 엑셀 행 쓰기 - L1265~L1276

```python
ws.append([
    msg_val,          # 메시지
    url_val,          # URL
    gubun_val,        # 구분 ("" for Red Group)
    code_val,         # 분류 코드
    msg_len,
    url_len,
    "O" if result.get("flagged") else "",   # 검토필요
    prob_val,
    semantic_val,
    reason_val,
    "O" if result.get("red_group") else ""  # ← Red Group 컬럼 = "O"
])
```

### 7-3. URL 중복제거 시트 수집 조건 - L1290

```python
# Red Group도 URL을 중복제거 시트에 등재 (악성 URL 차단 목적)
if (result.get("is_spam") is True
        or result.get("malicious_url_extracted")
        or result.get("red_group")        # ← Red Group 포함!
   ) and not result.get("drop_url"):
    # URL 수집 → unique_urls 또는 unique_short_urls
```

### 7-4. IBSE 시그니처 수집 조건 - L1337

```python
# Red Group도 시그니처 추출 대상 포함
if result.get("is_spam") or result.get("red_group"):
    if result.get("ibse_signature") and ...:
        blocklist_data.append({...})
```

---

## 8. `excel_handler.py` - 정렬 로직 (`_sort_sheet_by_type`)

### 파일: `excel_handler.py` L248~L274

```python
def rank_key(row):
    # [Fix] Red Group 판단: Reason 텍스트 대신
    #        Red Group 컬럼 값('O')으로 직접 확인
    is_red_group = (
        safe_get(row, red_col_idx).upper() == "O"
        if red_col_idx else False
    )
    is_separated = "[텍스트 HAM + 악성 URL 분리 감지" in reason_val

    # 색상/그룹 우대 순위:
    # 0: 일반 SPAM (황금색 - 최상단)
    # 1: Red Group + 분리 감지 (핑크색 - 스팸 바로 하단)
    # 2: HAM (투명)
    if is_separated or is_red_group:
        return 1   # Red Group: 스팸 바로 아래 배치
    elif is_type_a or is_type_b or is_spam:
        return 0   # 일반 SPAM: 최상단
    elif semantic_val.lower() == "ham":
        return 2   # HAM: 하단
```

### 정렬 최종 순서

```
① 일반 SPAM (rank=0) - 황금색 (FFF2CC)
   ├── URL 있음 → URL 없음 순
② Red Group (rank=1) - 핑크색 (FFCCCC)
   ├── URL 있음 → URL 없음 순
③ HAM (rank=2) - 배경 없음
```

---

## 9. `excel_handler.py` - 셀 서식 (`_apply_formatting`)

### 파일: `excel_handler.py` L429~L444

```python
red_col = get_col_idx("Red Group")
is_red_group = (
    ws.cell(row=row_idx, column=red_col).value == "O"
) if red_col else False

cell = ws.cell(row=row_idx, column=msg_col)
if is_separated or is_red_group:
    # 핑크색 배경 적용
    type_b_fill = PatternFill(
        start_color="FFCCCC",
        end_color="FFCCCC",
        fill_type="solid"
    )
    cell.fill = type_b_fill
elif gubun_val == "o" or is_type_b:
    # 황금색 배경 (일반 SPAM)
    cell.fill = spam_fill  # FFF2CC
```

---

## 10. Frontend (`App.tsx`) - Red Group UI 처리

### 10-1. 타입 정의 - L180

```typescript
type EditingLog = {
  ...
  red_group?: boolean;
  ...
}
```

### 10-2. 편집 모달 열기 시 기존 상태 복원 - L219

```typescript
// [Fix] 기존 Red Group 상태 복원:
//        모달 열 때 항상 false로 초기화하던 버그 수정
red_group: log.result.red_group || false,
```

### 10-3. Red Group 수동 토글 - L2166~L2173

```typescript
const isTurningOn = !editingLog.red_group;
// ... (reason 텍스트 업데이트)
setEditingLog({
  ...editingLog,
  red_group: isTurningOn,
  reason: newReason
});
```

### 10-4. 저장 시 drop_url 자동 해제 - L333~L334

```typescript
// [Fix] 수동 Red Group 지정 시, AI가 설정한 drop_url 플래그를
//        해제하여 URL이 엑셀에 표시되도록 함.
// 사용자가 Red Group을 수동으로 지정한다는 것은
// "이 URL은 악성이다"는 명시적 의사 표현이므로
// AI의 URL 제거 결정을 무시하고 drop_url을 false로 오버라이드
...(editingLog.drop_url !== undefined
  ? { drop_url: editingLog.red_group ? false : editingLog.drop_url }
  : {}),
...(editingLog.drop_url_reason !== undefined
  ? { drop_url_reason: editingLog.red_group ? null : editingLog.drop_url_reason }
  : {})
```

### 10-5. URL 본문 추출 버튼 비활성화 - L2310~L2312

```typescript
// Red Group으로 지정된 경우 본문 추출 버튼 잠금
disabled={isUrlExtracting || editingLog.red_group}
title={editingLog.red_group
  ? "Red Group은 본문 추출이 금지됩니다."
  : ""}
```

### 10-6. 필터 및 카운터 - L1196, L1204

```typescript
// Red Group 건수 카운팅
const redGroupCount = displayLogs.filter(
  ({ log }) => log?.result?.red_group
).length;

// RED_GROUP 필터 적용
if (logFilter === 'RED_GROUP'
    && (!log.result || !log.result.red_group)) return false;
```

---

## 11. 전체 Red Group 플래그 생명주기 요약

| 단계 | 위치 | 동작 |
|------|------|------|
| 1. 탐지 | `batch_flow.py` aggregator_node | `content=HAM` + `url=SPAM` + `has_input_url` → `force_red_group=True` |
| 2. 플래그 설정 | `batch_flow.py` L509~L515 | `red_group=True`, `is_spam=True`, `malicious_url_extracted=True` |
| 3. URL 보존 | `batch_flow.py` L764~L770 | `drop_url` 강제 방지 |
| 4. 엑셀 행 쓰기 | `excel_handler.py` L1173~L1180 | 구분="", Red Group 컬럼="O" |
| 5. URL 수집 | `excel_handler.py` L1290 | 중복제거 시트에 URL 등재 |
| 6. 정렬 | `excel_handler.py` `_sort_sheet_by_type` | rank=1 (SPAM 바로 아래) |
| 7. 서식 | `excel_handler.py` `_apply_formatting` | 핑크색(FFCCCC) 배경 |
| 8. UI 복원 | `App.tsx` L219 | 모달 오픈 시 기존 red_group 상태 복원 |
| 9. 수동 오버라이드 | `App.tsx` L2166~L2173 | 사용자가 직접 토글 가능 |
| 10. drop_url 해제 | `App.tsx` L333~L334 | Red Group 지정 시 drop_url 자동 해제 |

---

## 12. 알려진 주의사항 / 잠재적 이슈 (업데이트됨)

### ✅ [해결됨] 이슈 1: `is_separated` 문자열 의존성 잔존

**과거 상황:**
`batch_flow.py`와 `excel_handler.py` 여러 곳에서 `is_separated = "[텍스트 HAM + 악성 URL 분리 감지" in reason_val`와 같이 문자열 파싱을 통해 Red Group을 이중으로 판별했습니다. 이로 인해 UI에서 수동으로 일반 스팸 전환(red_group: false)을 하더라도, `reason` 문자열에 해당 문구가 남아있으면 백엔드가 엑셀 작성 시 강제로 Red Group(핑크색)으로 덮어씌우는 버그가 발생했습니다.

**해결 조치 (2026-04-22):**
백엔드 `excel_handler.py`에서 **모든 `is_separated` 텍스트 기반 판별 로직을 일괄 삭제**했습니다.
이제 엑셀 정렬 및 서식 생성 시 오직 `is_red_group = bool(result.get("red_group"))` 플래그 단 하나만을 확인합니다. 이를 통해 JSON에 저장된 `red_group` 불리언 값이 진정한 단일 원천(Single Source of Truth)으로 동작하게 되었습니다.

### 이슈 2: Red Group vs 일반 SPAM 분류 코드 차이

Red Group의 분류 코드(`classification_code`)는 URL Agent가 반환한 `url_spam_code`에서 가져옵니다. Content Agent 코드가 아님에 주의하세요. `classification_code`가 비어있으면 `url_spam_code` → 없으면 `"0"`으로 폴백합니다.

### 이슈 3: 수동 Red Group 지정 시 URL 보존

사용자가 UI에서 Red Group 버튼을 켜면, `drop_url=false`로 강제 오버라이드되어 엑셀 URL 컬럼에 URL이 반드시 표시됩니다. AI가 "URL을 버려야 한다"고 판단했더라도 사용자의 명시적 의사가 우선합니다.

