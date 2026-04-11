import os
import glob
import sqlite3
import pandas as pd
from pathlib import Path

def get_cp949_byte_len(text: str) -> int:
    try:
        return len(text.encode("cp949"))
    except UnicodeEncodeError:
        return len(text.encode("utf-8"))

def import_signatures_from_excel():
    spams_dir = r"d:\Projects\spam-detector\spams"
    db_path = r"d:\Projects\spam-detector\backend\data\signatures.db"
    
    excel_files = glob.glob(os.path.join(spams_dir, "*.xlsx"))
    print(f"Found {len(excel_files)} excel files. Processing...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    total_added = 0
    total_files_processed = 0
    
    for file_path in excel_files:
        if "~$" in file_path:
            continue
            
        try:
            # Read only sheet names first
            xl = pd.ExcelFile(file_path)
            sheet_names = xl.sheet_names
            
            signatures_to_add = set()
            
            if "문자열중복제거" in sheet_names:
                df = xl.parse("문자열중복제거")
                col_name = "문자열(중복제거)"
                if col_name in df.columns:
                    for val in df[col_name].dropna():
                        clean_val = str(val).replace(' ', '').replace('\n', '').replace('\r', '').strip()
                        if clean_val:
                            signatures_to_add.add(clean_val)
                            
            if "문장중복제거" in sheet_names:
                df = xl.parse("문장중복제거")
                col_name = "문장(중복제거)"
                # "문장(중복제거)" 컬럼명이 정확하지 않을 수 있어 유사 매칭 처리
                actual_col = None
                for c in df.columns:
                    if "문장" in str(c) and "중복제거" in str(c):
                        actual_col = c
                        break
                        
                if actual_col:
                    for val in df[actual_col].dropna():
                        clean_val = str(val).replace(' ', '').replace('\n', '').replace('\r', '').strip()
                        if clean_val:
                            signatures_to_add.add(clean_val)
                            
            if signatures_to_add:
                inserts = []
                for sig in signatures_to_add:
                    b_len = get_cp949_byte_len(sig)
                    inserts.append((sig, b_len, 'spam', f'bulk_import_{os.path.basename(file_path)}'))
                
                cursor.executemany('''
                    INSERT OR IGNORE INTO signatures (signature, byte_length, category, source)
                    VALUES (?, ?, ?, ?)
                ''', inserts)
                
                added_count = cursor.rowcount
                if added_count > 0:
                    total_added += added_count
                    
            total_files_processed += 1
            if total_files_processed % 10 == 0:
                print(f"Processed {total_files_processed}/{len(excel_files)} files... Current new sigs: {total_added}")
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            
    conn.commit()
    conn.close()
    
    print(f"\nDone! Processed {total_files_processed} files.")
    print(f"Successfully added {total_added} unique signatures to DB.")

if __name__ == "__main__":
    import_signatures_from_excel()
