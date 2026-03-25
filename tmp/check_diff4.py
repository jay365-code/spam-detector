import pandas as pd
import unicodedata
import re

def norm(text):
    if pd.isna(text): return ""
    text = str(text)
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'^(\W*(web발신|웹발신|국제발신|광고)\W*)+', '', text, flags=re.IGNORECASE)
    text = "".join(text.split())
    return re.sub(r'[^\w]', '', text)

human_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\MMSC스팸추출_20260320_C.xlsx'
llm_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\SD Output\MMSC스팸추출_20260320_C.xlsx'

h = pd.read_excel(human_path, sheet_name="육안분석(시뮬결과35_150)")
l = pd.read_excel(llm_path, sheet_name="육안분석(시뮬결과35_150)")

output = []

for idx, m in h['메시지'].items():
    if '재형아' in str(m) and '엄마' in str(m):
        output.append(f"HUMAN [{idx}]: {repr(m)}\nHUMAN NORM: {repr(norm(m))}\n")

for idx, m in l['메시지'].items():
    if '재형아' in str(m) and '엄마' in str(m):
        output.append(f"LLM [{idx}]: {repr(m)}\nLLM NORM: {repr(norm(m))}\n")

with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\tmp\diff_result4.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print("Done. Saved to diff_result4.txt")
