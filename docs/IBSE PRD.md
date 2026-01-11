# IBSE (Intelligence Blocking Signature Extractor) — PRD

> 목적: **스팸으로 판정된 SMS**에서 실시간 차단 시스템(단순 문자열 포함 매칭)에 등록할 **차단 시그니처(signature)** 를 자동으로 선택/추출한다.  
> 본 PRD는 **URL/도메인/단축URL 처리(별도 파이프라인)** 를 *범위에서 제외*한다.

---

## 1. 배경 및 문제 정의

실시간 차단 시스템은 `message contains signature` 형태의 **단순 문자열 매칭**만 제공한다.  
운영자는 스팸 SMS 원문에서 **20바이트 또는 40바이트**(CP949 기준) 내의 “의미 있는” 연속 부분 문자열을 수작업으로 선별해 차단 등록한다.

수작업에는 주관이 개입되며 재현성이 낮다. IBSE는 다음을 자동화한다.

- 스팸 SMS 1건이 **문자열 시그니처 차단에 적합한지** 판단
- 적합하면 원문 내 연속 substring 형태로 **≤20 또는 ≤40 바이트** 시그니처를 선택/추출
- 부적합하면 `unextractable`로 안전 종료

---

## 2. 목표 (Goals)

1) 스팸 SMS에서 **단순 문자열 포함 매칭**으로 차단 가능한 시그니처를 자동 선택/추출  
2) 시그니처는 **CP949 바이트 기준**으로 **≤20 우선**, 불충분하면 **≤40** 사용  
3) 시그니처는 반드시 **원문(매칭 기준 텍스트) 내 연속 substring**  
4) 결과는 **기계 검증 가능(JSON)** 하며, 실패 시 **리페어(재요청) 1회**로 안정성 확보  

---

## 3. 범위 (Non-Goals)

- URL/도메인/단축URL 탐지/차단/등록 로직은 **별도 시스템**에서 처리하며, IBSE에서는 고려하지 않는다.
- 실시간 차단 엔진(매칭 엔진) 자체 구현은 범위 제외.
- 유사도 매칭, 정규식 매칭, 토큰화 기반 매칭 등 고급 매칭은 범위 제외(향후 확장 과제).

---

## 4. 핵심 제약 (Hard Constraints)

- **연속 substring**: 시그니처는 `match_text[start:end]`로만 생성/검증 가능해야 한다.
- **바이트 길이**: `len(signature.encode("cp949")) <= 20` 또는 `<= 40`
- **인덱스 제공**: `start_idx`, `end_idx_exclusive`(문자 인덱스, Python slicing 기준)
- **URL 고려 금지**: URL 관련 앵커/태그/후보 생성/판단을 포함하지 않는다.
- **LLM은 "선택" 역할**: LLM은 후보 목록에서만 선택한다(후보 외 생성/변형 금지).

---

## 5. 용어 정의

- **match_text**: 매칭 기준 텍스트. 원문에서 전처리된 문자열로, 차단 시스템이 매칭에 사용하는 대상.
- **signature**: 차단 등록용 문자열(연속 substring, CP949 바이트 제한).
- **candidate**: 비LLM 단계에서 생성한 signature 후보(20/40 바이트 그룹).
- **anchor_tags**: 후보의 의미/특이성을 설명하는 태그(이 PRD에서 URL 태그는 사용하지 않음).

---

## 6. 전처리 정책 (match_text 정의)

### 6.1 권장 기본값
- `match_text = NFKC 정규화 + 모든 공백 제거`

> 이유: 스팸은 공백/전각/조합문자 등을 활용해 우회를 시도한다.  
> 전처리를 match 기준으로 고정하면 substring 추출/검증/차단 일관성이 올라간다.

### 6.2 CP949 인코딩 불가 문자 정책(필수 결정)
- **권장**: 후보 생성 시 `cp949` 인코딩 불가 문자가 포함된 후보는 **제외**
- 대안(비권장): `errors="replace"`는 바이트 길이/매칭 일관성 왜곡 가능성이 있음

---

## 7. 시스템 개요(고수준 아키텍처)

IBSE는 2단계로 구성된다.

1) **FR-2: 후보 생성 (비LLM)**  
   - 입력: `match_text`  
   - 출력: `candidates_20[]`, `candidates_40[]` (각 Top-K)  
   - 보장: 연속 substring + CP949 바이트 제한 + 인덱스 제공

2) **FR-3: 후보 선택/판단 (LLM: Antigravity)**  
   - 입력: 원문(match_text) + 후보 리스트  
   - 출력: `use_20` / `use_40` / `unextractable` + 선택 후보 메타 + risk/reason

---

## 8. 기능 요구사항 (Functional Requirements)

### FR-1. 입력/출력
- 입력: `message_id`, `sms_text` (원문)  
- 전처리 후 `match_text` 생성
- 출력: 표준 JSON(아래 스키마)

### FR-2. Candidate Generation (비LLM)

#### FR-2.1 후보 조건(필수)
모든 candidate는 아래를 만족해야 한다.

- `candidate.text == match_text[candidate.start_idx:candidate.end_idx_exclusive]`
- `candidate.byte_len_cp949 = len(candidate.text.encode("cp949"))`
- `candidate.byte_len_cp949 <= 20` (20 후보) 또는 `<= 40` (40 후보)
- `start_idx`, `end_idx_exclusive`는 문자 인덱스(슬라이싱 기준)

#### FR-2.2 앵커(Anchor) 정의 (URL 제외)
후보 점수화/태깅에 사용하는 앵커 태그:

- `PHONE`: 전화번호 패턴(휴대폰/유선 등)
- `OPT_OUT`: 무료거부/수신거부/거부번호/080 등
- `AD_MARK`: (광고) 등 광고 표기
- `OBFUSCATION`: ●◀▶, 분리형 자모, 특수문자 삽입 등 난독화
- `CODE`: 영문+숫자 혼합 토큰/식별자
- `SENSITIVE_KEYWORD`: 대출/코인/도박/성인/시급/지급/이벤트/추천번호/참여/상담/카톡유도 등
- `BRAND`: 상호/서비스명/고유명 추정(룰 기반)

#### FR-2.3 후보 생성 방식(권장 v2)
- (A) **슬라이딩 윈도우 후보 풀** 생성  
  - start를 step(1~2)로 이동하며, end를 “바이트 상한(20/40)”에 최대 근접하도록 확장
- (B) 후보 점수화(scoring) 후 Top-K 유지  
  - 가점: OPT_OUT, PHONE, AD_MARK, OBFUSCATION, CODE, SENSITIVE_KEYWORD, BRAND
  - 감점: 일반 인사/덕담/감사/일상 안내 중심 구간(오탐 위험)
- (C) 앵커 주변 **prefix/suffix/center** 후보 보강  
  - 특정 앵커가 존재할 경우 앵커 주변에서 “의미 밀도 높은 구간” 후보를 추가 생성
- (D) 중복 제거  
  - 동일 `text`는 최고 점수 1개만 유지(필요 시 start/end도 함께 기록)

#### FR-2.4 후보 개수(초기값)
- `candidates_20`: Top **80**
- `candidates_40`: Top **120**

> 메시지 길이에 따라 동적으로 조정 가능. 토큰 절감을 위해 후보 텍스트는 짧게 유지하며 중복 제거를 강하게 적용한다.

---

### FR-3. LLM Selection

#### FR-3.1 LLM의 역할
- 후보 목록 중 최적 1개 선택 또는 `unextractable` 판정
- **후보 외 문자열 생성 금지**
- 20 우선, 부족하면 40, 오탐 위험 크면 unextractable

#### FR-3.2 출력 JSON 스키마(표준)
```json
{
  "message_id": "string",
  "decision": "use_20 | use_40 | unextractable",
  "chosen_candidate_id": "string",
  "signature": "string",
  "byte_len_cp949": 0,
  "start_idx": 0,
  "end_idx_exclusive": 0,
  "risk": "low | medium | high",
  "reason": "string"
}
```

---

## 9. 서버 검증(필수) 및 오류 처리

### 9.1 검증 항목
- 포함 검증: `signature == match_text[start_idx:end_idx_exclusive]`
- 존재 검증: `signature in match_text`
- 바이트 검증:
  - decision=`use_20` → `byte_len_cp949 <= 20`
  - decision=`use_40` → `byte_len_cp949 <= 40`
- 인덱스 경계 검증: 0 ≤ start < end ≤ len(match_text)

### 9.2 리페어(재요청) 정책
- 검증 실패 시 1회에 한해 “리페어 프롬프트”로 재요청
- 재요청도 실패하면:
  - 차선 후보(서버 규칙) 선택 또는
  - `unextractable`로 안전 종료(권장)

---

## 10. 중복 제거 및 등록 정책

- 등록 저장소에서는 `signature` 단위 중복 제거(동일 signature 중복 등록 방지)
- 선택적으로 내부 dedup용 `normalized_key`를 운용할 수 있으나, **매칭은 match_text 기준 signature만** 사용한다.

---

## 11. 수용 기준(Acceptance Criteria)

1) 모든 입력 메시지에 대해 결과는 반드시 하나의 JSON 객체로 반환된다.  
2) `decision`이 `use_20/use_40`인 경우:
   - signature는 match_text의 연속 substring이며 서버 검증을 통과한다.
   - CP949 바이트 제한을 준수한다.
3) 검증 실패 시 리페어 1회로 복구하거나 안전 종료한다.
4) URL 관련 로직/태그/판단이 포함되지 않는다.

---

## 12. vibecoding용

아래 내용은 Antigravity에 등 vibecoding 환경에서 바로 요청하기 위한 “고정 프롬프트/페이로드”이다.

### 12.1 SYSTEM PROMPT
```text
너는 IBSE(Intelligence Blocking Signature Extractor)의 판단 엔진이다.
목표는 스팸 메시지를 실시간 단순 문자열 포함 매칭으로 차단할 수 있는 시그니처를 고르는 것이다.

중요 제약:
- 시그니처는 반드시 후보 목록에서만 선택한다. 후보 밖의 문자열을 새로 만들거나 변형/정규화/요약하지 않는다.
- 후보는 match_text에서 잘라낸 연속 substring이며, CP949 바이트 길이가 제공된다.
- 20바이트 이하 후보로 충분히 특이하고 스팸 앵커가 있으면 use_20을 선택한다.
- 20바이트로는 일반적이거나 오탐 위험이 크면 40바이트 이하 후보 중 선택(use_40).
- 40바이트에서도 일반 문구 중심이거나 오탐 위험이 크면 unextractable을 선택한다.

가점 앵커:
OPT_OUT(무료거부/수신거부/080 등), AD_MARK((광고)), PHONE(전화 패턴),
OBFUSCATION(난독화), CODE(영문+숫자), SENSITIVE_KEYWORD(대출/도박/코인/시급/지급/이벤트/추천번호/참여/상담/카톡유도), BRAND(고유명)

감점:
감사/인사/덕담/일상 안내처럼 일반 메시지에서도 흔한 구간

반드시 JSON 단일 객체만 출력한다. 추가 텍스트 금지.
```

### 12.2 USER PROMPT 템플릿
```text
message_id: {{message_id}}
match_text: {{match_text}}

candidates_20: [
  {"id":"c20_1","text":"...","byte_len_cp949":19,"start_idx":12,"end_idx_exclusive":25,"anchor_tags":["OPT_OUT","PHONE"]},
  {"id":"c20_2","text":"...","byte_len_cp949":20,"start_idx":40,"end_idx_exclusive":52,"anchor_tags":["OBFUSCATION"]}
]

candidates_40: [
  {"id":"c40_1","text":"...","byte_len_cp949":39,"start_idx":8,"end_idx_exclusive":34,"anchor_tags":["AD_MARK","OPT_OUT"]},
  {"id":"c40_2","text":"...","byte_len_cp949":40,"start_idx":60,"end_idx_exclusive":98,"anchor_tags":["SENSITIVE_KEYWORD"]}
]

출력(JSON):
{
  "message_id":"{{message_id}}",
  "decision":"use_20" | "use_40" | "unextractable",
  "chosen_candidate_id":"...",
  "signature":"...",
  "byte_len_cp949":0,
  "start_idx":0,
  "end_idx_exclusive":0,
  "risk":"low" | "medium" | "high",
  "reason":"한 줄 근거(특이성/앵커/오탐위험)"
}
```

### 12.3 vibecoding용 단일 페이로드 예시(JSON)
> 모델명은 환경에 맞게 변경한다.

```json
{
  "model": "llm_model_name",
  "input": [
    { "role": "system", "content": "<SYSTEM PROMPT 전문>" },
    { "role": "user", "content": "<USER PROMPT 템플릿에 값 채운 내용>" }
  ],
  "response_format": { "type": "json_object" }
}
```

### 12.4 리페어(검증 실패 시)용 SYSTEM/USER (선택)
- 검증 실패 시 1회 재요청에 사용한다.

**REPAIR SYSTEM**
```text
이전 출력이 검증에 실패했다.
후보 목록에서만 다시 선택해라. 반드시 JSON 단일 객체로만 출력해라.
signature는 match_text[start:end]와 일치해야 하며 CP949 바이트 제한을 준수해야 한다.
```

**REPAIR USER**
```text
검증 실패 사유: {{error_reason}}

이전 출력: {{previous_output_json}}

동일 입력:
message_id: {{message_id}}
match_text: {{match_text}}
candidates_20: {{candidates_20}}
candidates_40: {{candidates_40}}

위 조건을 만족하는 JSON만 다시 출력해라.
```

---

## 13. 구현 체크리스트 (MVP)

- [ ] match_text 전처리(NFKC + 공백 제거) 구현 및 고정
- [ ] CP949 바이트 계산 함수 및 인코딩 불가 문자 정책 적용
- [ ] FR-2 후보 생성(v2: 슬라이딩+점수+TopK+중복제거) 구현
- [ ] llm 호출(시스템/유저 프롬프트) 연결
- [ ] 서버 검증(포함/바이트/인덱스) + 리페어 1회
- [ ] 최종 결과 JSON 로그 및 등록 저장소 dedup
- [ ] 운영 파라미터(TopK, step, 점수 가중치) 설정화

---

## 14. 오픈 이슈 / 결정 필요 사항

1) CP949 인코딩 불가 문자 처리 정책(제외 vs 대체) 확정
    - 제외
2) 일반 문구(오탐 유발) 감점 리스트(Stop-signature) 초안 확정
    - 결정 원칙
        Stop-signature는 “스팸이 아닌 정상(햄)에서도 흔히 나오는 문구”를 걸러 오탐을 줄이는 장치입니다.
        초안은 완벽할 필요가 없고, 운영하면서 업데이트합니다.
    - 권장 기본값(초기 배포)
        방식은 2단계가 안정적입니다.
    (A) 강한 배제(하드 블록)
        * 후보가 아래 문구들로만 구성되거나 대부분이 이 계열이면 후보 점수를 크게 깎거나 제외:
            - 감사/인사/덕담: 감사, 고맙, 안녕, 좋은 하루, 수고, 건강, 행복, 새해, 연말, 명절, 축하
            - 일정/안내 상투어: 확인, 문의, 연락, 답장, 회신, 안내
        * 단, 다음 앵커가 함께 있으면 예외로 둡니다:
            - OPT_OUT, PHONE, AD_MARK, OBFUSCATION, CODE, SENSITIVE_KEYWORD
            - 예: “감사합니다 무료거부 080…”는 스팸 앵커가 명확하므로 후보 유지
    (B) 점수 감점(소프트 블록)
        * 위 단어가 포함되면 GENERIC_SCORE 감점 누적

    확정 절차(권장)
    1. 스팸 샘플 500~2,000건 + 정상 샘플 500~2,000건 준비(마스킹 가능)
    2. 후보 추출 후, 정상 메시지에서도 자주 등장하는 후보를 자동 식별
    3. 그 상위 50~200개를 Stop 리스트로 확정(운영 업데이트 가능)

3) 후보 점수 가중치(앵커별 가점/감점) 초기값 확정
    - 권장 초기 가중치
        OPT_OUT: +8
        PHONE: +7
        AD_MARK: +6
        OBFUSCATION: +6
        CODE: +5
        SENSITIVE_KEYWORD: +5
        BRAND: +3
        GENERIC_PHRASE: -4 (Stop-signature 계열 단어 1개당)
        TOO_SHORT: -3 (cp949 바이트가 너무 짧음: 예 ≤8)
        ALL_DIGITS: -2 (숫자만 있는 후보는 오탐 가능성으로 감점, 단 PHONE이면 예외)
    - Top-K 권장
        candidates_20: 80
        candidates_40: 120
        초기에는 K를 넉넉히 두고, 비용/토큰 부담이 커지면 줄입니다.
