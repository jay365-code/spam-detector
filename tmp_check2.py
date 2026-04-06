import pandas as pd
llm_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\SD Output\MMSC스팸추출_20260327_A.xlsx'
df = pd.read_excel(llm_path, sheet_name='문자문장차단등록(Type B)')
f_one = df[df['메시지'].str.contains('F - ONE', na=False)]
for _, r in f_one.iterrows():
    print(f"Sig: {r.get('시그니처(추출 문자열)')}")
