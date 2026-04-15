import sys

def patch():
    with open('app/utils/excel_handler.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the function to replace
    start_tag = "    def generate_excel_from_json(self, logs: list, output_path: str, is_trap: bool, original_filename: str = None) -> dict:"
    start_idx = content.find(start_tag)
    if start_idx == -1:
        print("start_tag not found")
        sys.exit(1)
        
    end_tag = "        return {\"success\": True, \"output_path\": output_path, \"filename\": original_filename, \"total_rows\": len(logs)}\n"
    end_idx = content.find(end_tag, start_idx) + len(end_tag)

    if end_idx < len(end_tag):
        print("end_tag not found")
        sys.exit(1)

    old_func = content[start_idx:end_idx]

    # The helper body is basically the old body starting from "# 2. 메인 시트 접근"
    # But wait! I can just use string replacement on old_func!
    # old_func has everything from `def generate_excel...` to `return {success...}`
    
    # 1. We split old_func at `# 2. 메인 시트 접근`
    split_str = "        # 2. 메인 시트 접근\n"
    split_idx = old_func.find(split_str)
    
    header_part = old_func[:split_idx]
    body_part = old_func[split_idx:]
    
    # body_part ends with:
    #         wb.save(output_path)
    #         return {"success": True, "output_path": output_path, "filename": original_filename, "total_rows": len(logs)}
    # Let's remove those 2 lines from body_part since they belong to original generate_excel_from_json
    
    save_str = "        wb.save(output_path)\n"
    save_idx = body_part.find(save_str)
    helper_body = body_part[:save_idx]
    
    # Now build new functions
    new_generate = """    def generate_excel_from_json(self, logs: list, output_path: str, is_trap_unused: bool, original_filename: str = None) -> dict:
        \"\"\"
        Re-generate the Excel file entirely from the UI's JSON state (logs).
        Splits data automatically into KISA and TRAP sheets based on individual log item's 'is_trap' flag.
        \"\"\"
        # 1. 템플릿 생성 및 로딩 (14개 기본 시트 보존)
        self.create_template_workbook(output_path)
        wb = load_workbook(output_path)
        
        logs_kisa = [l for l in logs if not l.get("is_trap")]
        logs_trap = [l for l in logs if l.get("is_trap")]
        
        if logs_kisa:
            self._populate_workbook_with_logs(wb, logs_kisa, False, original_filename)
            
        if logs_trap:
            self._populate_workbook_with_logs(wb, logs_trap, True, original_filename)
            
        wb.save(output_path)
        return {"success": True, "output_path": output_path, "filename": original_filename, "total_rows": len(logs)}

    def _populate_workbook_with_logs(self, wb, logs: list, is_trap: bool, original_filename: str = None):
"""
    
    new_code = new_generate + helper_body

    final_content = content[:start_idx] + new_code + content[end_idx:]

    with open('app/utils/excel_handler.py', 'w', encoding='utf-8') as f:
        f.write(final_content)

    print("Success")

patch()
