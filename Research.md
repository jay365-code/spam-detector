# 입력 파일 시스템 내 URL 분석 및 추출 로직 딥다이브

본 문서는 스팸 탐지 파이프라인(`UrlAnalysisAgent`, `ContentAnalysisAgent`, `Batch Flow`)에서 URL을 어떻게 추출, 검증하고 프론트엔드에 "입력 URL 분석" 및 "본문 추출 URL" 형태로 전달하는지에 대한 상세 코드 분석 결과를 담고 있습니다.

---

## 1. 개요 및 파이프라인 (Pipeline Overview)

입력된 스팸 메시지의 URL 분석은 크게 두 가지 트랙으로 나뉩니다.
1. **미리 정제되어 입력된 URL (Pre-parsed URL)**: KISA 텍스트 파일 등에서 메시지와 함께 탭(Tab) 등으로 분류되어 입력된 URL. 파이프라인 상 `pre_parsed_urls`로 취급되며, 프론트에서는 **"입력 URL 분석"** 으로 렌더링됩니다.
2. **본문 내 탐지 URL (Body Extracted URL)**: 입력 필드에 URL이 없거나, 의도적으로 파손된 경우 메시지 본문을 정규표현식 및 디코딩 기법을 통해 긁어낸 결과입니다. 이는 프론트엔드에서 **"본문 추출 URL"** 로 표기됩니다.

---

## 2. '입력 URL 분석' 로직 (Pre-parsed URL Logic)

해당 로직은 원본 소스 파일에서 파싱되어 명시적으로 전달된 URL에 대한 스크래핑과 판독 과정, 그리고 보존 및 출력 로직을 관리합니다.

### 2.1 데이터 전달 및 식별
- **백엔드 (`batch_flow.py`)**: `aggregator_node`의 라인 346 부근에서 `final["pre_parsed_url"] = state.get("pre_parsed_url")`를 통해 KISA 원본의 URL 파라미터를 보존합니다.
- **프론트엔드 (`frontend/src/App.tsx`)**: 
  - 라인 1920 부근에서 `log.result.pre_parsed_url`의 존재 유무를 확인. 
  - 있을 경우 `입력 URL 분석`이라는 라벨을 표시. (없을 경우 본문 강제 추출 경로 분석, 단건 테스트인 경우 AI 자체 추출 URL로 표기 변경 됨).

### 2.2 파손된 단축 URL 사전 포착 및 예외 필터
- `batch_flow.py`의 `url_node` (라인 121~148): 
  - 전달받은 `pre_parsed_url`이 주요 단축 URL(`bit.ly`, `buly.kr`, `vo.la` 등)에 해당할 경우 URL 형식을 검증합니다.
  - 슬래시('/') 뒤의 도메인 경로가 없거나(예: `bit.ly/ `), 괄호/별표/한글 등 파손 문자가 섞인 경우 KISA의 파싱 오류로 판정합니다.
  - 이 경우 `pre_parsed_url`을 버리고, 원문에서 전체를 다시 찾는 **본문 추출 모드로 강제 전환(`pre_parsed_url_invalidated = True`)** 합니다.

### 2.3 [핵심] "입력 URL 분석"에 "본문 추출 URL"이 섞여 나오는 원인 분석
사용자님께서 지적하신 **`입력 URL 분석` 필드에 입력 URL(예: `tinyurl.com`)뿐만 아니라 본문에서 추출된 `hwaljuro.com`, `casino.com` 등이 섞여 노출되는 현상**은 아래와 같은 아키텍처 상의 합병(Merge) 로직 때문입니다.

1. **추출 단계의 의도적 합병 (Backend - `nodes.py`)**:
   - `extract_node` (라인 484~535)에서 `pre_parsed_urls` (입력 URL)가 존재할 경우 이를 우선적으로 파싱합니다.
   - 그러나 함수를 조기 종료(return)하지 않고, **"밑의 본문 추출 로직까지 타게 해서 합치도록 변경!"** 이라는 주석과 함께 하단의 본문 추출 코드 블록을 그대로 실행합니다. 
   - 이로 인해 원본 텍스트 안에 존재하는 모든 URL (입력에 명시되지 않은 숨겨진 URL이나 Content Agent가 복원한 난독화 URL 포함)이 `unique_urls` 로 통합됩니다.

2. **접속 기록의 누적 (Backend - `URL Agent`)**:
   - URL Agent는 합쳐진 수많은 `target_urls` (입력 제공 URL + 본문 추출 URL의 병합본)들을 대상으로 스크래핑을 시도합니다.
   - 이때 실제 접속 시도를 한 모든 도메인의 이력이 `attempted_urls` 라는 배열에 차곡차곡 쌓이게 됩니다.

3. **프론트엔드 라벨링의 오해 (Frontend - `App.tsx`)**:
   - 프론트엔드 (라인 1920 부근)는 단순히 KISA 데이터로부터 전달받은 **`log.result.pre_parsed_url` 파라미터가 존재하기만 하면 무조건 타이틀을 "입력 URL 분석"으로 결정**해 버립니다.
   - 그런데 정작 그 옆에 렌더링하여 보여주는 데이터는 `log.result.url_result.details.attempted_urls` 입니다.
   - 즉, 타이틀은 "입력 URL 데이터"라고 쓰여있지만, 실제 출력되는 리스트는 **입력 URL 필드와 본문 전수 검사에서 발견된 모든 URL에 대한 총 스크래핑 시도 기록**이기 때문에 나타나는 현상입니다.

---

## 3. '본문 추출 URL' 로직 (Message Extracted URL Logic)

입력 URL이 없거나 위 과정을 통해 무효화되었을 때, 또는 함께 병합하여 탐색할 때 사용되는 URL 난독화 해제 및 추출 코어 로직입니다. 

### 3.1 Content Agent의 난독화 디코딩
- **`content_context` 병합**: Content Agent (의도 분석 LLM)가 난독화 해제 중 발견한 `obfuscated_urls` 결과물은 `batch_flow`를 거쳐 URL Agent로 넘어와 본문 필터링에서 취합됩니다.

### 3.2 URL Agent 추출 노드 (`url_agent/nodes.py` -> `extract_node`)
라인 484 ~ 794 내부에서 매우 강력한 여러 단계의 정규화 및 난독화 해제를 수행합니다.
1. **한글 도메인 (Punycode) 변환**: `convert_korean_domain_to_punycode`를 통해 한글 문자열이 들어간 도메인을 `xn--` 형태의 국제화 도메인(IDN)으로 변환합니다.
2. **NFKC 정규화 및 공백 제거 (Spaceless Filter)**: 
  - 띄어쓰기 난독화(`b i t . l y / 1 2 3`)를 무력화하기 위해 모든 공백을 없앤 `spaceless_message`를 만든 후 프로토콜 정규식을 다시 태웁니다.
3. **가비지 컬렉션 및 Back-Gluing 방어**:
  - `path_cleaned_urls` 로직 (라인 697~): URL 꼬리 부분에 구두점이나 한글이 붙어 파손되는 현상 (예: `http://youtube.../abc2차상담`) 수정. 한글, 번호 매기기를 분리.
  - 단축 주소 뒤의 쓰레기 특수 문자열을 잘라냅니다.
4. **허용 TLD 및 단독 도메인 검열**: `COMMON_TLDS` 화이트리스트를 사용해 영문 TLD 존재 여부 등을 보수적으로 감시합니다. 숫자로만 된 도메인은 오타로 판단해 버립니다.
5. **정렬 및 제한**: 쇼핑몰, 기업사이트 등 일반 도메인을 먼저 검증(우선순위)하고 UGC/단축 주소를 후순위로 미뤄 성능 최적화를 합니다. (최대 추출 개수 3개 등 제한 옵션 존재)

### 3.3 환각(Hallucination) 방어 검증 로직 (`batch_flow.py` -> `aggregator_node`)
URL Agent와 Content Agent에서 발견한 URL들이 **진짜 본문에 존재하는가**를 교차 검증합니다.
- **`is_url_in_message` 함수** (라인 367~405): 원본(raw), 디코딩문(decoded), 띄어쓰기 삭제본 등 3가지 버전을 모두 뒤져서, 해당 URL의 도메인 파트가 실제 텍스트에 포함되어있는지 입증합니다. (아이피 형태 정규식(`\d{1,3}(\.\d{1,3}){3}`)을 가짜 IP로 배제)
- **병합 (`final["message_extracted_url"]`)** (라인 573): 환각을 걸러내고 살아남은 최후의 URL들을 `valid_extracted_urls`에 넣은 뒤, 쉼표로 연결하여 프론트엔드의 "본문 추출 URL" 데이터 소스로 전달합니다.

---

## 4. 최종 프론트엔드 연동 뷰 (UI State Resolution)

`frontend/src/App.tsx` 내에서 분석 결과를 화면에 렌더링 할때 다음을 만족하는 경우에만 표시를 합니다.
- **"입력 URL 분석"**: 전달된 KISA 입력 데이터(`log.result.pre_parsed_url`)가 존재할 때 `url_result.details.extracted_url` 및 접속된 모든 `final_url` 이력을 표시합니다.
- **"본문 추출 URL"**: 파이프라인에서 환각 검사 등을 거쳐 최종 입증된  `log.result.message_extracted_url` 이 공백이 아닐 경우 표기되며, 원본 추출물에 대한 `target_blank` 하이퍼링크가 함께 렌더링 됩니다. (라인 2004)

### 특수 상태 처리 (URL Drop)
- 원본에서 추출은 되었으나 판독 결과 **"Safe URL Injection(정상 돔/은닉 방패막이)"**, **"Bare Domain(단독 도메인 사칭)"** 등 오탐지가 유력할 경우, 엑셀 및 UI 표기를 하지 않도록 `drop_url = True` 플래그를 할당합니다.
- 위의 2.3 현상에 비추어 볼 때, "입력 URL 분석"이라는 렌더링 라벨 표기 자체가 실질적인 동작(합병 스크래핑) 결과를 대표하기엔 다소 모호성을 띄고 있습니다. 이를 명확히 인지할 수 있도록 "전체 분석 시도 URL" 등으로 라벨링을 변경하거나 분리하는 리팩토링이 권장됩니다.
