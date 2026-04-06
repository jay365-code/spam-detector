import sys
import pandas as pd

file_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\spams\MMSC스팸추출_20260327_A.xlsx"
xls = pd.ExcelFile(file_path)

out = []
if "금융.SPAM" in xls.sheet_names:
    df = pd.read_excel(xls, "금융.SPAM", nrows=5)
    out.append("Sheet 금융.SPAM Columns: " + str(df.columns.tolist()))
    out.append(df.head(5).to_string())
else:
    out.append("금융.SPAM sheet not found in sample file.")

with open("scripts/excel_out3.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
