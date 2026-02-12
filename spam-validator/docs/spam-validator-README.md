# Spam Validator

> **스팸 분류 결과 검증 도구** - 사람의 육안 분류 결과와 AI(LLM) 자동 분류 결과의 일치도를 정량적으로 검증하는 웹 애플리케이션

---

## 📋 개요

Spam Validator는 엑셀 기반 스팸 분류 결과를 비교·분석하는 경량 검증 도구입니다.  
**Human(Ground Truth)**과 **AI(Prediction)**의 판단 차이를 수치화하고, 불일치 케이스를 시각적으로 검토할 수 있습니다.

### 핵심 목적
- 사람 기준으로 AI 스팸 판단이 얼마나 일치하는지 **정량적 지표** 제공
- **FN(False Negative)** / **FP(False Positive)** 중심의 Diff 분석
- 회의·보고용 지표로 즉시 활용 가능한 **자동 요약문** 생성

---

## ✨ 주요 기능

### 1. 파일 업로드 & 비교
- 엑셀 파일 2개 업로드 (Human.xlsx, LLM.xlsx)
- 지정 시트에서 `메시지`, `구분` 컬럼 자동 로드
- 메시지 정규화 및 중복 처리를 통한 정확한 매칭

### 2. 성능 지표 계산
| 지표 | 설명 |
|------|------|
| **Precision** | AI가 스팸이라 분류한 것 중 실제 스팸 비율 |
| **Recall** | 전체 실제 스팸 중 AI가 찾아낸 비율 |
| **F1 Score** | Precision과 Recall의 조화 평균 |
| **Cohen's Kappa (κ)** | 우연적 일치를 제거한 Human-AI 판단 일치도 |
| **MCC** | 클래스 불균형 상황에서의 종합 상관도 |
| **HEI** | Human Equivalence Index - 인간 대체 가능성 종합 평가 |

### 3. Diff 분석 UI
- FN/FP 케이스 필터링 및 검색
- 메시지 원문과 양측 분류 결과 상세 확인
- 정책 해석 태그 자동 부여

### 4. 자동 요약문 생성
분석 결과를 한국어 서술형으로 자동 생성하여 보고서에 즉시 활용 가능

---

## 🛠 기술 스택

### Backend
- **Python 3.11+**
- **FastAPI** - 고성능 웹 프레임워크
- **pandas** - 데이터 처리
- **openpyxl** - 엑셀 파일 파싱

### Frontend
- **React 18** + **TypeScript**
- **Vite** - 빌드 도구
- **Tailwind CSS** - 스타일링
- **Axios** - HTTP 클라이언트

---

## 📦 설치 방법

### Backend 설정

```bash
cd comparison-tool/backend

# 가상환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 의존성 설치
pip install -r requirements.txt
```

### Frontend 설정

```bash
cd comparison-tool/frontend

# 의존성 설치
npm install
```

---

## 🚀 실행 방법

### 1. Backend 서버 실행

```bash
cd comparison-tool/backend
.\venv\Scripts\activate
python main.py
```

서버가 `http://localhost:8001`에서 실행됩니다.

### 2. Frontend 개발 서버 실행

```bash
cd comparison-tool/frontend
npm run dev
```

브라우저에서 `http://localhost:5173`으로 접속합니다.

---

## 📖 사용 방법

### Step 1: 파일 준비
두 개의 엑셀 파일을 준비합니다:
- **Human.xlsx**: 사람이 육안으로 분류한 결과
- **LLM.xlsx**: AI가 자동으로 분류한 결과

### Step 2: 필수 컬럼 확인
각 파일에 다음 컬럼이 포함되어야 합니다:

| 컬럼명 | 설명 |
|--------|------|
| `메시지` | 비교 기준 메시지 원문 |
| `구분` | 스팸 여부 (`o` = 스팸, 그 외 = 햄) |
| `분류` (선택) | 분류 코드 |
| `Reason` / `사유` (선택) | 분류 근거 |

### Step 3: 비교 실행
1. 웹 페이지에서 **Target Sheet** 이름 입력
2. **Human (Ground Truth)** 파일 업로드
3. **AI (Prediction)** 파일 업로드
4. **Analyze** 버튼 클릭

### Step 4: 결과 확인
- **Workload Statistics**: 양측 데이터 통계
- **HEI (Human Equivalence Index)**: 종합 평가 점수
- **Human-LLM 합의도**: Cohen's Kappa, MCC, 불일치율
- **Performance Metrics**: F1, Precision, Recall, FN/FP 건수
- **분석 요약**: 자동 생성된 한국어 요약문
- **Mismatches**: 불일치 케이스 상세 분석

---

## 🔌 API 엔드포인트

### POST `/compare`

엑셀 파일 2개를 비교하여 분석 결과를 반환합니다.

**Request (multipart/form-data)**
| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `human_file` | File | ✅ | Human 분류 결과 엑셀 파일 |
| `llm_file` | File | ✅ | AI 분류 결과 엑셀 파일 |
| `sheet_name` | String | ❌ | 대상 시트명 (기본값: `육안분석(시뮬결과35_150)`) |

**Response**
```json
{
  "summary": {
    "sheet_used": "시트명",
    "total_human": 1000,
    "total_llm": 1000,
    "human_spam_count": 88,
    "llm_spam_count": 86,
    "human_spam_rate": 0.088,
    "llm_spam_rate": 0.086,
    "matched": 1000,
    "match_rate": 1.0,
    "agreement_rate": 0.92,
    "tp": 82,
    "fp": 4,
    "fn": 6,
    "tn": 908,
    "precision": 0.9535,
    "recall": 0.9318,
    "f1": 0.9425,
    "kappa": 0.8654,
    "kappa_status": "거의 인간 수준 합의",
    "mcc": 0.8721,
    "disagreement_rate": 0.01,
    "hei": 0.8812,
    "hei_status": "인간 대체 가능",
    "hei_color": "success"
  },
  "diffs": [
    {
      "diff_id": "abc123...",
      "diff_type": "FN",
      "message_preview": "메시지 미리보기...",
      "message_full": "전체 메시지 내용",
      "human_label_raw": "o",
      "llm_label_raw": "",
      "human_is_spam": true,
      "llm_is_spam": false,
      "human_reason": "광고성 문구",
      "llm_reason": "",
      "match_key": "정규화된메시지... (idx: 1)",
      "policy_interpretation": "정책 차이"
    }
  ],
  "auto_summary": "본 LLM 기반 Spam Detector는 사람 수작업 대비 스팸 탐지 Recall 93.2%를 달성했으며..."
}
```

---

## 📊 지표 상세 설명

### Confusion Matrix

```
                AI Prediction
                SPAM    HAM
Human    SPAM    TP      FN
Truth    HAM     FP      TN
```

| 구분 | 설명 |
|------|------|
| **TP (True Positive)** | Human=스팸, AI=스팸 (정탐) |
| **FN (False Negative)** | Human=스팸, AI=햄 (놓침) |
| **FP (False Positive)** | Human=햄, AI=스팸 (오탐) |
| **TN (True Negative)** | Human=햄, AI=햄 (정상) |

### Cohen's Kappa (κ) 해석

| κ 범위 | 해석 |
|--------|------|
| ≥ 0.80 | 거의 인간 수준 합의 |
| 0.60 ~ 0.79 | 강한 합의 |
| 0.40 ~ 0.59 | 중간 수준 합의 |
| < 0.40 | 약한 합의 |

### HEI (Human Equivalence Index) 계산

```
HEI = 0.4 × Recall + 0.3 × (1 - FN Rate) + 0.3 × Kappa
```

| HEI 범위 | 상태 |
|----------|------|
| ≥ 0.85 | 🟢 인간 대체 가능 |
| 0.75 ~ 0.84 | 🟡 보조적 대체 |
| < 0.75 | 🔴 검토 필요 |

---

## 📁 프로젝트 구조

```
comparison-tool/
├── backend/
│   ├── main.py           # FastAPI 서버 & 비교 로직
│   ├── test_metrics.py   # 지표 계산 테스트
│   ├── requirements.txt  # Python 의존성
│   └── venv/             # 가상환경
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx       # 메인 React 컴포넌트
│   │   ├── App.css       # 스타일
│   │   └── main.tsx      # 엔트리 포인트
│   ├── package.json      # Node.js 의존성
│   └── vite.config.ts    # Vite 설정
│
└── docs/
    ├── PRD.md            # 제품 요구사항 정의서
    └── spam-validator-README.md  # 본 문서
```

---

## ⚠️ 제한 사항

- **분류 수정 및 저장 기능 미지원**
- **재분류(LLM 호출) 기능 미지원**
- **다중 클래스 분류 미지원** (이진 분류만 지원)
- **다중 시트 비교 미지원**
- **사용자 인증/권한 관리 미지원**

---

## 🧪 테스트

백엔드 지표 계산 테스트:

```bash
cd comparison-tool/backend
.\venv\Scripts\activate
python test_metrics.py
```

---

## 📝 라이선스

내부 사용 전용

---

## 👥 기여

문의 및 버그 리포트는 프로젝트 담당자에게 연락해 주세요.


