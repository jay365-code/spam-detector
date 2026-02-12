
import sys

file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\tagging_org_20260106_C\kisa_20260106_C_result_hamMsg_url.txt'

try:
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    # Try decoding as UTF-8
    try:
        raw_data.decode('utf-8')
        print("UTF-8")
    except UnicodeDecodeError:
        pass
        
    # Try decoding as EUC-KR
    try:
        raw_data.decode('euc-kr')
        print("EUC-KR")
    except UnicodeDecodeError:
        pass
        
    # Try decoding as CP949
    try:
        raw_data.decode('cp949')
        print("CP949")
    except UnicodeDecodeError:
        pass

except Exception as e:
    print(f"Error: {e}")
