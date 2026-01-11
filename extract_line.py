
import sys

file_path = 'docs/kisa_20260103_A_result_hamMsg_url.txt'
out_path = 'debug_line.txt'

try:
    with open(file_path, 'r', encoding='cp949', errors='replace') as f:
        for idx, line in enumerate(f):
            if 'http' in line:
                with open(out_path, 'w', encoding='utf-8') as out_f:
                    out_f.write(f"Line {idx}:\n")
                    out_f.write(line)
                print(f"Found line at {idx}, written to {out_path}")
                break
except Exception as e:
    print(f"Error: {e}")
