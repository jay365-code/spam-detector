import re

file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\tagging_org_20260320_C\kisa_20260320_C_result_hamMsg_url.txt'

with open(file_path, 'rb') as f:
    raw_data = f.read()

decoded_text = raw_data.decode('cp949', errors='replace')
lines = decoded_text.splitlines()

print(f"Total lines: {len(lines)}")

rows = []
for i, line in enumerate(lines):
    line = line.strip()
    if not line: continue
    parts = line.split('\t')
        
    msg_body = parts[0] if len(parts) > 0 else ""
    
    if "가" in msg_body and "m" in msg_body and "g" in msg_body:
        print(f"[{i}] MATCHED msg_body: {repr(msg_body)}")
        
print("Done")
