import re
from typing import List, Dict, Set
from .state import Candidate, IBSEState
from .utils import get_cp949_byte_len

class CandidateGenerator:
    """
    Generates, scores, and filters signature candidates from the match_text.
    """
    
    def __init__(self):
        self._load_config()
        self._compile_patterns()

    def _load_config(self):
        import json
        import os
        
        config_path = os.path.join(os.path.dirname(__file__), "ibse_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.PATTERNS = config.get("PATTERNS", {})
                self.WEIGHTS = config.get("WEIGHTS", {})
        except Exception as e:
            # Fallback (Log warning in production)
            print(f"Warning: Failed to load ibse_config.json: {e}")
            self.PATTERNS = {}
            self.WEIGHTS = {}

    def _compile_patterns(self):
        self.regex_map = {}
        for tag, pattern in self.PATTERNS.items():
            self.regex_map[tag] = re.compile(pattern)

    def generate(self, match_text: str, original_text: str, max_byte_len: int, top_k: int) -> List[Candidate]:
        """
        Generates candidates using a sliding window approach.
        """
        candidates = []
        n = len(match_text)
        
        # Build Index Mapping: match_text index -> original_text index (start)
        # origin_map[i] = index j in original_text such that original_text[j] is the i-th non-whitespace char
        origin_map = []
        o_idx = 0
        for char in match_text:
            while o_idx < len(original_text):
                # We assume match_text comes from removing \s+ from original_text (with NO NFKC)
                # Matches char?
                if original_text[o_idx] == char:
                    origin_map.append(o_idx)
                    o_idx += 1
                    break
                # Skip original whitespace/mismatch (though mismatch shouldn't happen if preprocessing is consistent)
                o_idx += 1
        
        # If lengths mismatch (safety), fill remainder
        while len(origin_map) < len(match_text):
            origin_map.append(len(original_text))

        # Sliding Window
        # Step size could be 1 or 2. Using 1 for maximum coverage in MVP.
        step = 1 
        
        for start_idx in range(0, n, step):
            current_byte_len = 0
            # Expand end_idx until byte limit is reached
            for end_idx in range(start_idx + 1, n + 1):
                # Optimization: Slice just the new character if possible, but for CP949 strictness, 
                # we need to check the whole substring or maintain running count.
                # Since CP949 is variable width (1 or 2 bytes), let's check substring.
                substring = match_text[start_idx:end_idx]
                
                # IMPORTANT: Mapping back to Original Text
                # The original substring corresponds to original_text[origin_start : origin_end]
                # origin_start = map[start_idx]
                # origin_end = map[end_idx-1] + 1 (to include the last char)
                # Note: This strategy captures internal whitespace!
                
                if start_idx < len(origin_map) and (end_idx - 1) < len(origin_map):
                    orig_start = origin_map[start_idx]
                    orig_end_inclusive_idx = origin_map[end_idx-1]
                    # We want to slice up to the character AFTER the last matched one.
                    # But wait, does 'orig_end_inclusive_idx' cover everything?
                    # Example: "A B" -> match "AB". start=0('A'), end=2.
                    # map[0]=0('A'), map[1]=2('B').
                    # orig substring should be "A B". original_text[0:3].
                    # So slice end should be map[end_idx-1] + 1
                    orig_slice_end = orig_end_inclusive_idx + 1
                    
                    original_substring = original_text[orig_start:orig_slice_end]
                else:
                    original_substring = substring # Fallback

                # [USER REQUEST FIX] 문자열 길이는 공백을 제거한 상태(match_text 기반의 substring)에서 20/40자(바이트)를 제한해야 함.
                # orig_len: 나중에 원본 텍스트를 복원할 때 DB 저장용이나 참고용으로만 사용.
                # b_len (제한 기준): 공백이 없는 촘촘한 substring의 CP949 바이트 길이를 기준으로 함.
                b_len = get_cp949_byte_len(substring)
                
                if b_len == -1: 
                    # Contains invalid char, discard this substring and potentially stop extending 
                    # if the invalid char is at the end? 
                    # Ideally, if match_text is NFKC, most chars are valid, but emojis might not be.
                    # If invalid, we can just skip this candidate.
                    continue
                
                if b_len > max_byte_len:
                    # Exceeded limit, stop extending for this start_idx
                    break
                    
                # [USER APPROVED FIX] 토큰 폭발 방지 (Prompt Token Shield)
                # 순수 바이트(b_len)는 40바이트 이하를 통과했더라도, 
                # 중간에 스팸 발송자가 집어넣은 공백/엔터 때문에 원본 텍스트 길이가 100자를 넘어가면 LLM 과부하 방지를 위해 탈락시킴.
                if len(original_substring) > 100:
                    continue
                
                # It's a valid candidate within limit
                # We want to favor longer signatures usually, or at least keep them as candidates.
                # Use Normalized Byte Length for threshold check
                if b_len >= 4:
                    tags = self._identify_tags(substring) # Tags checked on DENSE text (easier for regex)
                    score = self._calculate_score(substring, b_len, tags)
                    
                    c = Candidate(
                        id=f"c{max_byte_len}_{len(candidates)}",
                        text=substring, # Keep normalized for deduplication / logic
                        text_original=original_substring, # Store original for Output
                        byte_len_cp949=b_len,
                        start_idx=start_idx,
                        end_idx_exclusive=end_idx,
                        anchor_tags=tags,
                        score=score
                    )
                    candidates.append(c)
        
        # Deduplicate and Filter
        return self._filter_top_k(candidates, top_k)

    def _identify_tags(self, text: str) -> List[str]:
        tags = []
        for tag, pattern in self.regex_map.items():
            if pattern.search(text):
                tags.append(tag)
        return tags

    def _calculate_score(self, text: str, byte_len: int, tags: List[str]) -> float:
        score = 0.0
        
        # Add Tag Weights
        for tag in tags:
            score += self.WEIGHTS.get(tag, 0.0)
            
        # Penalties
        if byte_len <= 8:
            score += self.WEIGHTS["TOO_SHORT"]
            
        if text.isdigit():
            score += self.WEIGHTS["ALL_DIGITS"]
            
        return score

    def _filter_top_k(self, candidates: List[Candidate], k: int) -> List[Candidate]:
        """
        Deduplicates by text (keeping highest score) and returns Top-K.
        """
        # Dedup map: text -> candidate
        dedup_map: Dict[str, Candidate] = {}
        
        for c in candidates:
            if c.text in dedup_map:
                # Keep the one with higher score (or random if same)
                if c.score > dedup_map[c.text].score:
                    dedup_map[c.text] = c
            else:
                dedup_map[c.text] = c
                
        # Sort by score desc, then byte_len desc
        unique_candidates = list(dedup_map.values())
        unique_candidates.sort(key=lambda x: (x.score, x.byte_len_cp949), reverse=True)
        
        return unique_candidates[:k]

# Node Function
def generate_candidates_node(state: IBSEState) -> dict:
    """
    Function-based node for LangGraph.
    Updates 'candidates_20' and 'candidates_40' in the state.
    """
    match_text = state.get("match_text", "")
    original_text = state.get("original_text", "")
    
    if not match_text:
        return {"error": "No match_text provided"}
    
    generator = CandidateGenerator()
    
    # PRD FR-2.4 Candidates Count (Revised to prevent LLM timeouts)
    # 200개의 문자열 후보를 전부 LLM에 넘기면 프롬프트 크기와 연산 과부하로 45초 이상의
    # 응답 타임아웃이 빈번히 발생함. 휴리스틱 점수 상위 10~15개씩만 넘겨도 충분함.
    # Candidates 20: Top 5 (Reduced from 10 to save prompt length)
    # Candidates 40: Top 5 (Reduced from 10 to save prompt length)
    
    c20 = generator.generate(match_text, original_text, max_byte_len=20, top_k=5)
    c40 = generator.generate(match_text, original_text, max_byte_len=40, top_k=5)
    
    return {
        "candidates_20": c20,
        "candidates_40": c40
    }
