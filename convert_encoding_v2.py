
import sys
import os

file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\tagging_org_20260106_C\kisa_20260106_C_result_hamMsg_url.txt'
new_file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\tagging_org_20260106_C\kisa_20260106_C_result_hamMsg_url_utf8.txt'

try:
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        sys.exit(1)

    with open(file_path, 'r', encoding='cp949') as f:
        content = f.read()
    
    with open(new_file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f"Successfully converted to {new_file_path}")

except Exception as e:
    print(f"Error: {e}")
