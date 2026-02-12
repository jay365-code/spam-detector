너는 시니어 풀스택 엔지니어(데이터/프론트)다. 나는 “Spam Validator”를 확장해서
JSON N개를 로드하고, 일자별로 취합(2~3개 소스 A/B/C)한 뒤,
일별 KPI 트렌드 + 날짜 클릭 시 FN/FP 상세 분석 화면을 제공하려고 한다.

# 0) 목표(중요)
- “파일별 KPI 평균” 금지.
- 반드시 일자별로 TP/FP/TN/FN을 합산하여(day confusion matrix) KPI를 재계산.
- 목적은 ‘LLM이 수작업을 대체 가능한가’에 대한 인사이트 제공.

# 1) 입력 데이터(첨부 JSON 포맷)
- 각 JSON은 { summary: {...}, diffs: [...] } 구조.
- summary에 tp/fp/tn/fn 및 precision/recall/f1/accuracy/kappa/mcc 등이 포함돼 있으나,
  일자별 KPI는 summary의 KPI를 신뢰하지 말고 합산된 confusion matrix로 재계산할 것.
- diffs에는 FN/FP 케이스 상세(메시지 원문, human/llm 라벨, llm_reason, policy_interpretation 등)가 들어있다.
- date/source는 JSON 본문에 없을 수 있으므로 파일명에서 파싱한다.
  예: "일별비교_20260101_A.json" -> date=2026-01-01, source=A

# 2) 디렉토리/로드 방식
- 사용자가 로컬 폴더를 지정하면 해당 폴더 내 JSON을 전부 로드한다.
- 기간 필터(start_date~end_date) 적용.
- 같은 date 내에 source(A/B/C) 2~3개가 있을 수 있다(누락 허용).
- 로드 실패/스키마 오류는 ingestion_log에 기록하고 나머지는 계속 처리.

# 3) 산출물(데이터셋) - 메모리 + 엑셀 저장
아래 3개 테이블을 생성하고, 엑셀(xlsx)로 저장(시트 3개):
1) source_summary (행: date, source)
   - date, source, records, tp, fp, tn, fn
   - (참고용) raw_kappa/raw_mcc/raw_f1/raw_precision/raw_recall/raw_accuracy (summary에서 읽은 값)
   - (검증용) calc_kappa/calc_mcc/calc_f1/calc_precision/calc_recall/calc_accuracy (tp/fp/tn/fn으로 재계산)
2) daily_summary (행: date)
   - date, total_records, TP, FP, TN, FN
   - daily_precision, daily_recall, daily_f1, daily_accuracy, daily_kappa, daily_mcc
   - fn_rate = FN/(TP+FN), fp_rate = FP/(FP+TN)
   - human_spam_rate, llm_spam_rate (가능하면 summary에서 count 기반으로 계산; 없으면 비워도 됨)
   - verdict: 🟢/🟡/🔴 (규칙은 아래 5) 참조
3) daily_diffs (행: date, source, idx)
   - date, source, diff_type(FN/FP), message_full, human_is_spam, llm_is_spam, llm_reason, policy_interpretation, 기타 필드
   - (optional) tags: url_present, short_msg, has_numbers, obfuscated 등 간단한 feature 추출

# 4) KPI 계산 함수(반드시 구현)
입력: tp, fp, tn, fn (int)
출력: precision, recall, f1, accuracy, kappa, mcc, fn_rate, fp_rate

정의:
- precision = tp/(tp+fp) if tp+fp>0 else 0
- recall = tp/(tp+fn) if tp+fn>0 else 0
- f1 = 2*precision*recall/(precision+recall) if precision+recall>0 else 0
- accuracy = (tp+tn)/N where N=tp+fp+tn+fn if N>0 else 0
- kappa:
  Po = (tp+tn)/N
  p_true_pos = (tp+fn)/N          # human spam rate in this matrix
  p_pred_pos = (tp+fp)/N          # llm spam rate in this matrix
  p_true_neg = (tn+fp)/N
  p_pred_neg = (tn+fn)/N
  Pe = p_true_pos*p_pred_pos + p_true_neg*p_pred_neg
  kappa = (Po - Pe)/(1 - Pe) if (1 - Pe)>0 else 0
- mcc:
  denom = sqrt((tp+fp)(tp+fn)(tn+fp)(tn+fn))
  mcc = (tp*tn - fp*fn)/denom if denom>0 else 0

# 5) Verdict 규칙(일자 기준)
- 🟢 협업 가능: daily_kappa >= 0.75 AND fn_rate <= 0.03
- 🟡 모니터링: 0.65 <= daily_kappa < 0.75 OR (0.03 < fn_rate <= 0.05)
- 🔴 위험: daily_kappa < 0.65 OR fn_rate > 0.05
(임계값은 상수로 정의하고 UI에서 조정 가능하도록 해도 좋음)

# 6) UI 요구사항(2레벨)
## Level 1: Daily Trend + KPI (기간 화면)
- 상단: 기간 선택(start/end), “데이터 로드” 버튼, “엑셀 다운로드” 버튼
- 차트(라인):
  - daily_kappa (기준선 0.75/0.65 표시)
  - fn_rate
  - (옵션) daily_mcc, daily_f1
- 테이블(클릭 가능, 정렬/필터):
  columns: date, total_records, daily_kappa, daily_mcc, fn_rate, fp_rate, FN, FP, verdict
- 테이블 row 클릭 -> Level 2로 이동 (해당 date)

## Level 2: Daily Deep Dive (날짜 상세)
- 상단 요약 카드: date, TP/FP/TN/FN, daily_kappa/mcc/f1, verdict
- Source breakdown 카드: A/B/C 각각 tp/fp/tn/fn + calc_kappa/mcc (raw KPI는 참고로 작은 글씨)
- 탭 2개:
  1) FN 탭:
     - FN count, policy_interpretation 분포(도넛/바)
     - FN 리스트(검색/필터: policy_interpretation, 키워드, url 여부)
     - row 클릭 -> 상세 모달(메시지 원문, human/llm, llm_reason)
  2) FP 탭:
     - 동일 구성
- “Back to Trend” 버튼

# 7) 기술 스택(선택해서 구현)
A안(권장): Python FastAPI + React(Typescript) + Recharts + openpyxl
B안(간단): Streamlit + pandas + openpyxl

내가 원하는 건 A안이지만, 작업량이 크면 B안으로 MVP를 먼저 만들어도 된다.
다만 데이터 모델/집계 로직은 동일해야 한다.

# 8) 구현 요구(산출물)
- (backend) bulk_loader:
  - load_json_files(root_dir, start, end) -> list of parsed files with date/source
  - build_source_summary(), build_daily_summary(), build_daily_diffs()
  - export_xlsx(path, tables)
- (api)
  - GET /api/days?start=...&end=... -> daily_summary[]
  - GET /api/day/{date} -> { daily_summary, source_summary[], diffs_fn[], diffs_fp[] }
  - GET /api/export?start=...&end=... -> xlsx download
- (frontend)
  - TrendPage: charts + table
  - DayDetailPage: summary + source cards + FN/FP tabs
  - 상태 뱃지(🟢/🟡/🔴) 일관 적용
- 에러/누락 처리:
  - date 폴더 누락/파일 누락은 warning으로 표기
  - summary에 tp/fp/tn/fn 없으면 해당 파일 skip + ingestion_log 기록

# 9) 개발 순서(지시)
1) JSON 로딩 + 파일명 파싱(date/source)
2) source_summary/daily_summary 계산(합산 후 KPI 재계산)
3) daily_diffs 누적 + FN/FP 필터 API
4) Trend UI + row click to detail
5) 엑셀 export
6) (옵션) policy_interpretation 기반 분포 차트

이 요구사항으로 “바로 실행 가능한” MVP 코드를 생성해라.
파일 구조, 실행 방법(로컬), 예시 .env/설정까지 포함해라.
