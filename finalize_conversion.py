
import os
import time

original = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\tagging_org_20260106_C\kisa_20260106_C_result_hamMsg_url.txt'
converted = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\tagging_org_20260106_C\kisa_20260106_C_result_hamMsg_url_utf8.txt'

try:
    # Try to replace
    if os.path.exists(original):
        os.remove(original)
    
    os.rename(converted, original)
    print(f"Successfully replaced {original} with UTF-8 version")

except Exception as e:
    print(f"Error replacing file: {e}")
