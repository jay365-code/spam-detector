
import sys

file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\tagging_org_20260106_C\kisa_20260106_C_result_hamMsg_url.txt'

try:
    # Read as EUC-KR (or CP949 which is a superset)
    with open(file_path, 'r', encoding='cp949') as f:
        content = f.read()
    
    # Write as UTF-8
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f"Successfully converted {file_path} to UTF-8")

except Exception as e:
    print(f"Error converting file: {e}")
