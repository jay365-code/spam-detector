from typing import TypedDict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class Candidate:
    id: str
    text: str
    text_original: str  # Original text including whitespace/normalization
    byte_len_cp949: int
    start_idx: int
    end_idx_exclusive: int
    anchor_tags: List[str]
    score: float = 0.0

class IBSEState(TypedDict):
    """
    State definition for IBSE (Intelligence Blocking Signature Extractor) Agent.
    Designed for LangGraph compatibility.
    """
    message_id: str
    original_text: str          # Raw SMS text
    match_text: str             # Preprocessed text (NFKC + No Space)
    
    candidates_20: List[Candidate] # Candidates <= 20 bytes
    candidates_40: List[Candidate] # Candidates <= 40 bytes
    
    selected_decision: Optional[str] # use_20, use_40, unextractable
    selected_candidate: Optional[Candidate]
    
    final_result: Optional[dict] # Final JSON output format for API
    
    retry_count: int            # For repair/retry logic
    error: Optional[str]        # Error message if any
