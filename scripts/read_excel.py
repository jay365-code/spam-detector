import sys
import pandas as pd

file_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\spams\MMSC스팸추출_20260327_A.xlsx"
xls = pd.ExcelFile(file_path)

out = []
for s in ["문자열중복제거", "문장중복제거"]:
    if s in xls.sheet_names:
        df = pd.read_excel(xls, s, nrows=2)
        out.append(f"\nSheet {s} Columns: " + str(df.columns.tolist()))
        out.append(df.head(2).to_string())

with open("scripts/excel_out2.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
