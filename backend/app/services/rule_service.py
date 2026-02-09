import os
import re
import unicodedata

class RuleBasedFilter:
    # 숫자 대용 알파벳 (O=0, l/I=1, S=5, B=8 등) - 이 비율이 높으면 난독화 의심
    DIGIT_LIKE_ASCII_LETTERS = set("OolIBSsQDZg")

    def __init__(self):
        # Special character obfuscation patterns
        # e.g., "향.꼼.썽", "안/내/주"
        self.obfuscation_patterns = [
            r"([가-힣])\W([가-힣])\W([가-힣])",  # Hangul with special char in between
            r"([가-힣])\s*[\.\/,\-_]\s*([가-힣])", # Hangul with specific separators
        ]
        
        # 외국어 판정 기준 (한글 비율 10% 미만이면 외국어로 간주)
        self.korean_ratio_threshold = 0.1
        
        # 알파벳-숫자 난독화 의심 비율 (이 값 이상이면 외국어 HAM 대신 다음 단계로 통과)
        self.alphanumeric_obfuscation_ratio_threshold = float(
            os.getenv("ALPHANUMERIC_OBFUSCATION_RATIO_THRESHOLD", "0.55")
        )
        
        # Unicode 난독화 문자 매핑 (Circle letters, Fullwidth 등)
        self.unicode_obfuscation_map = self._build_unicode_map()
    
    def _build_unicode_map(self) -> dict:
        """유니코드 난독화 문자를 일반 ASCII로 매핑하는 딕셔너리 생성"""
        mapping = {}
        
        # Circle letters (ⓐ-ⓩ, Ⓐ-Ⓩ) → a-z, A-Z
        for i, c in enumerate('ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ'):
            mapping[c] = chr(ord('a') + i)
        for i, c in enumerate('ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ'):
            mapping[c] = chr(ord('A') + i)
        
        # Fullwidth letters (ａ-ｚ, Ａ-Ｚ) → a-z, A-Z
        for i in range(26):
            mapping[chr(0xFF41 + i)] = chr(ord('a') + i)  # ａ-ｚ
            mapping[chr(0xFF21 + i)] = chr(ord('A') + i)  # Ａ-Ｚ
        
        # Fullwidth digits (０-９) → 0-9
        for i in range(10):
            mapping[chr(0xFF10 + i)] = chr(ord('0') + i)
        
        # Fullwidth punctuation
        mapping['．'] = '.'  # U+FF0E → .
        mapping['／'] = '/'  # U+FF0F → /
        mapping['：'] = ':'  # U+FF1A → :
        mapping['？'] = '?'  # U+FF1F → ?
        mapping['＆'] = '&'  # U+FF06 → &
        mapping['＝'] = '='  # U+FF1D → =
        mapping['＠'] = '@'  # U+FF20 → @
        mapping['－'] = '-'  # U+FF0D → -
        mapping['＿'] = '_'  # U+FF3F → _
        
        # Mathematical bold/italic letters
        # Bold A-Z: U+1D400-U+1D419, a-z: U+1D41A-U+1D433
        for i in range(26):
            mapping[chr(0x1D400 + i)] = chr(ord('A') + i)
            mapping[chr(0x1D41A + i)] = chr(ord('a') + i)
        
        # Subscript/superscript numbers
        subscript_map = {'₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', 
                        '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9'}
        superscript_map = {'⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
                         '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'}
        mapping.update(subscript_map)
        mapping.update(superscript_map)
        
        return mapping
    
    def decode_obfuscated_text(self, text: str) -> str:
        """난독화된 텍스트를 일반 텍스트로 디코딩"""
        result = []
        for char in text:
            if char in self.unicode_obfuscation_map:
                result.append(self.unicode_obfuscation_map[char])
            else:
                result.append(char)
        return ''.join(result)
    
    def has_unicode_obfuscation(self, text: str) -> bool:
        """텍스트에 유니코드 난독화 문자가 포함되어 있는지 확인"""
        for char in text:
            if char in self.unicode_obfuscation_map:
                return True
        return False
    
    def extract_obfuscated_urls(self, text: str) -> list:
        """난독화된 URL 패턴을 찾아서 디코딩된 URL 리스트 반환"""
        # 먼저 텍스트 전체를 디코딩
        decoded_text = self.decode_obfuscated_text(text)
        
        # URL 패턴 찾기 (도메인.확장자/경로 형태)
        url_pattern = r'(?:https?://)?(?:[\w가-힣-]+\.)+[a-zA-Z]{2,}(?:/[\w\-\.~:/?#\[\]@!$&\'()*+,;=%]*)?'
        
        original_urls = re.findall(url_pattern, text)
        decoded_urls = re.findall(url_pattern, decoded_text)
        
        # 디코딩 전후가 다른 URL만 반환 (난독화된 URL)
        obfuscated_urls = []
        for orig, decoded in zip(original_urls, decoded_urls):
            if orig != decoded:
                obfuscated_urls.append({
                    "original": orig,
                    "decoded": decoded
                })
        
        # 원본에서 못 찾았지만 디코딩 후 찾은 URL
        if len(decoded_urls) > len(original_urls):
            for url in decoded_urls[len(original_urls):]:
                obfuscated_urls.append({
                    "original": None,
                    "decoded": url
                })
        
        return obfuscated_urls

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

    def has_foreign_language(self, text: str) -> dict:
        """
        실제 외국어 문자가 포함되어 있는지 확인
        Returns: {"has_foreign": bool, "language": str or None}
        """
        chinese_count = 0
        japanese_count = 0
        english_count = 0
        korean_count = 0
        
        for char in text:
            # 한글
            if '\uac00' <= char <= '\ud7a3' or '\u1100' <= char <= '\u11ff':
                korean_count += 1
            # 중국어 (CJK Unified Ideographs)
            elif '\u4e00' <= char <= '\u9fff':
                chinese_count += 1
            # 일본어 히라가나/가타카나
            elif '\u3040' <= char <= '\u30ff':
                japanese_count += 1
            # 영어
            elif char.isalpha() and ord(char) < 128:
                english_count += 1
        
        total_alpha = chinese_count + japanese_count + english_count + korean_count
        if total_alpha == 0:
            return {"has_foreign": False, "language": None, "ratio": 0}
        
        korean_ratio = korean_count / total_alpha if total_alpha > 0 else 0
        
        # 일본어/중국어는 한글 비율과 무관하게 우선 판정 (CP949 오인코딩 시 일본어가 한글로 세어져 통과하는 것 방지)
        # CJK+일본어 합산 5 이상이면 외국어 (오인코딩 시 히라가나만 한글로 세어져도 한자는 CJK로 남음)
        cjk_ja = chinese_count + japanese_count
        if cjk_ja >= 5:
            lang = "Japanese" if japanese_count >= chinese_count else "Chinese"
            return {"has_foreign": True, "language": lang, "ratio": cjk_ja / total_alpha}
        if japanese_count > 5:
            return {"has_foreign": True, "language": "Japanese", "ratio": japanese_count / total_alpha}
        if chinese_count > 5:
            return {"has_foreign": True, "language": "Chinese", "ratio": chinese_count / total_alpha}
        # 한글이 거의 없고 영어만 많으면 외국어(영어)
        if korean_ratio < 0.1 and english_count > 10 and korean_count == 0:
            return {"has_foreign": True, "language": "English", "ratio": english_count / total_alpha}
        
        return {"has_foreign": False, "language": None, "ratio": korean_ratio}

    def _looks_like_alphanumeric_obfuscation(self, text: str) -> bool:
        """
        ASCII 알파벳 중 숫자 대용(O, o, l, I, B, S 등) 비율이 임계값 이상이면 True.
        숫자/코드 난독화 의심 시 외국어 HAM 적용하지 않고 다음 단계로 넘기기 위함.
        """
        ascii_letters = [c for c in text if c.isalpha() and ord(c) < 128]
        if len(ascii_letters) < 10:
            return False
        digit_like_count = sum(1 for c in ascii_letters if c in self.DIGIT_LIKE_ASCII_LETTERS)
        ratio = digit_like_count / len(ascii_letters)
        return ratio >= self.alphanumeric_obfuscation_ratio_threshold

    def check(self, message: str) -> dict:
        """
        Stage 1: Rule-Based Detection
        Returns:
            {
                "is_spam": bool or None (None means ambiguous/pass to next stage),
                "reason": str or None,
                "detected_pattern": str or None,
                "decoded_urls": list or None  # 난독화된 URL이 있으면 디코딩된 URL 리스트
            }
        """
        # 1. 외국어 체크를 먼저 수행 (전각 문자 '：' 등이 있어도 일본어/중국어면 HAM)
        foreign_check = self.has_foreign_language(message)
        if foreign_check["has_foreign"]:
            # 영어로 판정된 경우, 알파벳-숫자 난독화 의심이면 HAM 적용하지 않고 다음 단계로 통과
            if foreign_check.get("language") == "English" and self._looks_like_alphanumeric_obfuscation(message):
                return {
                    "is_spam": None,
                    "reason": "Possible alphanumeric obfuscation (e.g. O=0) - pass to analysis",
                    "detected_pattern": "alphanumeric_obfuscation"
                }
            return {
                "is_spam": False,
                "reason": f"Foreign language message ({foreign_check['language']}, ratio: {foreign_check['ratio']:.1%}) - Auto HAM",
                "detected_pattern": None,
                "classification_code": "HAM-5"
            }

        # 2. Unicode 난독화 체크 (Circle letters, Fullwidth 등)
        if self.has_unicode_obfuscation(message):
            obfuscated_urls = self.extract_obfuscated_urls(message)
            decoded_text = self.decode_obfuscated_text(message)
            return {
                "is_spam": None,
                "reason": "Unicode obfuscation detected - requires analysis",
                "detected_pattern": "unicode_obfuscation",
                "decoded_text": decoded_text,
                "decoded_urls": [u["decoded"] for u in obfuscated_urls] if obfuscated_urls else None
            }

        # 3. 한글 난독화 패턴 체크 (향.꼼.썽 등)
        for pattern in self.obfuscation_patterns:
            match = re.search(pattern, message)
            if match:
                detected_text = match.group(0)
                return {
                    "is_spam": None,
                    "reason": "Korean obfuscation pattern detected",
                    "detected_pattern": detected_text
                }

        # 4. Pass to Next Stage
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
