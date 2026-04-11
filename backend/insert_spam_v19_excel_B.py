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

EXCEL_PATH = r"d:\Projects\spam-detector\spams\MMSC스팸추출_20260107_B.xlsx"
SHEET_NAME = "육안분석(시뮬결과35_150)"

def insert_v19_excel_B():
    success_count = 0
    try:
        try:
            df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        except ValueError:
            print(f"[{SHEET_NAME}] 시트를 찾지 못했습니다. 첫 번째 기본 시트를 로드합니다.")
            df = pd.read_excel(EXCEL_PATH, sheet_name=0)
            
        # 조건: 구분='o' 이면서 메시지길이가 9 이상 30 이하
        df_filtered = df[
            (df['구분'].astype(str).str.strip().str.lower() == 'o') & 
            (df['메시지길이'] >= 9) & 
            (df['메시지길이'] <= 30)
        ]
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 중복 방지를 위한 set 처리
            unique_raw_texts = set(df_filtered['메시지'].dropna().astype(str).tolist())
            
            print(f"=== 엑셀 B 파일 DB 업데이트 시작 (단일 타겟 문장: {len(unique_raw_texts)}건) ===")
            
            for raw_text in sorted(unique_raw_texts):
                clean_text = HistoryManager.get_clean_text(raw_text)
                
                if not clean_text or len(clean_text) > int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30")):
                    continue
                    
                cursor.execute('''
                    INSERT INTO spam_history (normalized_text, count, last_updated)
                    VALUES (?, 10, CURRENT_TIMESTAMP)
                    ON CONFLICT(normalized_text) DO UPDATE SET 
                        count = count + 1,
                        last_updated = CURRENT_TIMESTAMP
                ''', (clean_text,))
                
                cursor.execute('SELECT count FROM spam_history WHERE normalized_text = ?', (clean_text,))
                result = cursor.fetchone()
                current_count = result[0] if result else 10
                
                success_count += 1
                try:
                    print(f"Processed: {clean_text} (Current count: {current_count})")
                except UnicodeEncodeError:
                    print(f"Processed: [인코딩 오류 회피 텍스트] (Current count: {current_count})")
                
            conn.commit()
        print(f"\n작업 완료! 엑셀 B 버전에서 파싱해 정상 적용된 총 텍스트 수: {success_count}건")
        
    except Exception as e:
        print(f"오류가 발생했습니다: {e}")

if __name__ == '__main__':
    insert_v19_excel_B()
