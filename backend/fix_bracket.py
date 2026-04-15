import sys

def patch():
    with open('app/utils/excel_handler.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for idx, line in enumerate(lines):
        if line.strip() == "}":
            print(f"Found rogue bracket at line {idx+1}")
            lines[idx] = ""
            
    with open('app/utils/excel_handler.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
patch()
