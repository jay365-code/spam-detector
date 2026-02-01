# ChromaDB 저장 방식 변경 지침 (RAG Reference 품질 개선)

본 문서는 SpamRagService가 사용하는 ChromaDB의 저장 방식을 개선하여  
RAG를 “문장 유사도 기반 검색”이 아닌 **“의도 유사도 기반 참조 시스템”**으로 동작시키기 위한
단일 변경 지침(Single Source of Truth)을 정의한다.

본 지침은 다음 전제를 변경하지 않는다.
- spam_guide.md는 항상 Full Context로 사용된다.
- RAG는 스팸 판정의 보조(reference) 수단이다.
- RAG는 SPAM/HAM 판정을 단독으로 결정하지 않는다.

---

## 1. 변경 목적 (Purpose)

현재 ChromaDB에는 메시지 원문 전체가 embedding 대상으로 저장되고 있다.  
이 방식은 다음과 같은 구조적 문제를 유발한다.

- 짧은 메시지·난독화 메시지가 과도하게 높은 유사도를 가짐
- 표현은 다르나 의도는 같은 스팸이 분산 저장됨
- 과거 사람 실수(FP)가 유사 메시지를 통해 전파될 위험 존재
- distance threshold(예: 0.15)의 의미가 불안정함

따라서 저장 단위를 **“메시지 문장”이 아닌 “판정 의미 단위”**로 변경한다.

---

## 2. 핵심 원칙 (Core Principles)

1. ChromaDB는 메시지를 기억하지 않는다.
2. ChromaDB는 판정된 의도 구조를 기억한다.
3. 벡터 검색은 문장 유사도가 아닌 **의도 유사도**를 비교한다.
4. 불확실한 판정은 절대 저장하지 않는다.

---

## 3. 저장 단위 정의 (Judgement Semantic Unit)

### 3.1 정의

Judgement Semantic Unit이란,  
사람이 해당 메시지를 SPAM으로 판정할 때 사용한  
**의도 구조와 판단 근거를 요약한 텍스트 단위**를 의미한다.

이는 메시지 원문과 동일하지 않으며,  
판정의 “이유”를 압축한 의미 표현이다.

---

## 4. Vector(Embedding) 저장 규칙

### 4.1 금지 사항 (기존 방식)

메시지 원문을 그대로 embedding 대상으로 저장하는 방식은 금지한다.

예:
무서류 개인돈 당일 지급 상담 주세요 010-xxxx

---

### 4.2 필수 방식 (변경 후)

Embedding 대상으로 저장되는 텍스트는 반드시  
**의도 요약 중심 텍스트**여야 한다.

권장 형식 1:
불법 대출 광고 / 개인 연락처로 상담 유도 / 무서류·당일 지급

권장 형식 2:
의도: 불법 금융  
패턴: 개인돈, 무서류, 당일 지급  
행위: 개인 연락처 상담 유도  

위 텍스트만 vector로 저장되며,  
메시지 원문은 embedding 대상이 아니다.

---

## 5. Metadata 저장 규칙

메시지 원문과 판정 세부 정보는 **모두 metadata로 저장**한다.

### 5.1 Metadata 예시

{
  "original_message": "무서류 개인돈 당일 지급 상담 주세요 010-xxxx",
  "label": "SPAM",
  "code": "3",
  "category": "불법 금융",
  "reason": "무서류·당일 지급을 미끼로 개인 연락처 상담 유도",
  "harm_anchor": true,
  "verified": true,
  "created_at": "2025-01-10T12:30:00"
}

---

### 5.2 필수 Metadata 필드

- original_message
- label
- code
- category
- reason
- harm_anchor
- verified
- created_at

---

## 6. 검색(Query) 시 처리 원칙

RAG 검색 시에도 입력 메시지를 그대로 embedding 하지 않는다.

### 6.1 검색 절차

1. 입력 메시지로부터 **즉석 판정 의미 요약 텍스트**를 생성한다.
2. 해당 요약 텍스트를 embedding 하여 ChromaDB를 검색한다.
3. 과거 저장된 Judgement Semantic Unit과 비교한다.

### 6.2 비교 구조

[입력 메시지의 추정 의도 요약]  
vs  
[과거 스팸의 판정 의미 요약]

이 비교는 문장 유사도가 아니라 **의도 구조 유사도**를 의미한다.

---

## 7. Distance 해석 기준

본 저장 방식을 사용할 경우 distance 값은 다음 의미를 가진다.

- distance < 0.10 : 의도 구조 거의 동일
- 0.10 ≤ distance < 0.20 : 동일 계열 가능성 높음
- distance ≥ 0.25 : 다른 의도

단일 임계값에 의존하지 않는다.

---

## 8. 운영 제한 사항 (Critical Rules)

다음 데이터는 **절대 ChromaDB에 저장하지 않는다**.

- 사람 판단이 확정되지 않은 메시지
- “의심스러워서 SPAM” 처리된 사례
- 오타·의미 불명·잡음 메시지
- HAM ↔ SPAM 논쟁이 있었던 케이스
- 임시 조치 또는 테스트용 데이터

RAG는 기억 시스템이므로,  
불확실한 데이터는 시스템 전체를 오염시킨다.

---

## 9. 최종 원칙 요약

ChromaDB에는 메시지를 저장하지 않는다.  
그 메시지를 스팸이라고 판단한 **이유의 요약만 저장한다.**
