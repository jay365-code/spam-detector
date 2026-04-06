import pandas as pd
file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\data\reports\DIFF\DIFF_20260327_A.xlsx'
df = pd.read_excel(file_path, sheet_name='Diff', keep_default_na=False)

def p(msg): print(msg)

p('--- 1. HAM인데 분류코드 존재 (사유에 Type_B 언급) ---')
chk1 = df[(df['AI 판단 (LLM)'] == 'HAM') & (df['AI 사유'].str.contains('Type_B'))]
p(f'Total count: {len(chk1)}')
if len(chk1) > 0:
    for i, r in chk1.head(3).iterrows():
        p(f"Row {r['Row 순번']}: 클래스={r['AI 분류코드']} URL=[{r['AI 추출 URL'][:30]}] Sig=[{r['AI 추출 SIGNATURE']}]\nReason: {r['AI 사유'][:80]}...")

p('\n--- 2. HAM인데 URL을 추출함 ---')
chk2 = df[(df['AI 판단 (LLM)'] == 'HAM') & (df['AI 추출 URL'] != '') & (~df['AI 사유'].str.contains('Type_B'))]
p(f'Total count: {len(chk2)}')
if len(chk2) > 0:
    for i, r in chk2.head(3).iterrows():
        p(f"Row {r['Row 순번']}: URL={r['AI 추출 URL'][:30]}")

p('\n--- 3. Type B SIGNATURE에 추출값 없음 ---')
chk3 = df[(df['AI 사유'].str.contains('SIGNATURE')) & (df['AI 사유'].str.contains('Type_B')) & (df['AI 추출 SIGNATURE'] == '') & (~df['AI 사유'].str.contains('URL, SIGNATURE'))]
p(f'Total count: {len(chk3)}')
if len(chk3) > 0:
    for i, r in chk3.head(3).iterrows():
        p(f"Row {r['Row 순번']}: 사유=[{r['AI 사유'][:80]}]")

p('\n--- 4. Type B (URL, SIGNATURE)인데 추출값 없음 ---')
chk4 = df[(df['AI 사유'].str.contains('Type_B \(URL, SIGNATURE\)')) & ((str(df['AI 추출 URL']) == '') | (str(df['AI 추출 SIGNATURE']) == ''))]
p(f'Total count: {len(chk4)}')
if len(chk4) > 0:
    for i, r in chk4.head(3).iterrows():
        p(f"Row {r['Row 순번']}: URL=[{r['AI 추출 URL']}] Sig=[{r['AI 추출 SIGNATURE']}]\n사유: {r['AI 사유'][:80]}...")
