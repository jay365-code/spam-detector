# [PRD] 지능형 스팸 URL 심층 분석 시스템 (ISAA)

**프로젝트 명:** ISAA (Intelligent Spam URL Advanced Analysis)  
**작성일:** 2026. 01. 04  
**핵심 프레임워크:** LangGraph, LangChain, Playwright, Gemini 3 Flash

---

## 1. 프로젝트 개요 (Overview)
KISA(한국인터넷진흥원)의 스팸 의심 메시지 배치 데이터를 기반으로, 메시지 내 URL의 최종 목적지를 추적하고 콘텐츠를 심층 분석하여 스팸 여부를 판별하는 자율형 AI 에이전트 시스템을 구축한다.

## 2. 주요 목표 (Project Goals)
- **단축 URL 완전 해제:** 리디렉션 체인을 끝까지 추적하여 실제 랜딩 페이지 확보.
- **재귀적 심층 탐색:** 첫 페이지에서 정보가 부족할 경우, AI가 판단하여 하위 링크를 탐색하는 자율적 판단 로직 구현.
- **대규모 배치 처리:** Google Anti-gravity 환경을 활용한 병렬 처리로 대량의 KISA 데이터를 안정적으로 분석.

## 3. 기능 요구사항 (Functional Requirements)

### 3.1 URL 전처리 및 추적
- SMS 텍스트 본문에서 정규표현식을 통해 모든 URL을 추출한다.
- 중복 URL은 제거한다.
- 단축 URL(bit.ly, t.co 등)은 HTTP Header 추적 및 Meta Refresh 파싱을 통해 최종 목적지 URL로 변환한다.

### 3.2 LangGraph 기반 자율 분석 워크플로우
- **상태 관리(State):** 수집된 텍스트, 이미지, 탐색 경로, 현재 탐색 깊이를 상태값으로 유지한다.
- **동적 스크래핑:** Playwright를 활용하여 자바스크립트 렌더링이 필요한 동적 페이지를 캡처(텍스트 및 스크린샷)한다.
- **단계적 탐색:** - LLM이 현재 페이지 정보를 분석하여 `[SPAM / HAM / UNKNOWN]` 판정을 내린다.
    - `UNKNOWN`일 경우, 페이지 내에서 가장 의심스러운 하위 링크를 추출하여 다시 탐색 노드로 진입한다.
    - 최대 탐색 깊이(Max Depth)에 도달하면 분석을 종료하고 결과를 요약한다.

### 3.3 결과 분류 및 저장
- 스팸 유형(도박, 피싱, 스미싱, 허위광고 등)을 세부 분류한다.
- 분석 근거(Reasoning)와 함께 증거 데이터(페이지 소스, 스크린샷 경로)를 저장한다.

## 4. 기술 스택 (Technical Stack)

| 구분 | 기술 요소 | 상세 용도 |
| :--- | :--- | :--- |
| **Infra** | **Google Anti-gravity** | 고성능 연산 및 확장형 배치 처리 환경 |
| **Orchestration** | **LangGraph** | 상태 기반 순환형 에이전트 워크플로우 제어 |
| **Agent Framework**| **LangChain** | LLM 도구 호출 및 프롬프트 관리 |
| **LLM** | **Gemini 1.5 Pro** | 텍스트/이미지 멀티모달 분석 및 추론 |
| **Scraping** | **Playwright** | 동적 웹 렌더링 및 샌드박스 브라우징 |
| **Storage** | **Google Cloud Storage** | 배치 파일 및 분석 결과 리포트 저장 |

## 5. 아키텍처 설계 (Architecture)

### 5.1 LangGraph 노드 구조


1. **`Extract_Node`**: SMS 본문 내 URL 추출 및 리디렉션 해제.
2. **`Scrape_Node`**: Playwright를 이용한 HTML/스크린샷 수집.
3. **`Analyze_Node`**: Gemini가 수집 데이터를 기반으로 스팸 여부 판단.
4. **`Router_Node`**: 
   - 판정 완료 시 -> `End`
   - 판정 불가(`UNKNOWN`) 시 -> `Select_Link_Node` (단, Depth < Max_Depth 일 때)
5. **`Select_Link_Node`**: 분석이 필요한 최적의 하위 링크 선정 후 `Scrape_Node`로 회귀.

### 5.2 데이터 스키마 (Agent State)
```python
from typing import List, TypedDict

class SpamState(TypedDict):
    sms_content: str
    target_urls: List[str]
    current_url: str
    visited_history: List[str]
    scraped_data: dict
    depth: int
    max_depth: int
    is_final: bool
    final_report: dict