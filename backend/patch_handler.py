import sys
import re

def refactor():
    with open('app/utils/excel_handler.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find where generate_excel_from_json starts and ends
    start_str = "    def generate_excel_from_json(self, logs: list, output_path: str, is_trap: bool, original_filename: str = None) -> dict:"
    
    start_idx = content.find(start_str)
    if start_idx == -1:
        print("Could not find method!")
        return

    # Find the start of the next method or end of file
    next_method_idx = content.find("\n    def ", start_idx + 10)
    if next_method_idx == -1:
         end_idx = len(content)
    else:
         end_idx = next_method_idx

    new_method = """    def generate_excel_from_json(self, logs: list, output_path: str, is_trap: bool, original_filename: str = None) -> dict:
        \"\"\"
        Re-generate the Excel file entirely from the UI's JSON state (logs).
        \"\"\"
        wb = Workbook()
        # 1. 시트 초기화 및 헤더 작성
        main_sheet_name = "TRAP.육안분석(시뮬결과35_150)" if is_trap else "육안분석(시뮬결과35_150)"
        ws = wb.active
        ws.title = main_sheet_name
        
        headers = ["메시지", "URL", "구분", "분류", "메시지 길이", "URL 길이", "Probability", "Semantic Class", "Reason", "Red Group", "In_Token", "Out_Token"]
        ws.append(headers)
        
        # 헤더 스타일
        header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
            
        unique_urls = {}
        unique_short_urls = {}
        blocklist_data = []
        stats = {"spam_count": 0}
        
        for log_item in logs:
            if log_item.get("result", {}).get("exclude_from_excel"):
                continue
                
            result = log_item.get("result", {})
            msg_val = log_item.get("message", "") # Fallback
            if not msg_val:
                msg_val = result.get("message", "")
                
            url_val = result.get("message_extracted_url", "")
                
            is_spam = result.get("is_spam")
            semantic_class = result.get("semantic_class", "")
            reason_val = result.get("reason", "")
            
            is_type_b = str(semantic_class).startswith("Type_B")
            is_separated = "[텍스트 HAM + 악성 URL 분리 감지" in str(reason_val)
            
            if is_separated:
                gubun_val = ""
                raw_code = str(result.get("classification_code", ""))
                import re
                match = re.search(r'\\d+', raw_code)
                code_val = match.group(0) if match else raw_code
            elif is_type_b or is_spam is True:
                gubun_val = "o"
                stats["spam_count"] += 1
                raw_code = str(result.get("classification_code", ""))
                import re
                match = re.search(r'\\d+', raw_code)
                code_val = match.group(0) if match else raw_code
            else:
                gubun_val = ""
                code_val = ""

            extracted_url_code = ""
            if result.get("malicious_url_extracted"):
                raw_ext_code = str(result.get("url_spam_code", ""))
                m_ext = re.search(r'\\d+', raw_ext_code)
                extracted_url_code = m_ext.group(0) if m_ext else raw_ext_code

            prob_float = result.get("spam_probability", 0.0)
            prob_val = f"{int(float(prob_float) * 100)}%"
            
            # Lengths
            msg_len = self._lenb(msg_val)
            url_len = self._lenb(url_val)
            
            if result.get("drop_url"):
                url_val = ""
                url_len = 0
                
            if is_separated and not url_val:
                url_val = result.get("message_extracted_url", "")
                url_len = self._lenb(url_val)

            in_token_val = result.get("input_tokens", 0)
            out_token_val = result.get("output_tokens", 0)

            # Write Row
            ws.append([
                self._sanitize_cell_value(msg_val), 
                self._sanitize_cell_value(url_val), 
                self._sanitize_cell_value(gubun_val), 
                self._sanitize_cell_value(code_val), 
                msg_len, 
                url_len, 
                self._sanitize_cell_value(prob_val),
                self._sanitize_cell_value(semantic_class),
                self._sanitize_cell_value(reason_val),
                self._sanitize_cell_value("O" if result.get("red_group") else ""),
                in_token_val,
                out_token_val
            ])
            
            if str(code_val) == "3":
                finance_ws = wb["금융.SPAM"] if "금융.SPAM" in wb.sheetnames else wb.create_sheet("금융.SPAM")
                if msg_val:
                    finance_ws.append([self._sanitize_cell_value(msg_val)])
                    
            # --- URL Collection Logic ---
            if (result.get("is_spam") is True or result.get("malicious_url_extracted")) and not result.get("drop_url"):
                target_url = url_val
                is_obfuscated = "[FP Sentinel Override] 도메인 난독화" in str(result.get("reason", ""))
                
                if target_url and not is_obfuscated:
                    target_url = target_url.rstrip('.,;:!?)}\"\\'')
                    
                    if not self.is_short_url(target_url):
                        if target_url not in unique_urls and self._lenb(target_url) <= 40:
                            raw_url_code = str(result.get("classification_code", ""))
                            _m = re.search(r'\\d+', raw_url_code)
                            url_dedup_code = _m.group(0) if _m else raw_url_code
                            if not result.get("is_spam"):
                                url_dedup_code = extracted_url_code
                            unique_urls[target_url] = {
                                "len": self._lenb(target_url),
                                "code": url_dedup_code,
                                "malicious_url_extracted": result.get("malicious_url_extracted", False)
                            }
                    else:
                        if target_url not in unique_short_urls and self._lenb(target_url) <= 40:
                            raw_url_code = str(result.get("classification_code", ""))
                            _m = re.search(r'\\d+', raw_url_code)
                            url_dedup_code = _m.group(0) if _m else raw_url_code
                            if not result.get("is_spam"):
                                url_dedup_code = extracted_url_code
                            unique_short_urls[target_url] = {
                                "len": self._lenb(target_url),
                                "code": url_dedup_code,
                                "malicious_url_extracted": result.get("malicious_url_extracted", False)
                            }
                            
            # --- IBSE Collection Logic ---
            ibse_sig = result.get("ibse_signature")
            if ibse_sig and str(ibse_sig).strip().lower() not in ["none", "unextractable"]:
                clean_sig = str(ibse_sig).replace(" ", "").replace("\\n", "").replace("\\r", "")
                
                raw_ibse_code = str(result.get("classification_code", ""))
                m_ibse = re.search(r'\\d+', raw_ibse_code)
                ibse_code = m_ibse.group(0) if m_ibse else raw_ibse_code
                
                sig_len_raw = result.get("ibse_len")
                sig_len = int(sig_len_raw) if sig_len_raw is not None else self._lenb(clean_sig)
                
                if 20 < sig_len < 39 or sig_len < 9:
                    pass
                else:
                    import re
                    blocklist_data.append({
                        "msg": re.sub(r'[ \\t\\r\\n\\f\\v]+', '', msg_val),
                        "sig": clean_sig,
                        "len": sig_len,
                        "code": ibse_code
                    })

        # Sort & Format
        self._sort_sheet_by_type(ws, headers)
        self._apply_formatting(ws, headers)
        
        # Create sheets
        dedup_sheet_name = "TRAP.URL중복 제거" if is_trap else "URL중복 제거"
        self._create_dedup_sheet(wb, unique_urls, unique_short_urls, sheet_name=dedup_sheet_name)
        
        blocklist_sheet_name = "TRAP.문자문장차단등록" if is_trap else "문자문장차단등록"
        self._create_blocklist_sheet(wb, blocklist_data, sheet_name=blocklist_sheet_name)
        
        sheet_name_str = "TRAP.문자열 중복제거" if is_trap else "문자열중복제거"
        sheet_name_sen = "TRAP.문장 중복제거" if is_trap else "문장중복제거"
        str_cnt, sen_cnt = self._create_split_dedup_sheets(wb, blocklist_data, sheet_name_str, sheet_name_sen)
        
        url_cnt = len(unique_urls) + len(unique_short_urls)
        actual_spam_cnt = stats["spam_count"]
        self._update_summary_table(wb, is_trap, original_filename or "generated.xlsx", actual_spam_cnt, url_cnt, str_cnt, sen_cnt)
        
        wb.save(output_path)
        return {"success": True, "output_path": output_path, "filename": original_filename, "total_rows": len(logs)}"""

    new_content = content[:start_idx] + new_method + content[end_idx:]
    
    with open('app/utils/excel_handler.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
        print("Replaced method correctly.")

if __name__ == '__main__':
    refactor()
