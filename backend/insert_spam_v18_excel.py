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

EXCEL_PATH = r"d:\Projects\spam-detector\spams\MMSC스팸추출_20260107_A.xlsx"
SHEET_NAME = "육안분석(시뮬결과35_150)"

def insert_v18_excel():
    success_count = 0
    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        
        # 조건: 구분='o' 이면서 엑셀 컬럼 기준 메시지길이가 9 이상 30 이하
        df_filtered = df[
            (df['구분'].astype(str).str.strip().str.lower() == 'o') & 
            (df['메시지길이'] >= 9) & 
            (df['메시지길이'] <= 30)
        ]
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 중복 실행 방지용 (동일 메시지가 엑셀에 여러 줄 있을 수 있으므로 set으로 가공)
            unique_raw_texts = set(df_filtered['메시지'].dropna().astype(str).tolist())
            
            print(f"=== 엑셀 추출본 DB 업데이트 시작 (대상 데이터: {len(unique_raw_texts)}건) ===")
            
            for raw_text in sorted(unique_raw_texts):
                clean_text = HistoryManager.get_clean_text(raw_text)
                
                # 공백제거 후 30 초과면 아예 오류로 넘기는 기존 보호 로직 유지 
                if not clean_text or len(clean_text) > int(os.getenv("MAX_HOLD_SHORT_LENGTH", "30")):
                    print(f"Skipped (length error after clean): {clean_text}")
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
        print(f"\n작업 완료! 엑셀에서 파싱해 정상 처리된 텍스트 수: {success_count}건")
        
    except Exception as e:
        print(f"오류가 발생했습니다: {e}")

if __name__ == '__main__':
    insert_v18_excel()
