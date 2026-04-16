# SMS 본문 내 다중 URL 처리 분석 보고서 (Research)

이 보고서는 스팸 탐지 시스템이 SMS 본문 내에 여러 개의 URL이 존재할 경우 이를 추출하고 순회하며 분석하는 전체 사이클을 분석한 결과입니다.

## 1. 개요
스팸 탐지 시스템은 **LangGraph** 기반의 `UrlAnalysisAgent` 내에서 워크플로우(`extract_node` -> `scrape_node` -> `analyze_node` -> `select_link_node`)를 통해 URL을 처리합니다. 다중 URL이 감지되면 한 번에 모든 URL을 병렬로 분석하는 대신, **순차적(순회)으로 악성 여부를 검사**하며 하나라도 SPAM으로 판정될 경우 즉시 분석을 종료하는 **"단락 평가(Short-circuit evaluation)"** 방식으로 설계되어 있습니다.

---

## 2. 상세 처리 파이프라인

### Phase 1: URL 추출 (`extract_node`)
`nodes.py`의 `extract_node`에서는 본문에서 탐지할 수 있는 모든 URL의 풀(pool)을 수집합니다. 

1. **소스 데이터 읽기:** 
   - 원문 메시지(`sms_content`), 난독화 해제된 텍스트(`decoded_text`), 그리고 Content Agent가 미리 복원해 둔 `obfuscated_urls` 등을 통합하여 분석 대상을 확보합니다.
2. **패턴 매칭:**
   - 정규표현식(`http/https://` 패턴 및 도메인 구조 패턴)을 통해 URL 후보를 식별합니다.
   - 단축 URL 쓰레기값 제거(Short URL Garbage cleaning) 및 한글 도메인/경로 분리 등 정제(Clean-up) 작업을 수행합니다.
   - 한글 도메인의 경우 `idna` 라이브러리를 사용해 퓨니코드(Punycode, `xn--...`)로 변환합니다.
3. **제한 및 타겟 선정 (`MAX_URLS_PER_MESSAGE`)**
   - 시스템 리소스 고갈을 막기 위해 추출된 고유 URL 집합을 순서대로 정렬한 뒤, 최대 처리 개수를 제한합니다. 기본적으로 환경변수 `MAX_URLS_PER_MESSAGE`가 적용되며 (기본값: 3개), `unique_urls[:max_urls]` 로 자릅니다.
   - 이렇게 구성된 URL 리스트를 상태(State)의 `target_urls` 배열에 저장하고, 순회 시작점을 위해 `current_url`을 첫 번째 URL로 설정합니다. (인덱스 `depth`는 0부터 시작)

---

### Phase 2: 스크래핑 (`scrape_node`)
현재 상태의 `current_url`에 PlaywrightManager를 이용해 직접 접속하여 랜딩 페이지의 콘텐츠(Title, Text, Screenshot 등)를 가져옵니다. 

---

### Phase 3: 분석 및 조기 종료 판단 (`analyze_node`)
1. **LLM 판단 로직:** 
   - 스크랩한 웹페이지 내용과 SMS 본문 내용을 Crosscheck 하도록 Prompt를 구성하고 LLM(Gemini 등)에 질의합니다. 
   - 일치 여부(Consistency), 유해성 여부 등을 따져 SPAM, HAM, 또는 Inconclusive(판단 불가) 여부를 도출합니다.
   - 텍스트 분석 결과가 Inconclusive일 경우 스크린샷 이미지를 활용하여 Vision API 기반 2차 분석을 추가 수행합니다.
2. **조기 종료 트리거 (Short-circuit):**
   - 만약 분석 결과가 **SPAM**으로 확정되면, LangGraph State의 `is_final`을 **True**로 변경합니다.
   - 한 링크라도 스팸 판정이 나면 다음 URL 분석으로 넘어갈 필요가 없으므로 그대로 그래프 흐름이 종류(END)됩니다.
   - HAM이거나 에러, 판불가인 경우 `is_final = False`로 유지하여 다음 단계로 넘깁니다.

---

### Phase 4: 다음 링크 탐색 (`select_link_node` 및 Edge 리라우팅)
해당 URL 분석 후 스팸 판정이 나지 않았다면(`is_final` == False), 다음 URL을 꺼내옵니다.

1. **상태 업데이트:**
   - 이전에 분석한 URL은 `visited_history`에 추가됩니다.
   - `target_urls` 중 방문하지 않은(Not in `visited_history`) 다음 URL을 찾아 `current_url`로 설정합니다.
2. **재귀 방지 장치 (Depth Limit):**
   - 현재 시도 횟수를 의미하는 `depth` 값을 1 증가시킵니다.
   - 라우터 로직(`router_logic`)에서 `depth`가 허용치(`max_depth`, 기본 2 이므로 총 3개의 URL을 0, 1, 2 단계에 걸쳐 탐색)에 도달했는지 검사합니다.
   - `max_depth`에 도달했거나 더 이상 깔 URL이 없으면 `is_final = True`로 플래그를 세우고 **HAM** 사유와 함께 전체 분석을 종료합니다.
3. **다음 URL 루프 돌기:**
   - 남은 URL이 있고 최대 깊이에 도달하지 않았다면, 제어 흐름은 그래프 상에서 다시 `scrape_node`로 점프하여 2번~4번 프로세스를 반복합니다.

---

## 3. 요약 및 요점 (결론)

- **선착순 3개 필터 적용:** 메시지 안에서 아무리 많은 URL이 있어도 시스템 오버헤드 방지를 위해 **최대 3개(max_depth 고려 시)**까지만 검사를 수행합니다.
- **순차적 검사 (Sequential):** 여러 개의 URL을 한꺼번에 LLM에 던지지 않고, URL 하나씩 꺼내어 Playwright로 접속 -> LLM 판단 과정을 거칩니다.
- **단락 평가 (Early Exit):** 검사하는 도중 어느 한 URL이라도 유해한(SPAM) 것으로 판단되면, 뒤에 남은 URL은 검사하지 않고 즉시 해당 메시지를 스팸으로 최종 확정합니다.
- **모두 안전해야 HAM:** 준비된 3개의 URL을 모두 접속하고 분석한 결과, 단 한 번도 SPAM 요소가 발견되지 않아야만 최종적으로 안전한 메시지(HAM)로 넘어갑니다.
