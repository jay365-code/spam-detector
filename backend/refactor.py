import sys

def refactor():
    with open('app/main.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Replace ExcelRowUpdate with RegenerateExcelRequest
        if "class ExcelRowUpdate(BaseModel):" in line:
            out.append("class RegenerateExcelRequest(BaseModel):\n")
            out.append('    """엑셀 전체 재생성 요청"""\n')
            out.append("    filename: str\n")
            out.append("    is_trap: bool = False\n")
            out.append("    logs: list[dict] = []\n\n")
            
            # skip until we see TextRequest
            while i < len(lines) and "class TextRequest" not in lines[i]:
                i += 1
            continue
            
        # Replace update_excel_row with regenerate_excel
        if "@app.put(\"/api/excel/update-row\")" in line:
            new_endpoint = """@app.post("/api/excel/regenerate")
async def regenerate_excel(req: RegenerateExcelRequest):
    \"\"\"프론트엔드의 최종 상태(logs)를 전체 전달받아 엑셀 파일을 백지에서 새로 생성합니다.\"\"\"
    try:
        from fastapi.responses import FileResponse
        # 1. 파일명 분석 및 경로 설정
        base_filename = req.filename
        if not base_filename.endswith('.xlsx'):
            base_filename += '.xlsx'
        output_path = os.path.join(OUTPUT_DIR, base_filename)
        
        # 기존 파일 덮어쓰기를 피하려면 백업하거나 새 이름을 부여할 수도 있으나, Save As 개념이므로 동일하게 덮어씁니다.
        # 2. 엑셀 생성기 호출
        result = excel_handler.generate_excel_from_json(
            logs=req.logs,
            output_path=output_path,
            is_trap=req.is_trap,
            original_filename=base_filename
        )
        
        # 3. 완성된 엑셀 파일 다운로드 응답 반환
        return FileResponse(
            path=output_path,
            filename=base_filename,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        logger.error(f"Error regenerating Excel: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""
            out.append(new_endpoint)
            # Skip until we hit download /{filename}
            while i < len(lines) and "@app.get(\"/download/{filename}\")" not in lines[i]:
                i += 1
            continue
            
        out.append(line)
        i += 1
        
    with open('app/main.py', 'w', encoding='utf-8') as f:
        f.writelines(out)

if __name__ == '__main__':
    refactor()
