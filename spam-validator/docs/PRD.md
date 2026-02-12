# PRD.md  
## 엑셀 기반 스팸 분류 결과 일치도 검증 툴  
*(사람 육안 결과 vs LLM 자동 결과 / 분류 컬럼은 이진 스팸 여부: `o` = 스팸, 그 외 = 햄)*

---

## 1. 문서 목적 (Purpose)

본 문서는 **사람이 육안으로 판단한 스팸 여부**와 **LLM이 자동으로 판단한 스팸 여부**가  
얼마나 **일치하는지 정량적으로 검증**하고,  
판단이 다른 메시지를 **Diff UI**로 검토할 수 있는 **경량 검증 툴**의 요구사항을 정의한다.

본 툴은 **성능 검증 및 품질 확인**을 목적으로 하며,  
분류 수정, 재분류(LLM 호출), 학습 기능은 포함하지 않는다.

---

## 2. 핵심 용어 및 규칙 (Critical Definitions)

### 2.1 분류 컬럼 정의 (Binary Spam Indicator)

`분류` 컬럼은 **스팸 여부를 나타내는 이진 판단 컬럼**이다.  
아래 규칙만을 단일 기준으로 사용한다.

"o" → Spam  
그 외 모든 값 → Ham  

빈 값, 공백, `x`, 기타 문자열 등 `"o"`가 아니면 모두 햄으로 간주한다.

### 2.2 평가 기준 정의

Human.xlsx 결과 = Ground Truth (정답)  
LLM.xlsx 결과   = Prediction (비교 대상)

---

## 3. 문제 정의 (Problem Statement)

사람과 LLM이 동일 메시지에 대해  
스팸/햄 판단을 얼마나 동일하게 했는지 빠르게 확인하기 어렵다.

운영 관점에서 특히 중요한 오류 유형은 다음과 같다.

FN: 사람은 스팸인데 LLM은 햄 (스팸 놓침)  
FP: 사람은 햄인데 LLM은 스팸 (오탐)

엑셀을 직접 열어 대조하는 방식은 시간이 오래 걸리고 누락 위험이 크다.

---

## 4. 목표 (Goals)

1. 사람 기준으로 LLM 스팸 판단이 얼마나 일치하는지 수치로 제공  
2. **총 스팸 갯수 비교**와 **스팸 일치율**을 핵심 KPI로 제공  
3. FN / FP 중심의 Diff 리스트 제공  
4. 메시지 클릭 시 원문과 양쪽 분류 결과를 즉시 확인 가능  

---

## 5. 범위 (Scope)

### In Scope
- 엑셀 파일 2개 업로드
- 지정 시트에서 메시지/분류 컬럼 로드
- 메시지 기준 매칭 후 스팸/햄 판단 비교
- Summary 지표 + Diff UI 제공

### Out of Scope
- 분류 수정 및 저장
- 재분류(LLM 호출)
- 다중 클래스 분류
- 다중 시트 비교
- 사용자 인증/권한 관리

---

## 6. 입력 데이터 정의 (Input Specification)

입력 파일:
- Human.xlsx : 사람이 육안으로 분류한 결과
- LLM.xlsx   : LLM이 자동으로 분류한 결과

대상 시트:
- 육안분석(시뮬결과35_150)

필수 컬럼:
- 메시지 : 비교 기준 메시지 원문
- 분류   : 스팸 여부 (`o`면 스팸)

예외 처리:
- 시트 없음 → 비교 중단
- 필수 컬럼 없음 → 비교 중단
- 메시지 값이 비어 있는 행 → 제외

---

## 7. 비교 로직 (Comparison Logic)

### 7.1 메시지 정규화 (Message Normalization)

normalized_message = normalize(메시지)

정규화 규칙:
- 앞뒤 공백 제거
- 연속 공백 → 단일 공백
- 줄바꿈(\n, \r\n) → 공백
- 유니코드 정규화(NFKC)

---

### 7.2 분류 정규화 (Label Normalization)

is_spam = (trim(lower(분류)) == "o")

정규화 결과 해석:
- "o", "O", "o " → True (Spam)
- "", "x", null, 기타 문자열 → False (Ham)

본 규칙은 **모든 비교·지표·Diff 판단의 단일 기준**이다.

---

### 7.3 행 매칭 (Row Matching)

메시지는 중복될 수 있으므로 **출현 순서 기반 occurrence index**를 포함한다.

match_key = (normalized_message, occurrence_index)

매칭 절차:
1. normalized_message 기준 그룹핑
2. 그룹 내 등장 순서대로 occurrence_index 부여
3. match_key 기준으로 1:1 매칭

---

### 7.4 Diff 판단 조건

human_is_spam != llm_is_spam → Diff 발생

---

## 8. 평가 지표 (Evaluation Metrics)

### Confusion Matrix (Spam = Positive)

TP: Human=Spam, LLM=Spam  
FN: Human=Spam, LLM=Ham  
FP: Human=Ham,  LLM=Spam  
TN: Human=Ham,  LLM=Ham  

---

### 핵심 지표 정의

Human Spam Count = count(human_is_spam == true)  
LLM Spam Count   = count(llm_is_spam == true)  
Spam Count Delta = LLM Spam Count - Human Spam Count  

Spam Agreement Rate = TP / (TP + FN)  
= TP / Human Spam Count  

Overall Agreement Rate = (TP + TN) / Matched Message Count  

FN Count = 사람이 스팸이라 판단했으나 LLM이 햄  
FP Count = 사람이 햄이라 판단했으나 LLM이 스팸  

지표 우선순위:
1. Spam Agreement Rate  
2. Spam Count + Delta  
3. FN / FP 절대 건수  
4. Overall Agreement Rate  

---

## 9. Diff 출력 정의 (Diff Output)

Diff Type:
- FN : 사람=스팸, LLM=햄
- FP : 사람=햄, LLM=스팸

Diff 필드:
- diff_id
- diff_type
- message_preview
- message_full
- human_label_raw
- llm_label_raw
- human_is_spam
- llm_is_spam
- match_key
- row_meta

---

## 10. UI 요구사항 (UI Requirements)

사용자 플로우:
1. 엑셀 2개 업로드
2. Compare 실행
3. Summary 지표 확인
4. FN / FP Diff 리스트 검토
5. 메시지 클릭 → 상세 패널 확인

화면 구성:
- Upload: 파일 업로드 + Compare 버튼
- Results: Summary KPI / Diff 리스트 / Diff 상세 패널

---

## 11. 기술 요구사항 (Technical Requirements)

Backend:
- FastAPI (Python)
- pandas + openpyxl

Frontend:
- React 또는 Next.js

성능:
- 1,000 ~ 50,000 row 처리 가능
- O(n) 매칭 로직
- 동일 입력 + 동일 규칙 → 항상 동일 결과

---

## 12. 결과 데이터 스키마 (Response Example)

{
  "summary": {
    "human_spam_count": 88,
    "llm_spam_count": 86,
    "spam_count_delta": -2,
    "spam_agreement_rate": 0.93,
    "overall_agreement_rate": 0.92,
    "tp": 82,
    "fn": 6,
    "fp": 4,
    "tn": 58
  },
  "diffs": [
    {
      "diff_type": "FN",
      "message_full": "...",
      "human_is_spam": true,
      "llm_is_spam": false
    }
  ]
}

---

## 13. 성공 기준 (Success Criteria)

- 사람 대비 LLM 스팸 판단 일치도를 즉시 이해 가능
- FN / FP 메시지를 엑셀 없이 검토 가능
- 회의·보고용 지표로 바로 사용 가능

---

## 14. 한 줄 요약

사람의 스팸 판단을 기준으로  
LLM 결과가 얼마나 동일한지를  
총 스팸 갯수, 스팸 일치율, Diff 리스트로 검증하는 도구
