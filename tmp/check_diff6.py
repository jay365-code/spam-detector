import pandas as pd
import unicodedata
import re

def norm(text):
    if pd.isna(text): return ""
    text = str(text)
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'^(\W*(web발신|웹발신|국제발신|로밍발신|광고|fw|fwd)\W*)+', '', text, flags=re.IGNORECASE)
    text = "".join(text.split())
    # 특수문자만으로 이루어진 경우 예외 처리
    norm_t = re.sub(r'[^\w]', '', text)
    if not norm_t.strip():
        return text # 특수기호만 있으면 공백만 제거한 원본 유지
    return norm_t

human_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\MMSC스팸추출_20260320_C.xlsx'
llm_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\SD Output\MMSC스팸추출_20260320_C.xlsx'

h = pd.read_excel(human_path, sheet_name="육안분석(시뮬결과35_150)")
l = pd.read_excel(llm_path, sheet_name="육안분석(시뮬결과35_150)")

output = []

for idx, m in h['메시지'].items():
    if '┣━┫' in str(m):
        output.append(f"HUMAN [{idx}]: {repr(m)}\nHUMAN NORM: {repr(norm(m))}\n")

for idx, m in l['메시지'].items():
    if '┣━┫' in str(m):
        output.append(f"LLM [{idx}]: {repr(m)}\nLLM NORM: {repr(norm(m))}\n")

with open(r'c:\Users\leejo\Project\AI Agent\Spam Detector\tmp\diff_result6.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print("Done. Saved to diff_result6.txt")
