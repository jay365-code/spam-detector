import pandas as pd
file_path = "/Users/jay/Projects/spam-detector/spams/SD Output/MMSC스팸추출_20260414_B 2.xlsx"
xls = pd.ExcelFile(file_path)
print("Sheet Names:", xls.sheet_names)
