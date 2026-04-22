import re
import io
import os
import pandas as pd
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, Any, List, Tuple, Optional

class ResultValidator:
    def __init__(self, logs_data: Dict[str, Any], excel_bytes: Optional[bytes] = None, excel_filename: Optional[str] = None):
        """
        logs_data: The logs object from the frontend/JSON
        excel_bytes: The uploaded Excel file bytes (optional)
        excel_filename: The name of the uploaded Excel file (optional)
        """
        if isinstance(logs_data, dict):
            self.logs = list(logs_data.values())
        elif isinstance(logs_data, list):
            self.logs = logs_data
        else:
            self.logs = []
            
        self.logs = [l for l in self.logs if l and isinstance(l, dict)]
        self.excel_bytes = excel_bytes
        self.excel_filename = excel_filename

    def _normalize_text(self, text: Any) -> str:
        text_str = str(text) if text is not None else ""
        return re.sub(r'\s+', '', text_str)

    def _get_cp949_len(self, text: str) -> int:
        if not text:
            return 0
        try:
            return len(str(text).encode('cp949'))
        except UnicodeEncodeError:
            return len(str(text).encode('utf-8'))

    def validate(self) -> tuple[str, str | None]:
        if not self.logs:
            return "분석된 JSON 로그가 없습니다.", None

        excel_data = []
        excel_map = {}
        sig_map = {}
        
        if self.excel_bytes:
            import io
            try:
                sheets = pd.read_excel(io.BytesIO(self.excel_bytes), sheet_name=None)
                
                # 1.1 Main Sheet (Find 육안분석 or MMSC)
                main_df = None
                for s_name, s_df in sheets.items():
                    if "육안분석" in s_name or "MMSC" in s_name:
                        main_df = s_df
                        break
                
                if main_df is None:
                    for s_name, s_df in sheets.items():
                        if "검토필요" in s_df.columns or "Red Group" in s_df.columns:
                            main_df = s_df
                            break
                
                if main_df is None:
                    # Fallback to second sheet if available, else first
                    if len(sheets) > 1:
                        main_df = list(sheets.values())[1]
                    else:
                        main_df = list(sheets.values())[0]

                excel_data = main_df.to_dict('records')
                
                # Create a lookup map for the main sheet
                for i, row in enumerate(excel_data):
                    msg = str(row.get("메시지", "")).strip()
                    if msg and msg != "nan":
                        norm_msg = self._normalize_text(msg)
                        excel_map[norm_msg] = {
                            "row": row,
                            "idx": i + 2  # Excel row index
                        }

                # 1.2 Blocklist Sheet (Find 문자문장차단등록)
                sig_df = None
                for s_name, s_df in sheets.items():
                    if "문자문장차단등록" in s_name:
                        sig_df = s_df
                        break
                
                if sig_df is not None:
                    sig_data = sig_df.to_dict('records')
                    for row in sig_data:
                        msg = str(row.get("메시지", "")).strip()
                        if msg and msg != "nan":
                            norm_msg = self._normalize_text(msg)
                            s1 = str(row.get("문자열") or "").strip()
                            s2 = str(row.get("문장열") or "").strip()
                            if s1 == "nan": s1 = ""
                            if s2 == "nan": s2 = ""
                            sig = s1 if s1 else s2
                            if sig:
                                sig_map[norm_msg] = sig

            except Exception as e:
                return f"❌ 엑셀 파일 파싱 오류: {str(e)}", None

        total_checked = 0
        mismatch_count = 0
        
        msg_results = {}

        # 3. JSON-Excel Cross Validation
        for log in self.logs:
            res = log.get("result") or {}
            req = log.get("request") or {}
            msg = log.get("message") or ""
            norm_msg = self._normalize_text(msg)
            
            # --- URL 통계 ---
            pre_parsed_url = res.get("pre_parsed_url")
            if not pre_parsed_url and req.get("url"):
                pre_parsed_url = req.get("url")
                
            is_dropped = res.get("drop_url", False)

            # --- 시그니처 품질 검증 ---
            is_spam = res.get("is_spam", False)
            ibse_cat = str(res.get("ibse_category") or "")
            cls_code = str(res.get("classification_code") or "")
            sig = str(res.get("ibse_signature") or "")
            sig_len = self._get_cp949_len(sig) if sig else 0
            
            excel_row = excel_map.get(norm_msg, {}).get("row", {})
            excel_idx = excel_map.get(norm_msg, {}).get("idx", "-")
            excel_url = str(excel_row.get("URL") or excel_row.get("URL(단축URL)") or "").strip() if excel_row else ""
            if excel_url == "nan": excel_url = ""
            excel_sig = sig_map.get(norm_msg, "")
            # Remove leading single quote added by excel_handler to prevent formula evaluation
            if isinstance(excel_sig, str):
                excel_sig = excel_sig.strip()
                if excel_sig.startswith("'"):
                    excel_sig = excel_sig[1:]

            result_row = {
                "엑셀 행 번호": excel_idx,
                "원문 메시지": msg,
                "스팸여부": "SPAM" if is_spam else "HAM",
                "분류코드": cls_code,
                "Input URL": pre_parsed_url or "",
                "Excel URL": excel_url,
                "JSON 시그니처": sig,
                "Excel 시그니처": excel_sig,
                "Size(Byte)": sig_len,
                "판정 교차검증": "정상",
                "시그니처 교차검증": "정상",
                "URL 교차검증": "정상",
                "시그니처 규격 검사": "정상",
                "클러스터 일관성": "정상",
                "_has_error": False
            }
            
            if is_spam:
                if "unextractable" not in ibse_cat.lower() and sig:
                    if not ((9 <= sig_len <= 20) or (39 <= sig_len <= 40)):
                        result_row["시그니처 규격 검사"] = f"길이 위반 ({sig_len} bytes)"
                        result_row["_has_error"] = True

            # --- 엑셀 교차 비교 (Excel Uploaded) ---
            if self.excel_bytes and norm_msg in excel_map:
                total_checked += 1
                
                # A. URL 누락 교차 검증
                if is_dropped and excel_url:
                    result_row["URL 교차검증"] = "불일치 (JSON Drop, Excel 보존됨)"
                    result_row["_has_error"] = True
                    mismatch_count += 1
                elif not is_dropped and pre_parsed_url and not excel_url and is_spam:
                    # HAM 메시지는 정책상 엑셀 URL 컬럼을 비워두므로, SPAM일 때만 검사
                    result_row["URL 교차검증"] = "불일치 (JSON 보존, Excel 누락됨)"
                    result_row["_has_error"] = True
                    mismatch_count += 1

                # B. 판정 교차 검증
                excel_gubun = str(excel_row.get("구분") or "").strip().upper()
                if excel_gubun == "nan": excel_gubun = ""
                
                is_red_group = bool(res.get("red_group", False))
                # 엑셀 핸들러는 Red Group의 경우 구분을 빈칸으로 둠
                if is_red_group:
                    expected_excel_is_spam = False
                else:
                    expected_excel_is_spam = is_spam

                excel_is_spam = (excel_gubun == "O")
                
                if expected_excel_is_spam != excel_is_spam:
                    if is_red_group:
                        result_row["판정 교차검증"] = f"불일치 (Red Group이라 Excel 빈칸 예상이나 '{excel_gubun}' 존재)"
                    else:
                        result_row["판정 교차검증"] = f"불일치 (JSON: {'SPAM' if is_spam else 'HAM'}, Excel: {'SPAM' if excel_is_spam else 'HAM'})"
                    result_row["_has_error"] = True
                    mismatch_count += 1
                
                # C. 시그니처 교차 검증
                # JSON ibse_signature가 실제로 None이면 검증 skip (Excel nan과 오탐 방지)
                json_has_sig = bool(res.get("ibse_signature"))
                if (is_spam or is_red_group) and json_has_sig:
                    if sig != excel_sig:
                        result_row["시그니처 교차검증"] = f"불일치 (JSON과 엑셀 값이 다름)"
                        result_row["_has_error"] = True
                        mismatch_count += 1

            msg_results[norm_msg] = result_row

        # 4. 클러스터 일관성 검사
        items = []
        for idx, log in enumerate(self.logs):
            res = log.get("result") or {}
            msg = log.get("message") or ""
            items.append({
                "id": idx,
                "msg": msg,
                "norm_msg": self._normalize_text(msg),
                "is_spam": res.get("is_spam", False),
                "signature": res.get("ibse_signature") or "",
                "category": str(res.get("classification_code") or "")
            })

        visited = set()
        clusters = []
        
        for i in range(len(items)):
            if i in visited: continue
            
            cluster = [items[i]]
            visited.add(i)
            
            from difflib import SequenceMatcher
            for j in range(i + 1, len(items)):
                if j in visited: continue
                len1, len2 = len(items[i]['norm_msg']), len(items[j]['norm_msg'])
                max_possible = (2.0 * min(len1, len2)) / (len1 + len2) if (len1 + len2) > 0 else 0
                if max_possible < 0.85: continue
                
                ratio = SequenceMatcher(None, items[i]['norm_msg'], items[j]['norm_msg']).ratio()
                if ratio >= 0.85:
                    cluster.append(items[j])
                    visited.add(j)
                    
            clusters.append(cluster)
                
        for cluster in clusters:
            if len(cluster) > 1:
                spam_statuses = set([item["is_spam"] for item in cluster])
                sigs = set([item["signature"] for item in cluster if item["signature"]])
                cats = set([item["category"] for item in cluster if item["category"]])
                
                has_inconsistent = False
                err_str = ""
                if len(spam_statuses) > 1:
                    has_inconsistent = True
                    err_str = "그룹 내 스팸/햄 엇갈림"
                    
                if len(cats) > 1:
                    has_inconsistent = True
                    if err_str: err_str += ", "
                    err_str += "그룹 내 분류코드 엇갈림"
                    
                if len(sigs) > 1:
                    has_inconsistent = True
                    if err_str: err_str += ", "
                    err_str += "그룹 내 시그니처 엇갈림"
                    
                if has_inconsistent:
                    for item in cluster:
                        nmsg = item["norm_msg"]
                        if nmsg in msg_results:
                            msg_results[nmsg]["클러스터 일관성"] = err_str
                            msg_results[nmsg]["_has_error"] = True

        # 클러스터 단위 정렬: 스팸 판정이 많은 클러스터부터 내림차순 정렬
        clusters.sort(key=lambda c: sum(1 for item in c if item["is_spam"]), reverse=True)

        # 모든 결과를 엑셀에 저장 (클러스터 정렬 순서 유지)
        detail_rows = []
        for cluster in clusters:
            # 클러스터 내에서는 에러가 있는 항목이 위로 가도록 정렬
            cluster_rows = [msg_results[item["norm_msg"]] for item in cluster if item["norm_msg"] in msg_results]
            cluster_rows.sort(key=lambda x: not x.get("_has_error", False))
            detail_rows.extend(cluster_rows)

        # 5. Save Details to Excel
        output_filename = None
        if detail_rows:
            import os
            output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../data/outputs'))
            os.makedirs(output_dir, exist_ok=True)
            
            date_type_suffix = ""
            if self.excel_filename:
                # 추출 시도: 20260414_B 등 (8자리숫자_알파벳)
                match = re.search(r'(\d{8}_[a-zA-Z])', self.excel_filename)
                if match:
                    date_type_suffix = f"_{match.group(1).upper()}"
                    
            if date_type_suffix:
                output_filename = f"validation_result{date_type_suffix}.xlsx"
            else:
                import datetime
                now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"validation_result_{now_str}.xlsx"
                
            output_path = os.path.join(output_dir, output_filename)
            
            df_out = pd.DataFrame(detail_rows)
            # Reorder columns
            cols = ["엑셀 행 번호", "원문 메시지", "스팸여부", "분류코드", "Input URL", "Excel URL", "JSON 시그니처", "Excel 시그니처", "Size(Byte)", "판정 교차검증", "시그니처 교차검증", "URL 교차검증", "시그니처 규격 검사", "클러스터 일관성"]
            df_out = df_out[[c for c in cols if c in df_out.columns]]
            
            with pd.ExcelWriter(output_path, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as writer:
                df_out.to_excel(writer, index=False, header=False, startrow=1, sheet_name='Validation')
                workbook = writer.book
                worksheet = writer.sheets['Validation']
                
                # Formats
                center_fmt = workbook.add_format({'align': 'center', 'valign': 'vcenter'})
                num_fmt = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'num_format': '#,##0'})
                error_fmt = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#D9D9D9'})
                
                # 텍스트 길이에 기반한 동적 컬럼 너비 계산 (한글=2, 영문=1)
                def get_visual_length(text):
                    if pd.isna(text): return 0
                    text_str = str(text)
                    return sum(2 if ord(c) > 127 else 1 for c in text_str)

                # 데이터에 맞게 열 너비 자동 조정
                for col_num, col_name in enumerate(df_out.columns):
                    max_len = df_out[col_name].map(get_visual_length).max()
                    header_len = get_visual_length(col_name)
                    col_width = max(max_len, header_len) + 4  # 여백 추가
                    
                    fmt = center_fmt
                    if col_name == "원문 메시지":
                        col_width = min(max(col_width, 30), 80) # 너무 넓어지지 않게 80으로 제한
                        fmt = None  # 기본 정렬
                    elif col_name == "Input URL":
                        col_width = 50
                        fmt = None  # 가로맞춤 일반
                    elif col_name == "Excel URL":
                        col_width = 50
                    elif col_name == "Size(Byte)":
                        col_width = 12
                        fmt = num_fmt
                    elif "교차검증" in col_name or "일관성" in col_name or "검사" in col_name:
                        col_width = min(max(col_width, 18), 50) # 검증 결과 최대 50
                    else:
                        col_width = min(max(col_width, 15), 40)
                        
                    worksheet.set_column(col_num, col_num, col_width, fmt)
                
                # 헤더 우리가 직접 쓰기 (Pandas와 충돌 방지)
                for col_num, value in enumerate(df_out.columns.values):
                    worksheet.write_string(0, col_num, str(value), header_fmt)
                
                # 에러/경고가 있는 특정 셀에만 빨간 배경색 적용 (조건부 서식 사용)
                for col_num, col_name in enumerate(df_out.columns):
                    if col_name in ["판정 교차검증", "시그니처 교차검증", "URL 교차검증", "시그니처 규격 검사", "클러스터 일관성"]:
                        worksheet.conditional_format(1, col_num, len(detail_rows), col_num, {
                            'type': 'cell',
                            'criteria': 'not equal to',
                            'value': '"정상"',
                            'format': error_fmt
                        })

        # Build summary text
        error_count = len([r for r in detail_rows if r.get("_has_error")])
        summary_lines = [
            f"✅ 검증 완료 (총 {len(self.logs)}건 중 엑셀 1:1 매핑 확인: {total_checked}건)",
            f"- 엑셀 판정/데이터 불일치 (불량): {mismatch_count}건",
            "",
            "[기타 내부 검증 결과]",
            f"- 시그니처 누락: {len([r for r in msg_results.values() if r.get('JSON 시그니처') == ''])}건"
        ]

        if detail_rows:
            summary_lines.append("")
            summary_lines.append(f"👉 전체 결과 {len(detail_rows)}건 (오류/경고 {error_count}건)이 엑셀 리포트로 생성되었습니다.")

        return "\n".join(summary_lines), output_filename
    def _normalize_text(self, text: Any) -> str:
        text_str = str(text) if text is not None else ""
        return re.sub(r'\s+', '', text_str)

    def _get_cp949_len(self, text: str) -> int:
        if not text:
            return 0
        try:
            return len(str(text).encode('cp949'))
        except UnicodeEncodeError:
            return len(str(text).encode('utf-8'))

