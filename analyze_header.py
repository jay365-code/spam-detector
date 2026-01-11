
import sys

# Reconfigure stdout to utf-8 just in case
sys.stdout.reconfigure(encoding='utf-8')

file_path = 'docs/kisa_20260103_A_result_hamMsg_url.txt'

try:
    with open(file_path, 'r', encoding='cp949') as f:
        print("--- START OF FILE ---")
        for i in range(10):
            line = f.readline()
            if not line:
                break
            print(f"Line {i}: {repr(line)}")
        print("--- END OF FILE ---")
except Exception as e:
    print(f"Error: {e}")
