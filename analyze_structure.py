
import sys

sys.stdout.reconfigure(encoding='utf-8')

file_path = 'docs/kisa_20260103_A_result_hamMsg_url.txt'

try:
    with open(file_path, 'r', encoding='cp949', errors='replace') as f:
        found_count = 0
        for i, line in enumerate(f):
            if 'http' in line:
                print(f"Line {i}: {repr(line)}")
                found_count += 1
                if found_count >= 10:
                    break
except Exception as e:
    print(f"Error: {e}")
