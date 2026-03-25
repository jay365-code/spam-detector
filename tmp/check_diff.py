import pandas as pd
import unicodedata

def norm(text):
    if pd.isna(text): return ""
    text = str(text)
    text = unicodedata.normalize('NFKC', text)
    return "".join(text.split())

human_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\MMSC스팸추출_20260320_C.xlsx'
llm_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\SD Output\MMSC스팸추출_20260320_C.xlsx'

h = pd.read_excel(human_path, sheet_name="육안분석(시뮬결과35_150)")
l = pd.read_excel(llm_path, sheet_name="육안분석(시뮬결과35_150)")

print("=== HUMAN M컴퓨터 아카데미 ===")
for idx, m in h['메시지'].items():
    if 'M컴퓨터' in str(m):
        print(f"[{idx}] {repr(m)}")
        print(f"NORM: {repr(norm(m))}")

print("\n=== LLM M컴퓨터 아카데미 ===")
for idx, m in l['메시지'].items():
    if 'M컴퓨터' in str(m):
        print(f"[{idx}] {repr(m)}")
        print(f"NORM: {repr(norm(m))}")

print("\n=== HUMAN 채무종결 법원 ===")
for idx, m in h['메시지'].items():
    if '채무종결' in str(m) and '법원' in str(m):
        print(f"[{idx}] {repr(m)}")
        print(f"NORM: {repr(norm(m))}")

print("\n=== LLM 채무종결 법원 ===")
for idx, m in l['메시지'].items():
    if '채무종결' in str(m) and '법원' in str(m):
        print(f"[{idx}] {repr(m)}")
        print(f"NORM: {repr(norm(m))}")
