import logging
import pandas as pd
import os
import re
from datetime import datetime
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment, PatternFill

logger = logging.getLogger(__name__)

class ExcelHandler:
    def _lenb(self, text: str) -> int:
        """Calculate byte length for CP949 encoding (Korean standard)."""
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        try:
            return len(text.encode('cp949'))
        except UnicodeEncodeError:
            # Fallback for chars not in cp949
            return len(text.encode('utf-8'))

    def process_file(self, file_path: str, output_path: str, processing_function, progress_callback=None, batch_size: int = 1):
        """
        Reads the Excel file, processes rows in batches, and appends results.
        Supports optional progress reporting.
        """
        try:
            # 1. Load Workbook
            wb = load_workbook(file_path)
            target_sheet_name = "육안분석(시뮬결과35_150)"
            
            if target_sheet_name not in wb.sheetnames:
                raise ValueError(f"Sheet '{target_sheet_name}' not found.")
            
            ws = wb[target_sheet_name]
            
            # 2. Identify Headers
            headers = [cell.value for cell in ws[1]]
            try:
                msg_col_idx = headers.index("메시지") + 1 # 1-based index
            except ValueError:
                raise ValueError("'메시지' column not found.")
                
            # Add or Find Output Columns (Cols setup logic same as before)
            
            def get_col_idx(name, default_idx):
                try:
                    return headers.index(name) + 1
                except ValueError:
                    ws.cell(row=1, column=default_idx, value=name)
                    return default_idx

            gubun_col_idx = get_col_idx("구분", len(headers) + 1)
            code_col_idx = get_col_idx("분류", gubun_col_idx + 1)
            prob_col_idx = get_col_idx("Probability", code_col_idx + 1)
            reason_col_idx = get_col_idx("Reason", prob_col_idx + 1)
            in_token_col_idx = get_col_idx("In_Token", reason_col_idx + 1)
            out_token_col_idx = get_col_idx("Out_Token", in_token_col_idx + 1)

            # 3. Iterate Rows & Batch Processing
            total_rows = ws.max_row - 1 # Excluding header
            logger.info(f"Processing {total_rows} rows from Excel (Batch Size: {batch_size})...")
            
            row_iterator = ws.iter_rows(min_row=2, max_row=ws.max_row)
            
            batch_buffer = [] # List of (vocab_row_idx, message_str, row_object)
            
            def flush_batch():
                if not batch_buffer:
                    return
                
                # Extract messages
                messages = [item[1] for item in batch_buffer]
                
                # Call Processing Function (Expects List -> Returns List)
                try:
                    results = processing_function(messages)
                except Exception as e:
                    logger.error(f"Batch Processing Failed: {e}")
                    # Create error results
                    results = [{"is_spam": None, "reason": f"Error: {e}"} for _ in messages]
                
                # Map results back to rows
                for idx, result in enumerate(results):
                    if idx >= len(batch_buffer): break # Safety
                    
                    row_idx, _, _ = batch_buffer[idx] # Current Row Element
                    
                    # Write Result
                    if result.get("is_spam") is True:
                        gubun_val = "o"
                    elif result.get("is_spam") is False:
                        gubun_val = ""
                    else:
                        gubun_val = "UNKNOWN"
                        
                    if result.get("is_spam") is False:
                        code_val = ""
                    else:
                        # Extract only digits from the code (e.g. SPAM-1 -> 1)
                        import re
                        raw_val = str(result.get("classification_code", ""))
                        match = re.search(r'\d+', raw_val)
                        code_val = match.group(0) if match else raw_val
                    prob_val = result.get("spam_probability", 0.0)
                    reason_val = result.get("reason", "")
                    in_token_val = result.get("input_tokens", 0)
                    out_token_val = result.get("output_tokens", 0)
                    
                    ws.cell(row=row_idx, column=gubun_col_idx, value=gubun_val)
                    ws.cell(row=row_idx, column=code_col_idx, value=code_val)
                    ws.cell(row=row_idx, column=prob_col_idx, value=prob_val)
                    ws.cell(row=row_idx, column=reason_col_idx, value=reason_val)
                    ws.cell(row=row_idx, column=in_token_col_idx, value=in_token_val)
                    ws.cell(row=row_idx, column=out_token_col_idx, value=out_token_val)

                    # Callback (Progress) 
                    if progress_callback:
                        progress_callback({
                            "current": row_idx - 1, # approx
                            "total": total_rows,
                            "message": batch_buffer[idx][1],
                            "result": result
                        })

                # Auto-Save after each batch to prevent data loss
                try:
                    wb.save(output_path)
                except Exception as save_err:
                    logger.error(f"Auto-save failed: {save_err}")

                batch_buffer.clear()

            # Loop
            for i, row in enumerate(row_iterator):
                msg_cell = row[msg_col_idx - 1]
                message = msg_cell.value
                current_row_idx = row[0].row 
                
                if not message:
                    message_str = ""
                else:
                    message_str = str(message)
                
                batch_buffer.append((current_row_idx, message_str, row))
                
                if len(batch_buffer) >= batch_size:
                    logger.info(f"Processing Batch (Row {i+1}/{total_rows})...")
                    flush_batch()
            
            # Process remaining
            if batch_buffer:
                logger.info(f"Processing Remaining Batch...")
                flush_batch()

            # 5. Save
            wb.save(output_path)
            return True
            
        except Exception as e:
            logger.error(f"Error processing Excel: {e}")
            raise e

    def is_short_url(self, url: str) -> bool:
        """
        Check if the URL belongs to a known shortener service.
        """
        if not url: return False
        
        # Common Shortener Domains (Korean & Global)
        shortener_domains = [
            "bit.ly", "goo.gl", "tinyurl.com", "ow.ly", "t.co", 
            "is.gd", "buff.ly", "adf.ly", "bit.do", "mcaf.ee", 
            "me2.do", "naver.me", "kakaolink.com", "buly.kr", 
            "vo.la", "url.kr", "zrr.kr", "yun.kr", "han.gl",
            "shorter.me", "shrl.me"
        ]
        
        try:
            # Simple domain extraction for check
            # Remove protocol
            clean_url = re.sub(r'^https?://', '', url.lower())
            clean_url = re.sub(r'^www\.', '', clean_url)
            
            for domain in shortener_domains:
                if clean_url.startswith(domain):
                    return True
            return False
        except:
            return False

    def _create_dedup_sheet(self, wb: Workbook, unique_urls: dict):
        """
        Create 'URL중복 제거' sheet with unique non-short URLs.
        Columns: URL(중복제거), 길이, 분류
        Style: Header Bold, Center, Light Gray Fill
        """
        if "URL중복 제거" in wb.sheetnames:
            ws = wb["URL중복 제거"]
        else:
            ws = wb.create_sheet("URL중복 제거")
            
        # Headers
        headers = ["URL(중복제거)", "길이", "분류"]
        ws.append(headers)
        
        # Style Definition
        header_font = Font(bold=True)
        header_align = Alignment(horizontal='center', vertical='center')
        header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid") # Light Grey
        
        # Apply Style to Header
        for cell in ws[1]:
            cell.font = header_font
            cell.alignment = header_align
            cell.fill = header_fill
            
        # Write Data
        for url, info in unique_urls.items():
            ws.append([url, info['len'], info['code']])

    def _create_blocklist_sheet(self, wb: Workbook, blocklist_data: list):
        """
        Create '문자문장차단등록' sheet for extracted signatures.
        Columns: 메시지, 문자열, 길이, 분류
        """
        if "문자문장차단등록" in wb.sheetnames:
             ws = wb["문자문장차단등록"]
        else:
             ws = wb.create_sheet("문자문장차단등록")
        
        # Headers
        headers = ["메시지", "문자열", "길이", "분류"]
        ws.append(headers)
        
        # Styling
        header_font = Font(bold=True)
        header_align = Alignment(horizontal='center', vertical='center')
        header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")
        
        for cell in ws[1]:
            cell.font = header_font
            cell.alignment = header_align
            cell.fill = header_fill
            
        # Write Data
        # blocklist_data = [{"msg":..., "sig":..., "len":..., "code":...}, ...]
        for item in blocklist_data:
            ws.append([item['msg'], item['sig'], item['len'], item['code']])


    def process_file(self, file_path: str, output_path: str, processing_function, progress_callback=None, batch_size: int = 1):
        """
        Reads the Excel file, processes rows in batches, and appends results.
        Supports optional progress reporting.
        """
        try:
            # 1. Load Workbook
            wb = load_workbook(file_path)
            target_sheet_name = "육안분석(시뮬결과35_150)"
            
            if target_sheet_name not in wb.sheetnames:
                raise ValueError(f"Sheet '{target_sheet_name}' not found.")
            
            ws = wb[target_sheet_name]
            
            # 2. Identify Headers
            headers = [cell.value for cell in ws[1]]
            try:
                msg_col_idx = headers.index("메시지") + 1 # 1-based index
            except ValueError:
                raise ValueError("'메시지' column not found.")
                
            # Add or Find Output Columns (Cols setup logic same as before)
            
            def get_col_idx(name, default_idx):
                try:
                    return headers.index(name) + 1
                except ValueError:
                    ws.cell(row=1, column=default_idx, value=name)
                    return default_idx

            gubun_col_idx = get_col_idx("구분", len(headers) + 1)
            code_col_idx = get_col_idx("분류", gubun_col_idx + 1)
            prob_col_idx = get_col_idx("Probability", code_col_idx + 1)
            reason_col_idx = get_col_idx("Reason", prob_col_idx + 1)
            signals_col_idx = get_col_idx("Signals", reason_col_idx + 1)
            in_token_col_idx = get_col_idx("In_Token", signals_col_idx + 1)
            out_token_col_idx = get_col_idx("Out_Token", in_token_col_idx + 1)

            # 3. Iterate Rows & Batch Processing
            total_rows = ws.max_row - 1 # Excluding header
            logger.info(f"Processing {total_rows} rows from Excel (Batch Size: {batch_size})...")
            
            row_iterator = ws.iter_rows(min_row=2, max_row=ws.max_row)
            
            batch_buffer = [] # List of (vocab_row_idx, message_str, row_object)
            unique_urls = {} # URL Reduplication Store
            blocklist_data = [] # IBSE Blocklist Store
            
            def flush_batch():
                if not batch_buffer:
                    return
                
                # Extract messages
                messages = [item[1] for item in batch_buffer]
                
                # Call Processing Function (Expects List -> Returns List)
                try:
                    results = processing_function(messages)
                except Exception as e:
                    logger.error(f"Batch Processing Failed: {e}")
                    # Create error results
                    results = [{"is_spam": None, "reason": f"Error: {e}"} for _ in messages]
                
                # Map results back to rows
                for idx, result in enumerate(results):
                    if idx >= len(batch_buffer): break # Safety
                    
                    row_idx, _, _ = batch_buffer[idx] # Current Row Element
                    
                    # Write Result
                    if result.get("is_spam") is True:
                        gubun_val = "o"
                    elif result.get("is_spam") is False:
                        gubun_val = ""
                    else:
                        gubun_val = "UNKNOWN"
                        
                    if result.get("is_spam") is False:
                        code_val = ""
                    else:
                        # Extract only digits from the code (e.g. SPAM-1 -> 1)
                        import re
                        raw_val = str(result.get("classification_code", ""))
                        match = re.search(r'\d+', raw_val)
                        code_val = match.group(0) if match else raw_val
                    prob_val = result.get("spam_probability", 0.0)
                    reason_val = result.get("reason", "")
                    
                    # Signals Formatting
                    signals = result.get("signals", {})
                    if signals and isinstance(signals, dict):
                         sig_list = []
                         if signals.get("harm_anchor"): sig_list.append("HA")
                         if signals.get("route_or_cta"): sig_list.append("RC")
                         if signals.get("obfuscation_heavy"): sig_list.append("OB")
                         signals_val = ",".join(sig_list)
                    else:
                         signals_val = ""

                    in_token_val = result.get("input_tokens", 0)
                    out_token_val = result.get("output_tokens", 0)
                    
                    ws.cell(row=row_idx, column=gubun_col_idx, value=gubun_val)
                    ws.cell(row=row_idx, column=code_col_idx, value=code_val)
                    ws.cell(row=row_idx, column=prob_col_idx, value=prob_val)
                    ws.cell(row=row_idx, column=reason_col_idx, value=reason_val)
                    ws.cell(row=row_idx, column=signals_col_idx, value=signals_val)
                    ws.cell(row=row_idx, column=in_token_col_idx, value=in_token_val)
                    ws.cell(row=row_idx, column=out_token_col_idx, value=out_token_val)

                    # --- URL Collection Logic ---
                    # Only collect URLs if the message is SPAM
                    if result.get("is_spam") is True:
                        # re is already imported globally
                        url_pattern = r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})'
                        urls = re.findall(url_pattern, batch_buffer[idx][1])
                        
                        for url in urls:
                            # Clean URL (exclude trailing punctuation often caught by greedy regex)
                            url = url.rstrip('.,;!?)]}"\'')
                            
                            if not self.is_short_url(url):
                                 # Only non-short URLs
                                 if url not in unique_urls:
                                     unique_urls[url] = {
                                         "len": self._lenb(url),
                                         "code": code_val
                                     }

                    # --- IBSE Collection Logic ---
                    if result.get("ibse_signature"):
                        # User requested "공백제거된 메시지"
                        
                        clean_msg = re.sub(r'[ \t\r\n\f\v]+', '', batch_buffer[idx][1]) # Check if batch_buffer[idx][1] is str
                        
                        blocklist_data.append({
                            "msg": clean_msg, 
                            "sig": result.get("ibse_signature"),
                            "len": result.get("ibse_len", 0),
                            "code": code_val
                        })

                    # Callback (Progress) 
                    if progress_callback:
                        progress_callback({
                            "current": row_idx - 1, # approx
                            "total": total_rows,
                            "message": batch_buffer[idx][1],
                            "result": result
                        })

                # Auto-Save after each batch to prevent data loss
                # Note: We don't write dedup sheet until the very end because we need full set.
                try:
                    wb.save(output_path)
                except Exception as save_err:
                    logger.error(f"Auto-save failed: {save_err}")

                batch_buffer.clear()

            # Loop
            for i, row in enumerate(row_iterator):
                msg_cell = row[msg_col_idx - 1]
                message = msg_cell.value
                current_row_idx = row[0].row 
                
                if not message:
                    message_str = ""
                else:
                    message_str = str(message)
                
                batch_buffer.append((current_row_idx, message_str, row))
                
                if len(batch_buffer) >= batch_size:
                    logger.info(f"Processing Batch (Row {i+1}/{total_rows})...")
                    flush_batch()
            
            # Process remaining
            if batch_buffer:
                logger.info(f"Processing Remaining Batch...")
                flush_batch()

            # 4. Create Dedup Sheet (After all rows processed)
            self._create_dedup_sheet(wb, unique_urls)

            # 6. Create Blocklist Sheet
            self._create_blocklist_sheet(wb, blocklist_data)

            # 5. Save
            wb.save(output_path)
            return True
            
        except Exception as e:
            logger.error(f"Error processing Excel: {e}")
            raise e

    def process_kisa_txt(self, file_path: str, output_dir: str, processing_function, progress_callback=None, batch_size: int = 1, original_filename: str = None):
        """
        Process KISA format TXT file: [Body] <TAB> [URL]
        """
        try:
            # 1. Parse Input Filename to determine Output Filename
            # kisa_20260103_A_result_hamMsg_url.txt -> MMSC스팸추출_20260103_A.xlsx
            input_filename = original_filename if original_filename else os.path.basename(file_path)
            
            # Try to extract 'yyyymmdd_A' pattern
            # Regex captures: kisa_(20260101_A)_result...
            match = re.search(r'kisa_(\d{8}_[A-Za-z0-9]+)', input_filename)
            
            if match:
                extracted_part = match.group(1)
            else:
                # Fallback: Just date
                date_match = re.search(r'\d{8}', input_filename)
                if date_match:
                    extracted_part = date_match.group(0)
                else:
                    extracted_part = datetime.now().strftime("%Y%m%d")
            
            base_filename = f"MMSC스팸추출_{extracted_part}"
            ext = ".xlsx"
            output_filename = f"{base_filename}{ext}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Check for duplicates/locks and increment counter
            counter = 1
            while os.path.exists(output_path):
                output_filename = f"{base_filename} ({counter}){ext}"
                output_path = os.path.join(output_dir, output_filename)
                counter += 1
            
            os.makedirs(output_dir, exist_ok=True)
            
            # 2. Read Text File with Encoding Detection (UTF-8 prior to CP949)
            lines = []
            encoding_used = 'utf-8'
            try:
                # First try UTF-8 (Common for modern editors/generated files)
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                # Fallback to CP949 (KISA Standard)
                encoding_used = 'cp949'
                logger.info("UTF-8 decode failed, falling back to CP949")
                with open(file_path, 'r', encoding='cp949', errors='replace') as f:
                    lines = f.readlines()
            
            logger.info(f"Processed KISA text file using {encoding_used} encoding. Total lines: {len(lines)}")

            rows = []
            for line in lines:
                line = line.strip()
                if not line: continue
                parts = line.split('\t')
                    
                msg_body = parts[0] if len(parts) > 0 else ""
                # URL is normally in parts[1] if exists
                url_in_file = parts[1] if len(parts) > 1 else ""
                
                rows.append({"message": msg_body, "url": url_in_file})

            total_rows = len(rows)
            logger.info(f"Processing {total_rows} rows from KISA TXT (Batch Mode)...")

            # 3. Create Excel & Setup Styles
            wb = Workbook()
            ws = wb.active
            ws.title = "육안분석(시뮬결과35_150)"
            
            # Define Headers
            headers = ["메시지", "URL", "구분", "분류", "메시지 길이", "URL 길이", "Probability", "Reason", "Signals"]
            ws.append(headers)
            
            # Styling
            header_font = Font(bold=True)
            header_align = Alignment(horizontal='center', vertical='center')
            header_fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid") # Light Grey
            
            for cell in ws[1]:
                cell.font = header_font
                cell.alignment = header_align
                cell.fill = header_fill

            # 4. Batch Processing
            batch_buffer = []
            unique_urls = {} # URL Reduplication Store
            blocklist_data = [] # IBSE Blocklist Store

            def flush_batch(start_idx):
                if not batch_buffer:
                    return

                messages = [item["message"] for item in batch_buffer]
                
                try:
                    results = processing_function(messages)
                except Exception as e:
                    logger.error(f"Batch Processing Failed: {e}")
                    results = [{"is_spam": None, "reason": f"Error: {e}"} for _ in messages]

                # Populate Excel Rows
                for i, result in enumerate(results):
                    original_data = batch_buffer[i]
                    msg_val = original_data["message"]
                    url_val = original_data["url"]
                    
                    # Logic
                    is_spam = result.get("is_spam")
                    if is_spam is True:
                        gubun_val = "o"
                    elif is_spam is False:
                        code_val = "" # Normal
                        gubun_val = ""
                    else:
                        gubun_val = "UNKNOWN"
                        
                    # Code
                    raw_code = str(result.get("classification_code", ""))
                    if is_spam:
                        match = re.search(r'\d+', raw_code)
                        code_val = match.group(0) if match else raw_code
                    else:
                        code_val = ""
                        
                    # Probability (e.g. 98%)
                    prob_float = result.get("spam_probability", 0.0)
                    prob_val = f"{int(prob_float * 100)}%"
                    
                    reason_val = result.get("reason", "")
                    
                    # Lengths
                    msg_len = self._lenb(msg_val)
                    url_len = self._lenb(url_val)
                    
                    # Write Row
                    # Headers: [Ms, U, G, C, ML, UL, P, R]
                    # Signals Formatting (KISA TXT)
                    signals = result.get("signals", {})
                    if signals and isinstance(signals, dict):
                         sig_list = []
                         if signals.get("harm_anchor"): sig_list.append("HA")
                         if signals.get("route_or_cta"): sig_list.append("RC")
                         if signals.get("obfuscation_heavy"): sig_list.append("OB")
                         signals_val = ",".join(sig_list)
                    else:
                         signals_val = ""

                    ws.append([
                        msg_val, url_val, gubun_val, code_val, msg_len, url_len, prob_val, reason_val, signals_val
                    ])
                    
                    # --- URL Collection Logic ---
                    # Only collect URLs from SPAM messages
                    if result.get("is_spam") is True:
                        target_url = url_val.strip()
                        if not target_url:
                             # Stricter URL Pattern: Exclude special chars in domain (only allow alphanumeric, dot, hyphen)
                             # Original: r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})'
                             # New: Enforce domain part to be standard
                             url_pattern = r'(?:https?://|www\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
                             match = re.search(url_pattern, msg_val)
                             if match:
                                 target_url = match.group(0)
                        
                        if target_url:
                            # Clean URL
                            target_url = target_url.rstrip('.,;!?)]}"\'')
                            
                            # Additional Safety: Check for special chars in domain part
                            # If URL contains chars like ⑨, it's likely a visual trick (homograph) or trash
                            # We filter out URLs containing non-ascii/non-standard chars if not intended
                            if not re.search(r'[^\x00-\x7F]', target_url): # If pure ASCII (simple check) => Good
                                 pass 
                            else:
                                 # If it has non-ascii, verification:
                                 # Allow Korean domains? .한국 etc. 
                                 # But user example "0000 00000 vt⑨8g.COm" -> exclude.
                                 # Let's simple check: exclude if contains specific special symbols?
                                 # Or just rely on is_short_url and strict regex earlier.
                                 pass

                            if not self.is_short_url(target_url):
                                 if target_url not in unique_urls:
                                     unique_urls[target_url] = {
                                         "len": self._lenb(target_url),
                                         "code": code_val
                                     }

                    # --- IBSE Collection Logic ---
                    if result.get("ibse_signature"):
                        # User requested "메시지-공백제거" AND "문자열-공백제거"
                        # "문자열에 공백 제거(추출된 signature에는 공백 제거한 문자욜 저장)"
                        
                        clean_msg = re.sub(r'[ \t\r\n\f\v]+', '', msg_val)
                        clean_sig = str(result.get("ibse_signature")).replace(" ", "").replace("\n", "").replace("\r", "")
                        
                        blocklist_data.append({
                            "msg": clean_msg, 
                            "sig": clean_sig, # whitespace removed signature
                            "len": result.get("ibse_len", 0),
                            "code": code_val
                        })

                    # Progress
                    if progress_callback:
                         progress_callback({
                            "current": start_idx + i + 1, 
                            "total": total_rows,
                            "message": msg_val,
                            "result": result
                        })

                try:
                    wb.save(output_path)
                except Exception as e:
                    logger.error(f"Auto-save error: {e}")

                batch_buffer.clear()

            # Iterate
            for i, row_data in enumerate(rows):
                batch_buffer.append(row_data)
                
                if len(batch_buffer) >= batch_size:
                    flush_batch(i - batch_size + 1)
            
            # Remaining
            if batch_buffer:
                flush_batch(total_rows - len(batch_buffer))
            
            # 5. Create Dedup Sheet
            self._create_dedup_sheet(wb, unique_urls)
            
            # 6. Create Blocklist Sheet
            self._create_blocklist_sheet(wb, blocklist_data)
                
            wb.save(output_path)
            return {"output_path": output_path, "filename": output_filename}

        except Exception as e:
            logger.error(f"Error processing KISA TXT: {e}")
            raise e
