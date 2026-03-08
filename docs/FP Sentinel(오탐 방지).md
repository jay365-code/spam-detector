# FP Sentinel Agent Requirements (for vibe coding)

## 1. 목적 (Purpose)
FP Sentinel은 **False Positive(오탐) 방지 전용 정책 에이전트**다.  
의미적으로는 스팸이지만, 본문에 정상 토큰(예: 기업명, 공공기관명, 배송, 안내, 승인, 시총, 매출 등)이 많이 포함되어 있어  
**Naive Bayes / 문자열 기반 필터를 오염시킬 위험이 큰 메시지**를 식별하고,  
**차단 정책(Enforcement)** 과 **학습 정책(Learning)** 을 분리하여 운영한다.

핵심 목표:
1. 정상 토큰이 스팸 학습 데이터로 들어가 **NB 오탐이 증가하는 문제**를 방지한다.
2. 본문 차단이 위험한 케이스는 **URL 중심 차단**으로 우회한다.
3. Type B(오탐 민감형 스팸)를 별도 관리하여 **실시간 차단 정확도와 학습 안정성**을 동시에 확보한다.

---

## 2. 위치 (Workflow Position)
FP Sentinel은 **Aggregator 이후, 최종 종료 전**에 위치한다.

### Workflow
- Content Agent → Router
- Router → URL Agent (if URL exists)
- Router → IBSE Agent (if spam probability >= threshold)
- URL Agent / IBSE Agent → Aggregator
- **Aggregator → FP Sentinel**
- FP Sentinel → End
- End → Excel Handler

### 이유
FP Sentinel은 다음 결과를 모두 본 뒤에 판단해야 한다.
- Content Agent의 본문 의도 분석 결과
- URL Agent의 URL 위험도/리다이렉션/최종 도메인
- IBSE Agent의 시그니처 추출 결과
- Entity 매칭 결과(기업명, 공공기관명 등)

즉, FP Sentinel은 **최종 라벨러라기보다 “정책 엔진(Policy Engine)”** 으로 동작한다.

---

## 3. 핵심 개념 (Core Concepts)

### 3.1 Semantic Class
FP Sentinel은 메시지를 아래 3가지 의미 클래스 중 하나로 분류한다.

- `Type_A` = **Pure Spam**
  - 본문만 봐도 유해/불법/사기 목적이 명확한 전형적 스팸
  - 예: 도박, 성인, 불법약, 대출사기, 피싱, 리딩방, 불법부업 등

- `Type_B` = **FP-Sensitive Spam**
  - 의미적으로는 스팸이지만, 본문에 정상 토큰이 많이 섞여 있어
    그대로 학습시키면 Naive Bayes / 문자열 필터가 오염될 위험이 큰 스팸
  - 예: 삼성전자/시총/매출/안내드립니다/고객센터/배송/승인 같은 정상 단어를 섞은 사칭형 투자/피싱/홍보 스팸

- `Ham`
  - 정상 메시지
  - 정상 공지, 승인/인증/명세, 공공기관 알림, 합법 마케팅/사업자 광고 등

## 4. 정책 기반 판단 로직 (Decision Matrix)

이전 단계의 에이전트 결과들을 조합하여 정책을 결정합니다.

**판단에 쓰이는 팩터 (Factors)**
- `C_Spam`: Content Agent 기준 스팸 의도 (True/False)
- `C_Impersonation`: Content Agent 기준 **사칭/위장 의도** 플래그 (`is_impersonation: boolean`)
- `C_VagueCTA`: Content Agent 기준 **의도적 모호 행동 유도** 플래그 (`is_vague_cta: boolean`)
  - 예: "확실하게 보여드리겠습니다", "들어오셔서 성과 지켜봐주세요" 등 범용어로 구성되어 링크 클릭이 공격 벡터인 패턴
- `C_PersonalLure`: Content Agent 기준 **사적 관계/경조사 위장** 플래그 (`is_personal_lure: boolean`)
  - 예: "[부고] 모친상", "청첩장", "오랜만이네 잘 지내?" 등 일상어로 클릭을 유도하는 패턴
- `U_Blocked`: URL Agent가 악성 방어막(timeout, Cloudflare 등) 차단을 겪었는가? (`bot_protection_active` 등)
- `U_Spam`: URL Agent 기준 결과 페이지가 명백한 악성인가?
- `U_ConfirmedSafe`: URL Agent가 URL이 안전하다고 명시적으로 확인 (`CONFIRMED SAFE` 태그)
- `I_Spam`: IBSE Agent 시그니처가 스팸 의도와 일치하는가?

---

### [Priority 0] URL CONFIRMED SAFE → Ham 확정
- **조건**: URL Agent가 안전함을 명시적으로 확인 (`U_ConfirmedSafe` = True)
- **결과**: `Ham` (c_impersonation 여부 무관)
- **의의**: 관리비 알림 등 정상 URL을 포함한 메시지가 텍스트 사칭으로 오분류되는 것을 최우선으로 방지.

---

### [룰셋 1] Type_B (사칭/기만)
- **조건**: `C_Impersonation` = True
- **결과**: `Type_B`
- **의의**: 대기업/공공기관 사칭 또는 정상 업무 위장. 이러한 메시지는 정상 비즈니스 용어를 사용하므로 나이브베이즈 오염 위험이 큽니다. URL 존재 여부나 접속 실패 등과 무관하게 사칭 신호만으로 Type_B 확정합니다.

### [룰셋 1.2] Type_B (Vague CTA 스팸 확정)
- **조건**: `C_VagueCTA` = True **AND** 최종 `is_spam` = True
- **결과**: `Type_B` (학습 제외)
- **의의**: 텍스트 자체는 모호/범용어로 구성되어 있고 최종적으로 스팸 판정이 난 경우(URL 추출 여부 무관). 이러한 모호한 정상 텍스트를 그대로 SPAM으로 학습하면 나이브베이즈가 정상 표현을 스팸으로 오인하기 쉬우므로 Type_B 처리.

### [룰셋 1.3] Type_B (Personal Lure)
- **조건**: `C_PersonalLure` = True
- **결과**: `Type_B`
- **의의**: 부고, 청첩장, 카톡 추가 유도 등 지인과의 일상 대화를 100% 모방한 메시지입니다. URL 유무와 무관하게 이를 Type_A로 학습하면 실제 개인 간 메시지가 스팸 처리되는 치명적인 오탐이 발생하므로 나이브 베이즈에서 완전히 격리합니다.

### [룰셋 1.5] Type_B (텍스트 HAM + URL 위험/불확실)
- **조건**: Content Agent가 HAM 판정 (`C_Spam` = False) **AND** (URL 악성 확인 또는 URL timeout/bot-block)
- **결과**: `Type_B` + Enforcement 차단 (`is_spam=True`)
- **의의**: 미결제 확인 안내처럼 텍스트는 정상이지만 연결된 URL이 악성이거나 접근 불가. 텍스트 학습 모델 오염 없이 URL 기반으로 차단.

### [룰셋 2] Type_A (Pure Spam) 판별
- **조건**: 위 룰셋에 해당하지 않음 **AND** 최종 판정이 스팸 (`is_spam` = True)
- **결과**: `Type_A`
- **의의**: 사칭·기만·모호한 우회 없이 명백한 불법/스팸 의도가 확인됨. 안심하고 SPAM으로 차단 및 학습.

### [룰셋 3] Ham 판별
- **조건**: 위 룰셋 중 어느 것도 해당하지 않는 경우
- **결과**: `Ham`

---

## 5. Override 규칙 (HITL 상태 무시)
기존 로직은 Content Agent의 스팸 확률이 0.4~0.6 사이일 때 **[확인 필요] (HITL, 코드 30)** 상태로 보류합니다.
하지만 FP Sentinel에서 **Type_B (룰셋 1, 1.2, 1.5)** 조건이 충족될 경우, 이는 교묘한 텍스트로 LLM을 속이려다 URL 필터에 걸린 명백한 피싱이므로, 기존의 보류 상태를 무시하고 **즉시 확정 차단(SPAM)으로 오버라이드(Override)** 합니다.
단, P0(CONFIRMED SAFE)가 선행되면 어떤 룰셋도 발동하지 않습니다.
