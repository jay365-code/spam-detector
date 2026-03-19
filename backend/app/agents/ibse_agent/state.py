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
    
    # Direct Extraction Fields
    extracted_signature: Optional[str]
    extraction_type: Optional[str] # "string" or "sentence"
    
    final_result: Optional[dict] # Final JSON output format for API
    
    final_result: Optional[dict] # Final JSON output format for API
    
    retry_count: int            # For repair/retry logic
    error: Optional[str]        # Error message if any
    
    is_garbage_obfuscation: bool # Signal from content_agent for intentional obfuscation
