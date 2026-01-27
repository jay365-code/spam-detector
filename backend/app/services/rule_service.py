import re

class RuleBasedFilter:
    def __init__(self):
        # Special character obfuscation patterns
        # e.g., "향.꼼.썽", "안/내/주"
        self.obfuscation_patterns = [
            r"([가-힣])\W([가-힣])\W([가-힣])",  # Hangul with special char in between
            r"([가-힣])\s*[\.\/,\-_]\s*([가-힣])", # Hangul with specific separators
        ]
        
        # 외국어 판정 기준 (한글 비율 10% 미만이면 외국어로 간주)
        self.korean_ratio_threshold = 0.1

    def get_korean_ratio(self, text: str) -> float:
        """
        한글 문자 비율 계산 (0.0 ~ 1.0)
        공백, 특수문자, 숫자 제외하고 알파벳/한글만 계산
        """
        if not text:
            return 0.0
        
        # 알파벳과 한글만 추출 (숫자, 공백, 특수문자 제외)
        alpha_chars = [c for c in text if c.isalpha()]
        if not alpha_chars:
            return 0.0
        
        # 한글 문자 (가-힣)
        korean_chars = [c for c in alpha_chars if '\uac00' <= c <= '\ud7a3']
        return len(korean_chars) / len(alpha_chars)

    def check(self, message: str) -> dict:
        """
        Stage 1: Rule-Based Detection
        Returns:
            {
                "is_spam": bool or None (None means ambiguous/pass to next stage),
                "reason": str or None,
                "detected_pattern": str or None # To be passed to Stage 2 LLM
            }
        """
        # 1. 외국어 체크 (한글 비율이 임계값 미만이면 HAM)
        korean_ratio = self.get_korean_ratio(message)
        if korean_ratio < self.korean_ratio_threshold:
            return {
                "is_spam": False,
                "reason": f"Non-Korean message (Korean ratio: {korean_ratio:.1%}) - Auto HAM",
                "detected_pattern": None,
                "classification_code": "HAM-5"
            }

        # 2. Obfuscation Detection
        for pattern in self.obfuscation_patterns:
            match = re.search(pattern, message)
            if match:
                detected_text = match.group(0)
                return {
                    "is_spam": True, # Tentative SPAM
                    "reason": "Obfuscation pattern detected",
                    "detected_pattern": detected_text
                }

        # 3. Pass to Next Stage
        return {
            "is_spam": None,
            "reason": "No rule matched",
            "detected_pattern": None
        }

    def check_batch(self, messages: list[str]) -> list[dict]:
        """
        Stage 1 (Batch) implementation
        """
        results = []
        for msg in messages:
            results.append(self.check(msg))
        return results
