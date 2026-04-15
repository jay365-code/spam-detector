import pandas as pd
file_path = "/Users/jay/Projects/spam-detector/spams/SD Output/MMSC스팸추출_20260414_B 2.xlsx"
df_data = pd.read_excel(file_path, sheet_name="시뮬결과전체", header=1) # The first row might be the summary table?

# Print first few rows to understand structure
print(pd.read_excel(file_path, sheet_name="시뮬결과전체", nrows=5).to_string())

EOF
