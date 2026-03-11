from typing import Dict, Any

def calculate_advanced_metrics(tp: int, tn: int, fp: int, fn: int, total: int) -> Dict[str, Any]:
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
    
    # ===== PRIMARY STATUS (Kappa 기반) =====
    # 판정 기준:
    # - 협업 가능 (🟢): Kappa >= 0.75
    # - 모니터링 필요 (🟡): 0.65 <= Kappa < 0.75
    # - 개선 필요 (🔴): Kappa < 0.65
    
    if kappa >= 0.75:
        primary_status = "협업 가능"
        primary_color = "success"
        primary_description = "Kappa가 0.75 이상으로 Human-AI 간 높은 통계적 합의를 보입니다."
    elif kappa >= 0.65:
        primary_status = "모니터링 필요"
        primary_color = "warning"
        primary_description = "Kappa가 0.65~0.75 구간으로 지속적인 모니터링이 권장됩니다."
    else:
        primary_status = "개선 필요"
        primary_color = "danger"
        primary_description = "Kappa가 0.65 미만으로 모델 개선이 필요합니다."
    
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

def generate_summary_text(metrics: Dict[str, Any], advanced: Dict[str, Any]) -> str:
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
    
    type_b_total = metrics.get('type_b_total_count', 0)
    type_b_url = metrics.get('type_b_url_count', 0)
    type_b_sig = metrics.get('type_b_sig_count', 0)
    type_b_both = metrics.get('type_b_both_count', 0)
    type_b_none = metrics.get('type_b_none_count', 0)
    
    summary = f"""본 LLM 기반 Spam Detector는 Human 판정 대비 **Accuracy {accuracy_pct}%**를 달성했으며, Cohen's Kappa **κ={kappa}** ({kappa_status})로 우연적 일치를 제외하더라도 통계적으로 유의미한 합의를 보입니다.

불일치 케이스는 총 {fp + fn}건 (FN {fn}건, FP {fp}건)이며, 이는 운영 정책 조정 및 모델 튜닝을 통해 개선 가능한 영역입니다.

**Type_B (FP Sentinel 보호) 분석**:
총 **{type_b_total}**건이 학습 데이터 오염 방지를 위해 Type_B로 분류되었습니다.
- **Type_B (URL, SIGNATURE)**: {type_b_both}건
- **Type_B (URL)**: {type_b_url}건
- **Type_B (SIGNATURE)**: {type_b_sig}건
- **Type_B (NONE)**: {type_b_none}건 (단속 무기 미추출 케이스)

**종합 판정**: 본 모델은 **{primary_status}** 수준입니다."""
    
    return summary
