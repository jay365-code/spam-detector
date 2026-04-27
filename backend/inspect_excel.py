import pandas as pd
import json
import sys

file_path = sys.argv[1]

try:
    xl = pd.ExcelFile(file_path)
    sheet_names = xl.sheet_names
    print(f"Sheet names: {sheet_names}")
    
    for sheet in sheet_names:
        df = xl.parse(sheet, nrows=5)
        print(f"\n--- Sheet: {sheet} ---")
        print("Columns:", list(df.columns))
        print("First few rows:")
        print(df.to_dict(orient='records')[:2])
        
except Exception as e:
    print(f"Error reading excel: {e}")
