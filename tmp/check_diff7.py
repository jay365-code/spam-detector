import pandas as pd
import unicodedata
import re

def norm(text):
    if pd.isna(text): return ""
    text = str(text)
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'^(\W*(web발신|웹발신|국제발신|로밍발신|광고|fw|fwd)\W*)+', '', text, flags=re.IGNORECASE)
    text = "".join(text.split())
    norm_t = re.sub(r'[^\w]', '', text)
    return norm_t

h=pd.read_excel('c:/Users/leejo/Project/AI Agent/Spam Detector/spams/MMSC스팸추출_20260320_C.xlsx', sheet_name='육안분석(시뮬결과35_150)')
l=pd.read_excel('c:/Users/leejo/Project/AI Agent/Spam Detector/spams/SD Output/MMSC스팸추출_20260320_C.xlsx', sheet_name='육안분석(시뮬결과35_150)')

h_empty_count = sum([1 for m in h['메시지'].dropna() if norm(m) == ""])
l_empty_count = sum([1 for m in l['메시지'].dropna() if norm(m) == ""])

print(f"H Empty Count (norm==''): {h_empty_count}")
print(f"L Empty Count (norm==''): {l_empty_count}")

# Print the messages that become empty
print("\nHUMAN EMPTY MESSAGES:")
for idx, m in h['메시지'].items():
    if norm(m) == "":
        print(f"[{idx}] {repr(m)}")

print("\nLLM EMPTY MESSAGES:")
for idx, m in l['메시지'].items():
    if norm(m) == "":
        print(f"[{idx}] {repr(m)}")
