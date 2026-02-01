# PRD: Spam RAG Reference Usage Specification

| Property | Value |
| :--- | :--- |
| **Version** | v1.2 (Implementation Update - Deduplication & Validator) |
| **Status** | Active |
| **Audience** | VibeCoding Agent / Internal Dev |
| **Scope** | ContentAnalysisAgent + SpamRagService + SpamValidator |

---

## 1. 목적 (Purpose)

본 문서는 ChromaDB 기반 **SpamRagService**를 개선하여, 단순 "문장 유사도"가 아닌 **"의도 유사도(Intent Similarity)"** 기반의 **참조 시스템(Reference System)**으로 재정의한다.

### 1.1 핵심 원칙
1.  **Intent Over Syntax**: 메시지 원문이 아닌 **"판정 의도 요약(Judgement Semantic Unit)"**을 임베딩한다.
2.  **No Decision Authority**: RAG는 단독으로 SPAM/HAM을 결정하지 않는다.
3.  **Dedicated Validator**: **SpamValidator** 에이전트가 중복을 차단하고 데이터 품질을 관리한다.
4.  **Meta-centric Storage**: 원본 메시지와 세부 판정 근거는 모두 Metadata로 이관한다.

---

## 2. 시스템 전제 (System Assumptions)

### 2.1 저장 데이터 구조 (Schema)
*   **Infrastructure**: ChromaDB
*   **Embedding Target (Document)**:
    *   `judgement_semantic_unit`: 의도 요약 중심 텍스트 (예: "불법 대출 광고 / 상담 유도"). **메시지 원문 아님.**
*   **Metadata Schema**:
    *   `original_message`: 메시지 원문 (필수)
    *   `label`: SPAM (필수)
    *   `classification_code`: 분류 코드
    *   `reason`: 판정 사유
    *   `source`: 등록 출처 (예: `web_ui`, `auto_batch`)
    *   `created_at`: 생성 일시

> [!IMPORTANT]
> **저장 금지 대상**: 불확실한 판정, 오타/노이즈, 단순 의심 사례는 절대 저장하지 않는다.

### 2.2 중복 방지 전략 (Deduplication Strategy)
데이터 품질 유지를 위해 2단계 중복 검사를 수행합니다.
1.  **Exact Match**: 원본 메시지(`original_message`)의 해시값을 비교하여 완전 일치 차단.
2.  **Semantic Check**: 거리가 매우 가까운(유사도 > 0.95) 데이터 존재 시 차단.

---

## 3. RAG Reference Output Contract

SpamRagService는 다음 구조의 데이터를 반환해야 한다.

```json
{
  "metric": "cosine_distance",
  "query_summary": "입력 메시지의 의도 요약문",
  "hits": [
    {
      "id": "rag_xxxx",
      "summary": "저장된 의도 요약문",
      "original_message": "원본 메시지 Full Text",
      "label": "SPAM",
      "distance": 0.12,
      "metadata": { ... }
    }
  ]
}
```

---

## 4. RAG Similarity Strength Levels

거리(Distance)는 **"의도 구조의 유사성"**을 의미한다.

| Level | Condition | Meaning |
| :--- | :--- | :--- |
| **STRONG** | `d1 < 0.10` AND `spam_count >= 2` | 의도 구조가 거의 동일 (Strong Intent Match) |
| **MID** | `d1 < 0.20` | 유사한 의도 패턴 존재 (Potential Intent Match) |
| **WEAK** | 그 외 | 다른 의도 또는 단순 키워드 매칭 |

> [!WARNING]
> **Level이 STRONG이어도 단독 판정 근거로 사용 금지.** 반드시 `harm_anchor` 검증을 거쳐야 함.

---

## 5. SpamValidator 에이전트

새로 도입된 `SpamValidator`는 RAG 데이터베이스의 게이트키퍼(Gatekeeper) 역할을 수행합니다.

### 5.1 역할
*   **데이터 검증**: 등록 요청된 메시지가 스팸 예제로 적합한지 검토.
*   **중복 차단**: 기존 DB와 비교하여 중복 데이터 저장 방지 (409 Conflict 반환).
*   **자동 요약**: 메시지 원문에서 핵심 의도(`judgement_semantic_unit`)를 추출하여 임베딩 품질 향상.

---

## 6. LLM 프롬프트 필수 가이드

프롬프트에는 다음 지침이 포함되어야 한다:
*   "RAG 검색 결과는 **과거의 유사 의도 사례**일 뿐이다."
*   "판단은 반드시 **현재 메시지의 문맥**을 기준으로 `harm_anchor`를 분석하여 수행하라."
*   "유사 사례가 있어도 `harm_anchor=false`라면 HAM이다."

