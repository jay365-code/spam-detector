from typing import List, TypedDict, Optional, Dict, Any

class SpamState(TypedDict):
    """
    ISAA (Intelligent Spam URL Analysis Agent)의 상태(State) 정의
    """
    sms_content: str                # 원본 문자 메시지
    target_urls: List[str]          # 추출된 URL 목록 (초기)
    current_url: Optional[str]      # 현재 분석 중인 URL
    
    # 방문 기록 및 데이터
    visited_history: List[str]      # 방문한 URL 히스토리
    scraped_data: Dict[str, Any]    # 수집된 데이터 (텍스트, 이미지경로 등)
    
    # 분석 결과
    is_spam: Optional[bool]         # 스팸 여부 (True: SPAM, False: HAM, None: UNKNOWN)
    spam_probability: float         # 스팸 확률 (0.0 ~ 1.0)
    classification_code: Optional[str] # 분류 코드 (예: "1", "HAM-1")
    reason: str                     # 판단 사유
    
    # 탐색 제어
    depth: int                      # 현재 탐색 깊이
    max_depth: int                  # 최대 탐색 허용 깊이 (기본: 2)
    is_final: bool                  # 최종 판단 완료 여부
