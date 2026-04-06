import pandas as pd
llm_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\SD Output\MMSC스팸추출_20260327_A.xlsx'
df = pd.read_excel(llm_path, sheet_name='육안분석(시뮬결과35_150)')
f_one = df[df['메시지'].str.contains('F - ONE', na=False)]
for _, r in f_one.iterrows():
    print(f"Row {r.name}: URL={r.get('URL', '')} | Reason={str(r.get('Reason', ''))[:50]}")
