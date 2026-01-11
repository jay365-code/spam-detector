import unicodedata
import re

def get_cp949_byte_len(text: str) -> int:
    """
    Calculates the byte length of a string when encoded in CP949.
    Returns -1 if the text contains characters that cannot be encoded in CP949.
    """
    try:
        return len(text.encode("cp949"))
    except UnicodeEncodeError:
        return -1

def is_valid_cp949(text: str) -> bool:
    """
    Checks if the text can be safely encoded in CP949.
    """
    try:
        text.encode("cp949")
        return True
    except UnicodeEncodeError:
        return False

def preprocess_text(text: str) -> str:
    """
    Preprocesses the text for signature extraction.
    1. Apply NFKC normalization.
    2. Remove all whitespace (spaces, tabs, newlines).
    
    Args:
        text: The original text.
        
    Returns:
        The normalized, whitespace-free text (match_text).
    """
    if not text:
        return ""
    
    # 1. NFKC Normalization -> DISABLED (User Requirement: Do not change original chars)
    # normalized = unicodedata.normalize("NFKC", text)
    
    # 2. Remove all whitespace
    # Using regex \s+ matches any whitespace character (equivalent to [ \t\n\r\f\v])
    match_text = re.sub(r'\s+', '', text)
    
    return match_text
