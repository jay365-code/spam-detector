# Spam Guide 버전 관리

spam_guide.md 및 관련 agent.py의 변경 이력을 추적합니다.

---

## v1.6 - 의도 기반 판단 및 route_or_cta 완화 (2026-01-25)

### 핵심 변경: 의도 기반 판단

**spam_guide.md 변경**
- **2.1 SPAM 확정 조건** 수정
  - 기존: `harm_anchor=true AND route_or_cta=true` 필수
  - 변경: 
    - 의도 명확 (spam_probability ≥ 0.85): `harm_anchor=true`만으로 SPAM
    - 의도 애매 (spam_probability < 0.85): 기존대로 `route_or_cta=true` 필요

- **2.2 harm_anchor 판정 원칙** 강화
  - 특정 키워드 매칭 불필요 - LLM이 맥락에서 의도 추론 가능
  - 고도 난독화 자체가 회피 의도의 증거

- **4. route_or_cta 판정 원칙** 간소화
  - 의도 명확 시 route_or_cta 확인 생략
  - SMS 발신 자체가 회신 가능 채널이므로 별도 연락처 없어도 가능

- **5. CODE EVIDENCE RULES** 완화
  - 기존: 패턴 1개 이상 매칭 필수
  - 변경: 의도 명확하면 키워드 매칭 없이도 해당 코드 적용 가능

**content_agent/agent.py 변경**
- 프롬프트 Step 4 수정: spam_probability 기반 분기 추가
- `_parse_response` HARD GATE 로직 수정:
  - `spam_prob >= 0.85 AND harm_anchor=true` → SPAM (route_or_cta 무시)
  - `spam_prob < 0.85 AND harm_anchor=true AND route_or_cta=false` → HAM

### 이유
- "벳삼삼" 같은 명백한 도박 스팸이 route_or_cta=false로 HAM 처리되던 문제 해결
- 모든 SMS는 회신 가능하므로 route_or_cta 조건이 사실상 무의미
- LLM의 의도 파악 능력을 활용하여 키워드 나열 방식 탈피

---

## URL Agent 무한 루프 수정 (2026-01-25)

### 문제
- `GRAPH_RECURSION_LIMIT` 에러 발생 (25회 초과)
- `select_link` → `scrape` 무조건 edge로 인한 무한 순환

### 수정
**url_agent/agent.py**
- `select_link` 뒤에 `select_link_router` conditional edge 추가
- `is_final=True`면 즉시 END로 이동

**url_agent/nodes.py**
- `analyze_node`에서 `is_final` 항상 `True` 반환 (첫 분석 후 종료)
- 기존 `prob` 기반 `is_final` 로직 제거 (select_link_node 미구현 상태)

### 결과
- 그래프 흐름: `extract → scrape → analyze → END` (단순화)
- 무한 루프 가능성 완전 제거

---

## Spam Validator UI 개선 (2026-01-25)

### 1. 텍스트 다운로드 기능
- ALL/FN/FP 탭별 메시지 원본 텍스트 다운로드 버튼 추가
- 파일명: `spam_validator_{filter}_{date}.txt`

### 2. 탭별 개수 표시
- Mismatches 헤더: 선택된 필터의 개수 표시 (예: "FP 8")
- 필터 버튼: 각각 뱃지로 개수 표시 (예: "ALL (50)")

### 3. Accuracy 카드 추가
- Human-LLM 합의도 섹션에 추가
- subValue: "단순 일치율"
- type: neutral (회색, 참고용 표시)
- tooltip: 클래스 불균형 취약성 안내

### 4. URL 분석 결과 코드 반영
- main.py: URL Agent의 classification_code로 spam_code 업데이트
- 코드 변경 시 알림: "⚠️ 코드 업데이트: 0 → 3 (URL 분석 기반)"

---

## URL Agent 개선 (2026-01-25)

### 프롬프트 강화 (`nodes.py`)
- **"Inconclusive" 키워드 강제 규칙 추가**
  - Captcha/보안 페이지 감지 시 반드시 reason에 "Inconclusive" 포함
  - 콘텐츠가 짧거나 비어있으면 반드시 "Inconclusive" 포함
  - 명확히 정상 사이트(사업자번호, 공식 사이트 등)일 때만 "Inconclusive" 없이 HAM 판정
- **한국어 스팸 키워드 추가**: 배팅, 카지노, 토토, 슬롯, 바카라, 충전, 환전, 유흥, 출장, 안마, 오피, 급전, 대출, 무서류

### 로깅 추가
- `scrape_node`: URL 스크래핑 결과 상세 로깅 (status, final_url, title, captcha, text_len, content_preview)
- `analyze_node`: LLM 분석 결과 로깅 (is_spam, probability, code, reason)

### 이유
- URL Agent가 Captcha 페이지를 "CONFIRMED SAFE"로 오판하여 Content SPAM을 override하는 문제 해결
- Aggregator의 `is_inconclusive` 체크가 "Inconclusive" 키워드에 의존하므로, URL Agent가 불확실한 경우 반드시 해당 키워드 포함하도록 강제
- 디버깅을 위한 URL 분석 과정 가시성 향상

---

## v1.5 (2026-01-25)

### 변경
- **섹션 4. route_or_cta 판정 원칙** 수정
  - **harm_anchor=true인 경우, 연락 수단 제공 자체를 CTA로 간주**
  - 기존: 전화/문자 요청은 항상 route_or_cta=false
  - 변경: harm_anchor=true면 전화/문자/카톡/URL 제공도 route_or_cta=true
  - 예시 추가: 성인/유흥+전화번호, 도박+카톡ID, 불법대출+문자회신

### 이유
- "울샨 한K 걸 ☎전화" 같은 성인 스팸이 HAM으로 오탐되는 문제 해결
- harm_anchor=true (불법 목적 확인)인데 "전화 요청"이라는 이유로 HAM 처리되던 허점 수정
- 불법 서비스에서 연락 수단은 실제 "서비스 이용 경로"이므로 CTA로 간주해야 함

### 프론트엔드 코드 매핑 동기화
- `frontend/src/App.tsx`, `frontend/src/components/LogViewer.tsx` 수정
- **기존 (1-10 코드 체계)** → **신규 (0-3 코드 체계)**로 통일
  | Code | 기존 | 신규 |
  |------|------|------|
  | 0 | (없음) | 기타 스팸 (통신, 대리운전, 구인/부업 등) |
  | 1 | 도박, 게임 | 유해성 스팸 (성인, 불법 의약품, 나이트클럽 등) |
  | 2 | 성인 | 사기/투자 스팸 (주식 리딩, 로또 등) |
  | 3 | 통신, 휴대폰 | **불법 도박/대출** (도박, 카지노, 불법 대출 등) |
- 백엔드 `constants.py` 및 `spam_guide.md`와 일치하도록 수정

---

## agent.py 버그 수정 (2026-01-25)

### 수정 1: 프롬프트 변수 치환 버그
- **문제**: `{{context_text}}` → Python f-string에서 escape 문자로 처리되어 실제 spam_guide.md 내용이 LLM에 전달되지 않음
- **수정**: `{{context_text}}` → `{context_text}` 로 변경
- **영향**: LLM이 spam_guide.md 규칙을 전혀 받지 못하고 자체 판단하던 문제 해결

### 수정 2: HARD GATE 안전장치 추가
- **문제**: `_parse_response`에서 `harm_anchor=false`여도 `spam_probability >= 0.6`이면 SPAM으로 분류
- **수정**: `_parse_response`에 HARD GATE 강제 로직 추가
  - `harm_anchor=false` → 무조건 `is_spam=False`
  - `harm_anchor=true AND route_or_cta=false` → `is_spam=False`
  - `harm_anchor=true AND route_or_cta=true` → 확률 기반 판단
- **영향**: LLM이 signals를 잘못 판단해도 코드 레벨에서 HARD GATE 규칙 강제

### 수정 3: 프롬프트 PROCEDURE 강화
- Step 4를 "SPAM 확정 조건: harm_anchor=true AND route_or_cta=true 일 때만 SPAM"으로 명확화

---

## v1.4 (2026-01-25)

### 추가
- **섹션 3. Content Agent 역할 제한** 신규 추가
  - Content Agent는 텍스트만 분석, URL은 URL Agent가 담당
  - URL/단축URL 존재는 harm_anchor 근거가 아님
  - 역할 분리 명확화로 오탐 방지

### 변경
- 섹션 번호 재정렬 (route_or_cta: 3→4, CODE EVIDENCE: 4→5)

### 이유
- Content Agent가 "단축 URL 존재"를 SPAM 근거로 오판하는 문제 해결
- 정치인 새해인사 등 정상 메시지가 URL 포함만으로 SPAM 판정되는 오탐 방지

---

## v1.3 (2026-01-25)

### 제거
- ~~섹션 3. IMAGE/URL HANDLING~~ (2.1에 통합)
- ~~섹션 4. DECISION CHECKLIST~~ (1.2, 2.1에 통합)
- ~~섹션 5. HIGH-RISK ACTION~~ (route_or_cta로 간소화)
- ~~섹션 6. AD_SUSPECT~~ (2.2에서 커버)
- ~~섹션 8. 판정 요약~~ (2.1과 중복)

### 변경
- 전체 구조 간소화 (8개 섹션 → 4개 섹션)
- 토큰 절약 (~900 토큰)

### 이유
- 중복 내용 제거로 토큰 비용 절감
- agent.py 프롬프트와 중복 제거

---

## v1.2 (2026-01-25)

### 변경
- **2.2 harm_anchor 판정 원칙** 수정
  - "키워드 직접 존재" → "합리적으로 확인"
  - 은어/난독화/맥락 기반 판단 허용
- **1.2 HAM 정의** 확장
  - 결제/승인/인증 알림 추가
  - 공공/행정/정치 메시지 추가
  - 개인화 1:1 트랜잭션 추가

### 이유
- 스팸이 난독화/은어를 사용하므로 맥락 기반 판단 필요
- 명확한 HAM 케이스를 즉시 HAM으로 처리

---

## v1.1 (초기 버전)

### 구조
```
0. 목적
1. 절대 정의 (SPAM/HAM 정의, 민원 방지 원칙)
2. HARD GATE (최상위 규칙)
3. IMAGE/URL HANDLING
4. DECISION CHECKLIST
5. HIGH-RISK ACTION
6. AD_SUSPECT
7. CODE EVIDENCE RULES
8. 대표 예시
9. 변경 정책
```

### 핵심 원칙
- harm_anchor = false → 무조건 HAM
- SPAM = harm_anchor + route_or_cta 모두 만족
- 불확실하면 HAM (민원 방지 우선)

---

## 변경 가이드라인

### 버전 번호 규칙
- **Major (x.0)**: 핵심 판단 로직 변경
- **Minor (x.y)**: 섹션 추가/제거, 규칙 명확화

### 변경 시 체크리스트
1. [ ] spam_guide.md 버전 번호 업데이트
2. [ ] 이 문서에 변경 이력 추가
3. [ ] agent.py 프롬프트와 일관성 확인
4. [ ] README.md 판단 로직 Table과 일관성 확인

