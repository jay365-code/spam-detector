import os
import sqlite3
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

from app.agents.history_manager import HistoryManager, DB_PATH

SPAM_DIR = Path(r"d:\Projects\spam-detector\spams")
SHEET_NAME = "육안분석(시뮬결과35_150)"

def batch_insert():
    start_date = datetime(2026, 1, 9)
    end_date = datetime(2026, 4, 8)
    versions = ['A', 'B', 'C']
    
    total_files_processed = 0
    total_texts_inserted = 0
    total_unique_texts = 0
    
    print(f"[{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}] 기간 일괄 배치 추출 시작...\n")
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y%m%d")
        
        for v in versions:
            filename = f"MMSC스팸추출_{date_str}_{v}.xlsx"
            filepath = SPAM_DIR / filename
            
            if not filepath.exists():
                continue
                
            try:
                # 파일 처리 시작
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
                
        current_date += timedelta(days=1)
        
    print("\n" + "="*50)
    print("                대규모 일괄 작업 완료!")
    print("="*50)
    print(f"처리한 파일 수: {total_files_processed}개")
    print(f"찾아낸 고유 텍스트 타겟 (공백포함): {total_unique_texts}건")
    print(f"DB에 최종 적용된 스팸 건수(클리닝/길이제한필터 후): {total_texts_inserted}건")
    print("="*50)

if __name__ == '__main__':
    batch_insert()
