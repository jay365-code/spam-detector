import pandas as pd
import sys

try:
    df = pd.read_excel("sample_test_result.xlsx", sheet_name="육안분석(시뮬결과35_150)")
    print("Columns:", df.columns.tolist())
    
    if "In_Token" in df.columns and "Out_Token" in df.columns:
        print("PASS: Token columns exist.")
        # Check if values are non-null/numeric for the first processed row
        # (Assuming at least one row was processed)
        print("First row values:", df.iloc[0][["In_Token", "Out_Token"]].to_dict())
    else:
        print("FAIL: Token columns missing.")
        
except Exception as e:
    print(f"FAIL: Error reading file - {e}")
