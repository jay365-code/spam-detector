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

app = FastAPI()

# CORS for frontend (Port 5173 and 5174)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    # Merge on [norm_msg, cc_idx]
    # Inner join to compare only matched messages
    merged = pd.merge(
        df_h, 
        df_l, 
        on=['norm_msg', 'cc_idx'], 
        how='inner', 
        suffixes=('_human', '_llm')
    )
    
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
    
    # Generate Diffs
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
    
    logger.info(f"비교 완료 | Matched: {matched_count} | TP: {tp} | FP: {fp} | FN: {fn} | TN: {tn} | Accuracy: {advanced_metrics['accuracy']}")
    
    return {
        "summary": summary_dict,
        "diffs": diffs,
        "auto_summary": auto_summary
    }

def calculate_advanced_metrics(tp: int, tn: int, fp: int, fn: int, total: int) -> dict:
    """
    Cohen's Kappa, MCC, Disagreement Rate, HEI, Primary Status를 계산합니다.
    
    Args:
        tp: True Positives
        tn: True Negatives
        fp: False Positives
        fn: False Negatives
        total: Total matched messages
        
    Returns:
        dict with metrics including primary_status based on Accuracy + Kappa
    """
    # Accuracy (단순 일치율)
    accuracy = (tp + tn) / total if total > 0 else 0
    
    # Cohen's Kappa
    po = (tp + tn) / total if total > 0 else 0  # 관찰된 합의도
    
    # 우연에 의한 기대 합의도
    spam_h = (tp + fn) / total if total > 0 else 0
    spam_l = (tp + fp) / total if total > 0 else 0
    ham_h = (tn + fp) / total if total > 0 else 0
    ham_l = (tn + fn) / total if total > 0 else 0
    
    pe = (spam_h * spam_l) + (ham_h * ham_l)  # 우연 합의도
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 0 else 0
    
    # Kappa 상태 레이블
    if kappa >= 0.75:
        kappa_status = "우수한 일치"
    elif kappa >= 0.60:
        kappa_status = "상당한 일치"
    elif kappa >= 0.40:
        kappa_status = "중간 수준"
    else:
        kappa_status = "미흡"
    
    # MCC (Matthews Correlation Coefficient)
    numerator = (tp * tn) - (fp * fn)
    denominator = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = numerator / denominator if denominator > 0 else 0
    
    # Disagreement Rate
    disagreement_rate = (fp + fn) / total if total > 0 else 0
    
    # Human Equivalence Index (HEI) - 보조 지표로 유지
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    fn_rate = fn / (tp + fn) if (tp + fn) > 0 else 0
    hei = 0.4 * recall + 0.3 * (1 - fn_rate) + 0.3 * kappa
    
    # HEI 상태 (보조용)
    if hei >= 0.85:
        hei_status = "인간 대체 가능"
        hei_color = "success"
    elif hei >= 0.75:
        hei_status = "보조적 대체"
        hei_color = "warning"
    else:
        hei_status = "검토 필요"
        hei_color = "danger"
    
    # ===== PRIMARY STATUS (Accuracy + Kappa 기반) =====
    # 판정 기준:
    # - 협업 가능: Accuracy >= 95% AND Kappa >= 0.60
    # - 모니터링 필요: Accuracy >= 90% AND Kappa >= 0.40
    # - 개선 필요: 그 외
    
    if accuracy >= 0.95 and kappa >= 0.60:
        primary_status = "협업 가능"
        primary_color = "success"
        primary_description = "Human-AI 간 높은 일치율과 통계적으로 유의미한 합의를 보입니다."
    elif accuracy >= 0.90 and kappa >= 0.40:
        primary_status = "모니터링 필요"
        primary_color = "warning"
        primary_description = "일치율은 양호하나, 지속적인 모니터링이 권장됩니다."
    else:
        primary_status = "개선 필요"
        primary_color = "danger"
        primary_description = "일치율 또는 합의도가 기준에 미달합니다. 모델 개선이 필요합니다."
    
    return {
        "accuracy": round(accuracy, 4),
        "kappa": round(kappa, 4),
        "kappa_status": kappa_status,
        "mcc": round(mcc, 4),
        "disagreement_rate": round(disagreement_rate, 4),
        "hei": round(hei, 4),
        "hei_status": hei_status,
        "hei_color": hei_color,
        # Primary metrics (Accuracy + Kappa based)
        "primary_status": primary_status,
        "primary_color": primary_color,
        "primary_description": primary_description
    }

def interpret_policy(diff_type: str, llm_reason: str, human_reason: str) -> str:
    """
    불일치 케이스의 정책 해석 태그를 생성합니다.
    
    Args:
        diff_type: "FN" 또는 "FP"
        llm_reason: AI의 분류 근거
        human_reason: 사람의 분류 근거
        
    Returns:
        정책 해석 문자열
    """
    llm_lower = str(llm_reason).lower()
    human_lower = str(human_reason).lower()
    
    if diff_type == "FN":
        # Human=SPAM, AI=HAM (놓침)
        if any(word in human_lower for word in ["애매", "모호", "불명확", "ambiguous"]):
            return "애매한 사람 판단"
        else:
            return "정책 차이"
    
    else:  # FP
        # Human=HAM, AI=SPAM (오탐)
        conservative_keywords = ["suspicious", "promotional", "commercial", "의심", "홍보", "광고"]
        if any(keyword in llm_lower for keyword in conservative_keywords):
            return "과차단 (보수적 정책)"
        else:
            return "키워드 기반 오탐"

def generate_summary_text(metrics: dict, advanced: dict) -> str:
    """
    분석 결과의 한국어 서술형 요약을 생성합니다.
    
    Args:
        metrics: 요약 지표 dict
        advanced: calculate_advanced_metrics의 고급 지표 dict
        
    Returns:
        마크다운 형식의 한국어 요약문
    """
    accuracy_pct = round(advanced['accuracy'] * 100, 1)
    kappa = advanced['kappa']
    kappa_status = advanced['kappa_status']
    primary_status = advanced['primary_status']
    fp = metrics['fp']
    fn = metrics['fn']
    
    summary = f"""본 LLM 기반 Spam Detector는 Human 판정 대비 **Accuracy {accuracy_pct}%**를 달성했으며, Cohen's Kappa **κ={kappa}** ({kappa_status})로 우연적 일치를 제외하더라도 통계적으로 유의미한 합의를 보입니다.

불일치 케이스는 총 {fp + fn}건 (FN {fn}건, FP {fp}건)이며, 이는 운영 정책 조정 및 모델 튜닝을 통해 개선 가능한 영역입니다.

**종합 판정**: 본 모델은 **{primary_status}** 수준입니다."""
    
    return summary


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
