import pandas as pd
file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\DIFF\DIFF_20260327_A.xlsx'
df = pd.read_excel(file_path, sheet_name='Diff', keep_default_na=False)

def p(msg): print(msg)
p('--- 1. HAM인데 분류코드/URL/Signature 존재 ---')
chk1 = df[(df['AI 판단 (LLM)'] == 'HAM') & (df['AI 분류코드'].str.startswith('Type_B'))]
p(f'Total count: {len(chk1)}')
for i, r in chk1.head(2).iterrows():
    p(f"Row {r['Row 순번']}: AI판단={r['AI 판단 (LLM)']}, 분류={r['AI 분류코드']}\nURL: {str(r['AI 추출 URL'])[:30]}\nSig: {r['AI 추출 SIGNATURE']}\nReason: {r['AI 사유']}\n")

p('--- 2. HAM인데 URL 추출 ---')
chk2 = df[(df['AI 판단 (LLM)'] == 'HAM') & (df['AI 추출 URL'] != '') & (~df['AI 분류코드'].str.startswith('Type_'))]
p(f'Total count: {len(chk2)}')
for i, r in chk2.head(2).iterrows():
    p(f"Row {r['Row 순번']}: AI판단={r['AI 판단 (LLM)']}\nURL: {str(r['AI 추출 URL'])[:30]}\nSig: {r['AI 추출 SIGNATURE']}\nReason: {r['AI 사유']}\n")

p('--- 3. Type B SIGNATURE에 추출값 없음 ---')
chk3 = df[(df['AI 분류코드'] == 'Type_B (SIGNATURE)') & (df['AI 추출 SIGNATURE'] == '')]
p(f'Total count: {len(chk3)}')

p('--- 4. Type B (URL, SIGNATURE)인데 추출값 없음 ---')
chk4 = df[(df['AI 분류코드'] == 'Type_B (URL, SIGNATURE)') & ((df['AI 추출 URL'] == '') | (df['AI 추출 SIGNATURE'] == ''))]
p(f'Total count: {len(chk4)}')
if len(chk4) > 0:
    for i, r in chk4.head(3).iterrows():
        p(f"Row {r['Row 순번']}: URL=[{r['AI 추출 URL']}] Sig=[{r['AI 추출 SIGNATURE']}]")
