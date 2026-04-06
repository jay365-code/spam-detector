import re

with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\backend\app\utils\excel_handler.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. 육안분석 (size 10.5)
text = text.replace('base_font = Font(name="맑은 고딕", size=11.0)', 'base_font = Font(name="맑은 고딕", size=10.5)', 1)
text = text.replace('msg_font = Font(name="맑은 고딕", size=11.0)', 'msg_font = Font(name="맑은 고딕", size=10.5)', 1)
text = text.replace('header_font = Font(name="맑은 고딕", bold=True, size=11.0)', 'header_font = Font(name="맑은 고딕", bold=True, size=10.5)', 1)

# column widths in _create_analysis_sheet
text = re.sub(
    r"ws\.column_dimensions\[get_column_letter\(msg_col\)\].width = 90.*?ws\.column_dimensions\[get_column_letter\(reason_col\)\].width = 90",
    "ws.column_dimensions[get_column_letter(msg_col)].width = 89.625\n        ws.column_dimensions[get_column_letter(url_col)].width = 21.625\n        ws.column_dimensions[get_column_letter(msg_len_col)].width = 13.625\n        ws.column_dimensions[get_column_letter(prob_col)].width = 13.0\n        ws.column_dimensions[get_column_letter(semantic_col)].width = 13.0\n        ws.column_dimensions[get_column_letter(reason_col)].width = 40.625",
    text, flags=re.DOTALL
)

# 2. _create_dedup_sheet (URL)
text = re.sub(
    r"ws\.column_dimensions\[get_column_letter\(1\)\].width = 42\.5\s*ws\.column_dimensions\[get_column_letter\(20\)\].width = 42\.5",
    "ws.column_dimensions[get_column_letter(1)].width = 25.625\n        ws.column_dimensions[get_column_letter(2)].width = 10.625\n        ws.column_dimensions[get_column_letter(3)].width = 13.0\n        ws.column_dimensions[get_column_letter(20)].width = 25.625\n        ws.column_dimensions[get_column_letter(21)].width = 10.625\n        ws.column_dimensions[get_column_letter(22)].width = 13.0",
    text
)

# 3. _create_blocklist_sheet (문자문장차단등록)
text = re.sub(
    r"ws\.column_dimensions\[get_column_letter\(1\)\].width = 114\.4.*?ws\.column_dimensions\[get_column_letter\(6\)\].width = 10.*?# 분류",
    "ws.column_dimensions[get_column_letter(1)].width = 65.625  # 메시지\n        ws.column_dimensions[get_column_letter(2)].width = 25.625   # 문자열\n        ws.column_dimensions[get_column_letter(3)].width = 19.625     # 문자열 길이\n        ws.column_dimensions[get_column_letter(4)].width = 10.625   # 문장열\n        ws.column_dimensions[get_column_letter(5)].width = 40.625     # 문장열 길이\n        ws.column_dimensions[get_column_letter(6)].width = 10.625     # 분류",
    text, flags=re.DOTALL
)

# 4. 시뮬결과전체 
text = re.sub(
    r"sim_ws\.column_dimensions\['A'\].width = 100.*?sim_ws\.column_dimensions\['E'\].width = 15.*?# URL길이",
    "sim_ws.column_dimensions['A'].width = 81.0\n        sim_ws.column_dimensions['B'].width = 25.625\n        sim_ws.column_dimensions['C'].width = 10.625\n        sim_ws.column_dimensions['D'].width = 11.88\n        sim_ws.column_dimensions['E'].width = 11.88",
    text, flags=re.DOTALL
)

# 5. _create_split_dedup_sheets (문자열 중복, 문장 중복)
text = re.sub(
    r"c_ws\.column_dimensions\['A'\].width = 80\s*c_ws\.column_dimensions\['B'\].width = 10\s*c_ws\.column_dimensions\['C'\].width = 10",
    "if '문장' in sheet_name_str:\n            c_ws.column_dimensions['A'].width = 40.625\n            c_ws.column_dimensions['B'].width = 10.625\n            c_ws.column_dimensions['C'].width = 13.0\n            c_ws.column_dimensions['D'].width = 13.0\n            c_ws.column_dimensions['E'].width = 12.625\n            c_ws.column_dimensions['F'].width = 10.625\n        else:\n            c_ws.column_dimensions['A'].width = 25.625\n            c_ws.column_dimensions['B'].width = 10.625\n            c_ws.column_dimensions['C'].width = 13.0",
    text
)

# 6. Global replace size=11 back to None where needed? No, 11.0 is correct for others!

with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\backend\app\utils\excel_handler.py', 'w', encoding='utf-8') as f:
    f.write(text)

