import os
import sqlite3
import sys
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

SPAM_DIR = Path(r"d:\Projects\spam-detector\spams")
SHEET_NAME = "육안분석(시뮬결과35_150)"

def insert_20260409():
    dates_and_versions = [("20260409", "A"), ("20260409", "B")]
    
    total_files_processed = 0
    total_texts_inserted = 0
    total_unique_texts = 0
    
    print(f"=== 20260409 A, B 파일 DB 로드 시작 ===\n")
    
    for date_str, v in dates_and_versions:
        filename = f"MMSC스팸추출_{date_str}_{v}.xlsx"
        filepath = SPAM_DIR / filename
        
        if not filepath.exists():
            print(f"[SKIP] 파일을 찾을 수 없습니다: {filename}")
            continue
            
        try:
            try:
                df = pd.read_excel(filepath, sheet_name=SHEET_NAME)
            except ValueError:
                df = pd.read_excel(filepath, sheet_name=0)
                
            df_filtered = df[
                (df['구분'].astype(str).str.strip().str.lower() == 'o') & 
                (df['메시지길이'] >= 9) & 
                (df['메시지길이'] <= 30)
            ]
            
            unique_raw_texts = set(df_filtered['메시지'].dropna().astype(str).tolist())
            total_unique_texts += len(unique_raw_texts)
            
            success_count = 0
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                
                for raw_text in unique_raw_texts:
                    clean_text = HistoryManager.get_clean_text(raw_text)
                    
                    if not clean_text or len(clean_text) > int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30")):
                        continue
                        
                    # 업데이트 시간은 서울 시간 기준으로 맞춤 
                    cursor.execute('''
                        INSERT INTO spam_history (normalized_text, count, last_updated)
                        VALUES (?, 10, datetime('now', 'localtime'))
                        ON CONFLICT(normalized_text) DO UPDATE SET 
                            count = count + 1,
                            last_updated = datetime('now', 'localtime')
                    ''', (clean_text,))
                    success_count += 1
                    
                conn.commit()
            
            total_files_processed += 1
            total_texts_inserted += success_count
            print(f"[SUCCESS] {filename} 완료 - 추출/적재: {len(unique_raw_texts)}건 / {success_count}건")
            
        except Exception as e:
            print(f"[ERROR] {filename} 처리 실패: {e}")
            
    print("\n" + "="*50)
    print(f"최종 처리 완료: 파일 {total_files_processed}개, DB 반영 {total_texts_inserted}건")
    print("="*50)

if __name__ == '__main__':
    insert_20260409()
