# 스팸 시그니처 추출 로직 상세 분석 (IBSE Agent)

이 문서는 코어 텍스트 기반 스팸 필터링을 담당하는 **IBSE(Intelligence Blocking Signature Extractor)** 에이전트의 스팸 시그니처 추출 로직을 분석한 리서치 문서입니다. 

---

## 1. 개요 및 핵심 설계 사상
IBSE 에이전트는 이미 스팸으로 분별된 문장 내에서, 오탐 확률이 0%에 수렴하는 **"매우 고유한(Unique) 문자열 조합"**을 추출하는 것을 목표로 합니다.
추출 과정은 크게 LLM에 의한 의사결정(Selector), Python 단의 CP949 바이트 패딩 및 방어 선(Guardrails), 최종 엄격한 검토(Validator), 그리고 상위 파이프라인(Batch Flow) 내 캐시 및 병합 로직으로 나뉘어 구성되어 있습니다.

## 2. LLM 가이드라인 및 우선순위 (Prompt)
- **파일**: `backend/data/signature_spam_guide.md`
- **핵심 목표**: 오직 "유니크(Unique)함" 만을 기반으로 추출. 기괴한 은어나 형태소, 고유 단축 URL, 특수 연락처 위주로 타게팅.
- **길이 조건 (Byte 단위, CP949 인코딩 기준)**
  1. `use_string` (문자열): **9 ~ 20 bytes**. (가장 강력한 은어나 단축 주소가 있을 때)
  2. `use_sentence` (단문): **39 ~ 40 bytes**. (특수 기호가 없이 일반 텍스트 위주일 때)
  3. _그 외의 경우 21~38바이트 구역은 시스템상 존재하지 않으며 절대 금지됨._
  4. 도저히 유니크하게 추출 불가능하면 `{"decision": "unextractable"}` 로 포기.

## 3. 추출 프로세스 및 파이썬 로직 (Selector)
- **파일**: `backend/app/agents/ibse_agent/selector.py`

### 3.1. LLM 추출 추론 (Fallback 적용)
- `LLMSelector.select()` 함수에서 메인 모델 (예: GPT-4o)을 호출하여 JSON 출력을 유도합니다.
- **[Fallback 엔진]** 메인 모델이 "unextractable(추출 불가)"을 선언해도 포기하지 않고, 곧바로 서브 모델(예: Gemini-3.1 등 설정된 모델)로 넘겨서 집착스럽게 2차 시그니처 추출을 강제합니다 (`_use_fallback = True`).

### 3.2. CP949 바이트 기반 2차 방어망 메커니즘
LLM이 문자열을 추론하고 나면, 파이썬 코드가 한글 인코딩 깨짐(Mojibake)이나 바이트 길이 규정 이탈을 방지하기 위해 정교하게 문자들을 확장 및 절단(Truncate)합니다.

- **자동 승격 방어망**: LLM이 `use_string` (최대 20바이트) 구역으로 판결했지만, 텍스트가 20바이트를 넘어버린 경우 강제로 `use_sentence` (40바이트) 등급으로 자동 승격시켜 패딩 기회를 부여합니다.
- **Dead Zone 방어 (Use Sentence 패딩)**: `use_sentence` 판별 시 39바이트보다 부족할 경우, 원문(`match_text`)에서 좌우로 한 글자씩 윈도우를 확장하여(Expand String Window) 정확히 39~40 바이트에 도달하도록 덧붙입니다. 그래도 39바이트 도달에 실패 시 `use_string`(20바이트 이하)으로 강제로 강등하여 룰을 지킵니다.
- **윈도우 절단 방식 보호**: 보존해야 하는 URL(obfuscated URLs 포함)이 시그니처 중앙에 끼어있을 때 무작정 잘라버리지 않게 먼저 URL을 보호하고, 양옆으로 한 글자씩만 덧붙이면서 바이트를 측정(`encoded = sig_text.encode("cp949")`)하여 무손실 절단을 달성합니다.

## 4. 엄격한 검증기 (Validator)
- **파일**: `backend/app/agents/ibse_agent/validator.py`

추출된 시그니처는 하위 4개의 파이썬 단위 검증을 통과해야 합니다.
1. **정확한 일치 (No Hallucination)**: LLM이 지어낸 단어 혹은 조사가 들어갔는지 `signature not in text_context` 로 검열해 반려합니다.
2. **도메인 단독 추출 방지**: URL의 껍데기(루트 도메인, 예: naver.com)만 단독 추출했는지 정규식과 URL Parse로 추적합니다. (단, Path나 Query 파라미터가 있는 고유 단축 주소는 허용)
3. **블랙리스트 필터링**: "광고", "(광고)", "무료수신거부", "080-" 등 정상/법적 의무 키워드가 단 1바이트라도 혼입되면 즉시 실패 처리합니다.
4. **엄격한 길이 검증 (CP949 잣대)**: 각 Decision 타입에 맞춰 9, 20, 39, 40 바이트 조건을 통과하지 못하면 반려(`error`) 시킨 후, 이 에러 사유를 포함하여 다시 LLM 프롬프트로 재요청(Repair) 하도록 그래프가 동작합니다.

## 5. 파이프라인 통합 로직 (Batch Flow)
- **파일**: `backend/app/graphs/batch_flow.py`

### 5.1. 런타임 하이패스 및 DB 캐싱
`ibse_node` 호출에서 LLM 요청을 보내기 이전에 가장 먼저 캐시 검사를 실행합니다.
- **영구 DB (SQLite)**: 기존에 등재된 스팸 시그니처(`SignatureDBManager`) 중 현재 메시지("공백 제거 상태")에 매칭되는 문자열이 있으면 LLM 비용과 속도를 획기적으로 줄이며 즉시 반환시킵니다.
- **런타임 릴레이 (Batch Session) 캐시**: 해당 배치(Batch) 중 방금 다른 스레드가 생성한 시그니처가 이번 메시지에도 있다면(`BATCH_SIGNATURE_CACHE`) 바로 통과합니다.

### 5.2. 멀티 에이전트 정보 병합 (Aggregator - URL 중복 소거)
의존성 중첩 방지를 위해 URL 에이전트와 IBSE 에이전트 결과를 결합합니다.
- 추출된 유효 URL(`valid_extracted_urls`)이 정상적으로 존재하며 엑셀 출력에 기록될 예정일 경우, **IBSE 시그니처 변수 값을 강제로 `None` 처리**합니다(`"unextractable (URL Deduplication Active)"`). 이는 URL 차단만으로도 충분히 목적 달성이 가능하여, 불필요한 시그니처 남발과 필터 오염을 사전에 차단하기 위함입니다.
- 단, `preserve_signature_override` (URL 단독보다는 본문 맥락에 악의성이 깊어 시그니처를 우선시하는 경우) 로 지정된 건은 소거당하지 않고 보호됩니다.

---
**[결론 요약]**
현재 IBSE 모듈은 단순히 LLM의 언어 감각에 기대는 것을 넘어서, CP949 바이트 연산, 블랙리스트, 하이패스 캐시 통과, 그리고 URL 에이전트와의 상호배제(MutEx-like) 등 파이썬 단의 강력한 통제 로직으로 오탐률 0%를 지향하며 고도로 최적화되어 있습니다.
