import pandas as pd
import sys

file_path = "/Users/jay/Projects/spam-detector/spams/SD Output/MMSC스팸추출_20260414_B 2.xlsx"
df_summary = pd.read_excel(file_path, sheet_name="04월 14일 (화)_B")
df_data = pd.read_excel(file_path, sheet_name="Original")

summary_val = df_summary.iloc[1, 1] # row 2 (index 1), col F (index 1) which is "스팸태깅"
print(f"Summary Spam Count in Sheet: {summary_val}")

# count in Original
gubun_not_null = df_data['구분'].notna().sum()
gubun_o = (df_data['구분'].astype(str).str.lower() == 'o').sum()
red_group = (df_data.get('Red Group', pd.Series(dtype=str)) == 'O').sum()

print(f"Total Rows: {len(df_data)}")
print(f"Rows with 구분 == 'o': {gubun_o}")
print(f"Rows with Red Group == 'O': {red_group}")

# Find any that are SPAM or Red Group but not counted
is_b = df_data['Semantic Class'].astype(str).str.startswith("Type_B").sum()

