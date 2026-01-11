import re

class RuleBasedFilter:
    def __init__(self):
        # Special character obfuscation patterns
        # e.g., "향.꼼.썽", "안/내/주"
        self.obfuscation_patterns = [
            r"([가-힣])\W([가-힣])\W([가-힣])",  # Hangul with special char in between
            r"([가-힣])\s*[\.\/,\-_]\s*([가-힣])", # Hangul with specific separators
        ]

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
        # 1. Simple HAM Rules (Placeholder - can be expanded)
        # if "안녕하세요" in message and len(message) > 20:
        #     return {"is_spam": False, "reason": "Basic HAM pattern", "detected_pattern": None}

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
