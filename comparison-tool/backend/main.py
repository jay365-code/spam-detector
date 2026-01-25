import unicodedata
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import io
import hashlib
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

app = FastAPI()

# CORS for frontend (Port 5173 and 5174)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "http://localhost:5174", 
        "http://127.0.0.1:5174"
    ],
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

@app.post("/compare")
async def compare_results(
    human_file: UploadFile = File(...),
    llm_file: UploadFile = File(...),
    sheet_name: str = Form("육안분석(시뮬결과35_150)")
):
    try:
        # Load Excels
        human_content = await human_file.read()
        llm_content = await llm_file.read()
        
        # Strict loading: raises ValueError if sheet_name not found
        df_human = pd.read_excel(io.BytesIO(human_content), sheet_name=sheet_name)
        df_llm = pd.read_excel(io.BytesIO(llm_content), sheet_name=sheet_name)
        
    except ValueError as e:
        # Sheet not found or other Excel error
        raise HTTPException(status_code=400, detail=f"Sheet '{sheet_name}' not found or error loading excel: {str(e)}")
    except Exception as e:
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
        "kappa": advanced_metrics["kappa"],
        "kappa_status": advanced_metrics["kappa_status"],
        "mcc": advanced_metrics["mcc"],
        "disagreement_rate": advanced_metrics["disagreement_rate"],
        "hei": advanced_metrics["hei"],
        "hei_status": advanced_metrics["hei_status"],
        "hei_color": advanced_metrics["hei_color"]
    }
    
    auto_summary = generate_summary_text(summary_dict, advanced_metrics)
    
    return {
        "summary": summary_dict,
        "diffs": diffs,
        "auto_summary": auto_summary
    }

def calculate_advanced_metrics(tp: int, tn: int, fp: int, fn: int, total: int) -> dict:
    """
    Cohen's Kappa, MCC, Disagreement Rate, HEI를 계산합니다.
    
    Args:
        tp: True Positives
        tn: True Negatives
        fp: False Positives
        fn: False Negatives
        total: Total matched messages
        
    Returns:
        dict with keys: kappa, kappa_status, mcc, disagreement_rate, hei, hei_status, hei_color
    """
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
    if kappa >= 0.80:
        kappa_status = "거의 인간 수준 합의"
    elif kappa >= 0.60:
        kappa_status = "강한 합의"
    elif kappa >= 0.40:
        kappa_status = "중간 수준 합의"
    else:
        kappa_status = "약한 합의"
    
    # MCC (Matthews Correlation Coefficient)
    numerator = (tp * tn) - (fp * fn)
    denominator = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = numerator / denominator if denominator > 0 else 0
    
    # Disagreement Rate
    disagreement_rate = (fp + fn) / total if total > 0 else 0
    
    # Human Equivalence Index (HEI)
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    fn_rate = fn / (tp + fn) if (tp + fn) > 0 else 0
    hei = 0.4 * recall + 0.3 * (1 - fn_rate) + 0.3 * kappa
    
    # HEI 상태
    if hei >= 0.85:
        hei_status = "인간 대체 가능"
        hei_color = "success"
    elif hei >= 0.75:
        hei_status = "보조적 대체"
        hei_color = "warning"
    else:
        hei_status = "검토 필요"
        hei_color = "danger"
    
    return {
        "kappa": round(kappa, 4),
        "kappa_status": kappa_status,
        "mcc": round(mcc, 4),
        "disagreement_rate": round(disagreement_rate, 4),
        "hei": round(hei, 4),
        "hei_status": hei_status,
        "hei_color": hei_color
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
    recall_pct = round(metrics['recall'] * 100, 1)
    kappa = advanced['kappa']
    kappa_status = advanced['kappa_status']
    hei_status = advanced['hei_status']
    fp = metrics['fp']
    
    summary = f"""본 LLM 기반 Spam Detector는 사람 수작업 대비 **스팸 탐지 Recall {recall_pct}%**를 달성했으며, Cohen's Kappa 기준 **κ={kappa}**로 우연적 일치를 제거하더라도 사람 판단과 **{kappa_status.lower()}**를 보입니다.

False Positive는 {fp}건으로, 주로 보수적 정책 차이에서 발생하며 운영 정책 튜닝을 통해 감소 가능한 영역입니다.

**종합 평가(HEI)**: 본 모델은 **{hei_status}** 수준으로 평가됩니다."""
    
    return summary


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
