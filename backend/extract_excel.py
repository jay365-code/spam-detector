import sys
import pandas as pd
from pathlib import Path

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

# 콘솔 출력 인코딩 안전화 (한글 특수문자 깨짐 방지)
sys.stdout.reconfigure(encoding='utf-8')

from app.agents.history_manager import HistoryManager

EXCEL_PATH = r"d:\Projects\spam-detector\spams\MMSC스팸추출_20260107_A.xlsx"
SHEET_NAME = "육안분석(시뮬결과35_150)"

def extract_from_excel():
    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        
        # 1. '구분' 값이 'o' 인 행만 필터링 (대소문자, 공백 주의)
        df_filtered = df[df['구분'].astype(str).str.strip().str.lower() == 'o']
        
        # 결과 저장할 셋 (중복 제거용)
        unique_texts = set()
        
        print(f"--- 조건: 구분='o' & 길이 9이상 30이하 (공백제거후) ---")
        for idx, row in df_filtered.iterrows():
            msg = str(row['메시지']) if pd.notna(row['메시지']) else ""
            
            # 기존 로직과 동일하게 공백을 완벽히 제거
            clean_text = HistoryManager.get_clean_text(msg)
            
            # 2. 메시지 길이가 9 이상, 30 이하인지 체크
            if 9 <= len(clean_text) <= 30:
                unique_texts.add(clean_text)
        
        # 보기 좋게 정렬해서 화면에 출력
        for text in sorted(unique_texts):
            print(text)
            
        print(f"\n총 추출된 고유 메시지 수: {len(unique_texts)} 개")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract_from_excel()
