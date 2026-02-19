import unicodedata
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import io
import hashlib
import warnings

# 로깅 설정 (다른 import 전에 초기화)
from logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore")

# Import metrics
from metrics import calculate_advanced_metrics, interpret_policy, generate_summary_text
import monitor

app = FastAPI()

# CORS for frontend (Port 5173 and 5174)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitor.router)

def normalize_text(text: Any) -> str:
    if pd.isna(text):
        return ""
    text = str(text)
    # NFKC normalization
    text = unicodedata.normalize('NFKC', text)
    # Generic whitespace normalization (remove all spaces for robust matching)
    text = "".join(text.split())
    return text

def normalize_label(val: Any) -> bool:
    if pd.isna(val):
        return False
    # Check for 'o' (spam indicator)
    s = str(val).strip()
    return s == 'o'


# ========== 로그 레벨 런타임 변경 API ==========
from logging_config import get_log_levels, set_log_level, set_console_enabled
from pydantic import BaseModel

class LogLevelChange(BaseModel):
    target: str  # "console" 또는 "file"
    level: str   # "DEBUG", "INFO", "WARNING", "ERROR"

class ConsoleToggle(BaseModel):
    enabled: bool  # True=ON, False=OFF

@app.get("/api/log-level")
async def get_current_log_level():
    """현재 로그 레벨 및 콘솔 상태 조회"""
    return get_log_levels()

@app.post("/api/log-level")
async def change_log_level(request: LogLevelChange):
    """런타임에 로그 레벨 변경"""
    result = set_log_level(request.target, request.level)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@app.post("/api/log-console")
async def toggle_console_log(request: ConsoleToggle):
    """콘솔 로그 출력 ON/OFF"""
    return set_console_enabled(request.enabled)


@app.post("/compare")
async def compare_results(
    human_file: UploadFile = File(...),
    llm_file: UploadFile = File(...),
    sheet_name: str = Form("육안분석(시뮬결과35_150)")
):
    logger.info(f"비교 요청 | Human: {human_file.filename} | LLM: {llm_file.filename} | Sheet: {sheet_name}")
    
    try:
        # Load Excels
        human_content = await human_file.read()
        llm_content = await llm_file.read()
        
        # Strict loading: raises ValueError if sheet_name not found
        df_human = pd.read_excel(io.BytesIO(human_content), sheet_name=sheet_name)
        df_llm = pd.read_excel(io.BytesIO(llm_content), sheet_name=sheet_name)
        
    except ValueError as e:
        # Sheet not found or other Excel error
        logger.warning(f"Sheet not found: {sheet_name} - {e}")
        raise HTTPException(status_code=400, detail=f"Sheet '{sheet_name}' not found or error loading excel: {str(e)}")
    except Exception as e:
        logger.exception("Excel 로드 중 오류")
        raise HTTPException(status_code=400, detail=f"Error reading excel file: {str(e)}")

    # Check Columns
    required_cols = ["메시지", "구분"]
    for col in required_cols:
        if col not in df_human.columns:
            raise HTTPException(status_code=400, detail=f"Human file missing column: {col}")
        if col not in df_llm.columns:
            raise HTTPException(status_code=400, detail=f"LLM file missing column: {col}")

    # Process Data with index preservation
    def process_df(df):
        df = df.copy()
        # Keep original index
        df['original_index'] = df.index
        df['norm_msg'] = df['메시지'].apply(normalize_text)
        df['is_spam'] = df['구분'].apply(normalize_label)
        
        # Determine Reason column (Reason or 사유)
        reason_col = None
        for col in ['Reason', '사유', 'reason']:
            if col in df.columns:
                reason_col = col
                break
        
        if reason_col:
            df['reason'] = df[reason_col].fillna("").astype(str)
        else:
            df['reason'] = ""

        # Determine Code column (분류 - Classification Code)
        if '분류' in df.columns:
             df['code'] = df['분류'].fillna("").astype(str).replace(r'\.0$', '', regex=True) # Remove .0 for integers
        else:
             df['code'] = ""

        # Occurrence Index for Duplicates
        # This handles multiple identical messages by assigning 1, 2, 3...
        df['cc_idx'] = df.groupby('norm_msg').cumcount() + 1
        return df

    df_h = process_df(df_human)
    df_l = process_df(df_llm)

    # Combined Merge for Match and Missing detection
    merged_all = pd.merge(
        df_h, 
        df_l, 
        on=['norm_msg', 'cc_idx'], 
        how='outer', 
        suffixes=('_human', '_llm'),
        indicator=True
    )
    
    # Split into Matched / Missing
    merged = merged_all[merged_all['_merge'] == 'both'].copy()
    missing_in_llm_df = merged_all[merged_all['_merge'] == 'left_only'].copy()
    missing_in_human_df = merged_all[merged_all['_merge'] == 'right_only'].copy()

    def format_missing(df, side):
        msg_col = f'메시지_{side}'
        label_col = f'구분_{side}'
        idx_col = f'original_index_{side}'
        code_col = f'code_{side}'
        reason_col = f'reason_{side}'
        
        return [
            {
                "index": int(row[idx_col]),
                "message": str(row[msg_col]),
                "label": str(row[label_col]),
                "code": str(row.get(code_col, '')),
                "reason": str(row.get(reason_col, ''))
            } for _, row in df.iterrows()
        ]

    missing_in_llm = format_missing(missing_in_llm_df, 'human')
    missing_in_human = format_missing(missing_in_human_df, 'llm')

    # Calculate Metrics
    tp = len(merged[(merged['is_spam_human'] == True) & (merged['is_spam_llm'] == True)])
    fn = len(merged[(merged['is_spam_human'] == True) & (merged['is_spam_llm'] == False)])
    fp = len(merged[(merged['is_spam_human'] == False) & (merged['is_spam_llm'] == True)])
    tn = len(merged[(merged['is_spam_human'] == False) & (merged['is_spam_llm'] == False)])
    
    matched_count = len(merged)
    same_label_count = len(merged[merged['is_spam_human'] == merged['is_spam_llm']])
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # 고급 지표 계산
    advanced_metrics = calculate_advanced_metrics(tp, tn, fp, fn, matched_count)
    
    # Generate Diffs (Mismatched Labels)
    diffs = []
    # Filter for mismatches
    mismatch = merged[merged['is_spam_human'] != merged['is_spam_llm']]
    
    for _, row in mismatch.iterrows():
        diff_type = "FN" if row['is_spam_human'] else "FP"
        policy_tag = interpret_policy(
            diff_type, 
            row.get('reason_llm', ''), 
            row.get('reason_human', '')
        )
        
        diffs.append({
            "diff_id": hashlib.md5(f"{row['original_index_human']}_{row['original_index_llm']}".encode()).hexdigest(),
            "diff_type": diff_type,
            "message_preview": str(row['메시지_human'])[:80] + "...",
            "message_full": str(row['메시지_human']),
            "human_label_raw": str(row['구분_human']),
            "llm_label_raw": str(row['구분_llm']),
            "human_code": str(row.get('code_human', '')),
            "llm_code": str(row.get('code_llm', '')),
            "human_is_spam": bool(row['is_spam_human']),
            "llm_is_spam": bool(row['is_spam_llm']),
            "human_reason": str(row.get('reason_human', '')),
            "llm_reason": str(row.get('reason_llm', '')),
            "match_key": f"{row['norm_msg'][:10]}... (idx: {row['cc_idx']})",
            "policy_interpretation": policy_tag
        })

    # 자동 요약 생성
    summary_dict = {
        "sheet_used": sheet_name,
        "total_human": len(df_h),
        "total_llm": len(df_l),
        "human_spam_count": int(df_h['is_spam'].sum()),
        "llm_spam_count": int(df_l['is_spam'].sum()),
        "human_spam_rate": float(df_h['is_spam'].mean()) if len(df_h) > 0 else 0.0,
        "llm_spam_rate": float(df_l['is_spam'].mean()) if len(df_l) > 0 else 0.0,
        "matched": matched_count,
        "match_rate": matched_count / len(df_h) if len(df_h) > 0 else 0.0,
        "agreement_rate": same_label_count / matched_count if matched_count > 0 else 0.0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        # 주요 지표
        "accuracy": advanced_metrics["accuracy"],
        "kappa": advanced_metrics["kappa"],
        "kappa_status": advanced_metrics["kappa_status"],
        "mcc": advanced_metrics["mcc"],
        "disagreement_rate": advanced_metrics["disagreement_rate"],
        # 주요 판정 (Accuracy + Kappa 기반)
        "primary_status": advanced_metrics["primary_status"],
        "primary_color": advanced_metrics["primary_color"],
        "primary_description": advanced_metrics["primary_description"],
        # 보조 지표 (HEI)
        "hei": advanced_metrics["hei"],
        "hei_status": advanced_metrics["hei_status"],
        "hei_color": advanced_metrics["hei_color"]
    }
    
    auto_summary = generate_summary_text(summary_dict, advanced_metrics)
    
    logger.info(f"비교 완료 | Matched: {matched_count} | TP: {tp} | FP: {fp} | FN: {fn} | TN: {tn} | Accuracy: {advanced_metrics['accuracy']} | MissingH: {len(missing_in_human)} | MissingL: {len(missing_in_llm)}")
    
    return {
        "summary": summary_dict,
        "diffs": diffs,
        "missing_in_human": missing_in_human,
        "missing_in_llm": missing_in_llm,
        "auto_summary": auto_summary
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
