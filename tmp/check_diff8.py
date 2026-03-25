import pandas as pd
import unicodedata
import re

def norm(text):
    if pd.isna(text): return ""
    text = str(text)
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'^(\W*(web발신|웹발신|국제발신|로밍발신|광고|fw|fwd)\W*)+', '', text, flags=re.IGNORECASE)
    text_no_space = "".join(text.split())
    norm_t = re.sub(r'[^\w]', '', text_no_space)
    if not norm_t:
        return text_no_space
    return norm_t

h_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\MMSC스팸추출_20260320_C.xlsx'
l_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\SD Output\MMSC스팸추출_20260320_C.xlsx'

h = pd.read_excel(h_path, sheet_name='육안분석(시뮬결과35_150)')
l = pd.read_excel(l_path, sheet_name='육안분석(시뮬결과35_150)')

for idx, m in h['메시지'].items():
    if '가 갠 니' in str(m) or '가    갠  니' in str(m) or '가갠니' in norm(m):
        print(f"H [{idx}]: {repr(m)}")
        print(f"H NORM: {norm(m)}")

for idx, m in l['메시지'].items():
    if '가 갠 니' in str(m) or '가    갠  니' in str(m) or '가갠니' in norm(m):
        print(f"L [{idx}]: {repr(m)}")
        print(f"L NORM: {norm(m)}")
