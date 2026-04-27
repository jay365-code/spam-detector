# CLAUDE.md — Strato Spam Detector

> 협업 세부 규칙은 `GEMINI.md` 참조. 이 문서는 Claude Code 세션에
> 매 호출 자동 주입되는 **요약본**이다.

## 1. 기본 협업 규칙
- 응답/주석/도구 요약: **한국어**
- 코드 수정 전: 변경 요약 + 이유 설명 + **명시적 승인** 후 진행
- 작업은 원자적 단위로 쪼개고 단계마다 확인

## 2. 환경
- OS: **macOS**, Shell: **zsh** (명령 체이닝은 `&&`)
- Python: `./.venv` 활성화 필수
- 새 패키지 설치 시 `requirements.txt` 갱신
  - ⚠️ `requirements.txt`는 UTF-16 인코딩 — 직접 수정 시 인코딩 유지

## 3. 자주 쓰는 명령어
- Backend 개발 실행: `python backend/run.py` (uvicorn 내부 호출, reload=False)
- Backend 테스트: `cd backend && pytest tests/`
- Frontend 개발: `cd frontend && npm run dev`
- Frontend 빌드/린트: `npm run build`, `npm run lint`

## 4. 운영 환경 (권장 구성)
- Docker Compose + Nginx 리버스 프록시
- 베이스 이미지: `mcr.microsoft.com/playwright/python` (Playwright 시스템 의존성 포함)
- 워커 수: **1 worker + 내부 async 동시성** (`MAX_BROWSER_CONCURRENCY`로 조절)
  - Playwright 다중 워커는 브라우저 풀이 워커별로 중복되어 메모리 급증
- `uvicorn --reload` 사용 금지 (Playwright 이벤트 루프 정책 충돌)
- ChromaDB 디렉터리는 볼륨 마운트로 영속화
- `.env`는 레포 외부에서 주입 (커밋 금지)

## 5. 아키텍처 (요약)
- 도메인: AI 에이전트 기반 한국어 SMS 스팸 탐지
- 파이프라인: Rule → Content → URL → IBSE → Aggregator → FP Sentinel → HITL
- 다중 에이전트: LangGraph 기반 (`backend/app/agents/*`)
- 상세 설계: `docs/README.md`

## 6. LLM 선택 정책
- **주력은 Gemini** — 품질·비용 양쪽에서 최적이라 판단해 채택
- Claude Haiku 4.5는 보조용 (교차검증/fallback)
- Claude 주력 전환 제안 금지. LLM 추가/교체 제안 시 비용·품질 근거 필수
- 모델 정의: `backend/app/core/models.py`

## 7. 금기 사항
- `.env`, API 키, 크레덴셜 파일 커밋 금지
- **LLM 프롬프트·컨텍스트 수정은 반드시 승인 후 진행** (에이전트 판정 품질에
  직결되므로 단독 판단으로 문구를 바꾸지 말 것)
- `requirements.txt` UTF-16 인코딩 건드리지 말 것

## 8. 테스트
- Backend: `pytest` + `pytest-asyncio`, 구조는 `backend/tests/` 참고
- UI/프론트 변경 시 `npm run build` 통과 확인 후 보고

## 9. 외부 문서
- 전체 설계/플로우: `docs/README.md`
- 협업 프로토콜 상세: `GEMINI.md`
