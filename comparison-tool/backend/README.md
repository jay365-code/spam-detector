# 🔍 Spam Validator

**Spam Validator**는 Human 판정과 AI 판정 결과를 비교하여 모델 성능을 분석하는 도구입니다.

## ✨ 주요 기능

- **정확도 분석**: TP, TN, FP, FN 계산
- **고급 지표**: Cohen's Kappa, MCC, Disagreement Rate
- **불일치 분석**: FN/FP 케이스 상세 보기

## 🚀 실행

```bash
cd comparison-tool/backend
pip install -r requirements.txt
python main.py  # http://localhost:8001
```

## 📋 로깅 시스템

### 로그 파일 위치
- **로그**: `comparison-tool/backend/logs/spam_validator.log` (7일 보관)

### 환경변수 설정
```env
LOG_LEVEL_CONSOLE=INFO    # DEBUG, INFO, WARNING, ERROR
LOG_LEVEL_FILE=DEBUG      # DEBUG, INFO, WARNING, ERROR
LOG_CONSOLE_ENABLED=1     # 1=ON, 0=OFF (운영환경에서는 0 권장)
```

### 런타임 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/log-level` | 현재 로그 레벨 조회 |
| `POST` | `/api/log-level` | 로그 레벨 변경 |
| `POST` | `/api/log-console` | 콘솔 출력 ON/OFF |

**사용 예시:**
```bash
# 레벨 조회
curl http://localhost:8001/api/log-level

# 콘솔 레벨을 DEBUG로 변경
curl -X POST http://localhost:8001/api/log-level \
  -H "Content-Type: application/json" \
  -d '{"target": "console", "level": "DEBUG"}'

# 콘솔 출력 끄기
curl -X POST http://localhost:8001/api/log-console \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

## 🔗 API

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/compare` | `POST` | Human/LLM Excel 비교 분석 |
| `/api/log-level` | `GET/POST` | 로그 레벨 조회/변경 |
| `/api/log-console` | `POST` | 콘솔 출력 ON/OFF |
