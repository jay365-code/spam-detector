import re
import unicodedata
import os

class RuleBasedFilter:
    def __init__(self):
        # Special character obfuscation patterns
        # e.g., "향.꼼.썽", "안/내/주"
        self.obfuscation_patterns = [
            r"([가-힣])\W([가-힣])\W([가-힣])",  # Hangul with special char in between
            r"([가-힣])\s*[\.\/,\-_]\s*([가-힣])", # Hangul with specific separators
        ]
        
        try:
            self.alphanumeric_obfuscation_threshold = float(os.getenv("ALPHANUMERIC_OBFUSCATION_RATIO_THRESHOLD", "0.55"))
        except ValueError:
            self.alphanumeric_obfuscation_threshold = 0.55

        # 메시지 최소 길이 필터링 (환경변수 로드, 기본값 9바이트)
        try:
            self.min_message_length = int(os.getenv("MIN_MESSAGE_LENGTH", "9"))
        except ValueError:
            self.min_message_length = 9

        # 숫자와 혼동될 수 있는 알파벳 (대소문자 포함)
        # O, o, I, l, B, S, Z, b, q, g, z ... 
        self.number_lookalikes = set('OoIlBSZbqgz')
        
        # 키보드 입력 가능한 가림/난독화 문자 (? * _ # ~ ^ · 및 인코딩 오류 시 �)
        self.mask_obfuscation_chars = set('?*_#~^\u00b7\ufffd')
        
        # Unicode 난독화 문자 매핑 (Circle letters, Fullwidth 등)
        self.unicode_obfuscation_map = self._build_unicode_map()
    
    def update_thresholds(self):
        """런타임에 설정 임계값들을 다시 로드"""
        try:
            self.alphanumeric_obfuscation_threshold = float(os.getenv("ALPHANUMERIC_OBFUSCATION_RATIO_THRESHOLD", "0.55"))
            self.min_message_length = int(os.getenv("MIN_MESSAGE_LENGTH", "9"))
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"⚙️ [RuleFilter] 임계값 갱신: MIN_LEN={self.min_message_length}, ALPHANUMERIC={self.alphanumeric_obfuscation_threshold}")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"RuleFilter thresholds update failed: {e}")
    
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

    def get_obfuscation_ratio(self, text: str) -> float:
        """
        알파벳-숫자 혼용 난독화 비율 계산
        숫자(0-9)와 숫자 유사 문자(O, I, B, S 등)가 전체 영숫자(Alphanumeric) 중 차지하는 비율 
        """
        if not text:
            return 0.0
            
        # 영문자와 숫자만 추출 (공백, 특수문자 제외)
        # 한글도 제외하고 순수하게 영문자+숫자 패턴만 봄
        alphanum_chars = [c for c in text if c.isalnum() and not ('\uac00' <= c <= '\ud7a3')]
        
        if not alphanum_chars:
            return 0.0
            
        # 의심스러운 문자: 숫자(0-9) + 숫자 유사 알파벳(O, I 등)
        suspicious_count = 0
        for char in alphanum_chars:
            if char.isdigit() or char in self.number_lookalikes:
                suspicious_count += 1
                
        return suspicious_count / len(alphanum_chars)

    def has_url_in_message(self, text: str) -> bool:
        """메시지에 URL이 포함되어 있는지 확인"""
        url_pattern = re.compile(
            r'(?:https?://|www\.)\S+|[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163\-\.?]+\.[a-zA-Z가-힣]{2,}'
        )
        return bool(url_pattern.search(text))

    def has_garbled_or_masked_text(self, text: str) -> bool:
        """
        난독화/가림 패턴: mask_obfuscation_chars 비율이 높으면 의심
        대상: ? * _ # ~ ^ · � (키보드 입력 가능 + 인코딩 오류 시)
        예: "????? ***** https://v****.im/...", "___^^^___"
        """
        if not text or len(text) < 10:
            return False
        garbled_chars = sum(1 for c in text if c in self.mask_obfuscation_chars)
        return garbled_chars / len(text) >= 0.15  # 15% 이상이면 가림/난독화 의심

    def has_url_with_obfuscated_domain(self, text: str) -> bool:
        """
        도메인 내부에 가림 문자가 있는 URL 패턴
        예: https://v????.im/flrvl2, bit*.ly/xxx, v***.im
        """
        # mask_obfuscation_chars 중 하나라도 도메인 부분에 있으면 의심
        mask_class = ''.join(re.escape(c) for c in self.mask_obfuscation_chars)
        # 도메인.확장자 직전에 가림 문자 포함
        pattern = re.compile(
            rf'[a-zA-Z0-9]*[{mask_class}]+[a-zA-Z0-9]*\.[a-zA-Z]{{2,}}',
            re.IGNORECASE
        )
        return bool(pattern.search(text))


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
        # 0. 메시지 최소 길이 체크 (SKIP 대상)
        # 한글 포함 여부와 무관하게 무조건 지정된 길이 미만이면 SKIP 처리함
        
        # 공백과 줄바꿈을 제외한 실제 의미 있는 문자열의 바이트 길이(CP949 기준) 계산
        import re
        visible_text = re.sub(r'\s+', '', message) if message else ""
        try:
             visible_len = len(visible_text.encode('cp949'))
        except UnicodeEncodeError:
             # 인코딩 불가 문자가 있을 경우를 대비한 대략적 폴백 (문자수 * 2)
             visible_len = len(visible_text) * 2
        
        if message and visible_len < self.min_message_length:
            return {
                "is_spam": False,
                "reason": f"Short message (Visible Length: {visible_len} < {self.min_message_length}) - Skipped",
                "detected_pattern": "short_message",
                "classification_code": "SKIP",
                "exclude_from_excel": True  # 엑셀 저장에서 제외 플래그
            }

        # 1. Unicode 난독화 체크 (Circle letters, Fullwidth 등)
        # 난독화가 감지되면 외국어 체크 건너뛰고 분석 진행
        if self.has_unicode_obfuscation(message):
            obfuscated_urls = self.extract_obfuscated_urls(message)
            decoded_text = self.decode_obfuscated_text(message)
            
            return {
                "is_spam": None,  # LLM/URL Agent로 전달
                "reason": "Unicode obfuscation detected - requires analysis",
                "detected_pattern": "unicode_obfuscation",
                "decoded_text": decoded_text,
                "decoded_urls": [u["decoded"] for u in obfuscated_urls] if obfuscated_urls else None
            }
        
        # 2. 한글 난독화 패턴 체크 (향.꼼.썽 등)
        for pattern in self.obfuscation_patterns:
            match = re.search(pattern, message)
            if match:
                detected_text = match.group(0)
                return {
                    "is_spam": None,  # LLM으로 전달 (확정 스팸 아님)
                    "reason": "Korean obfuscation pattern detected",
                    "detected_pattern": detected_text
                }

        # 3. 알파벳-숫자 혼용 난독화 체크
        obfuscation_ratio = self.get_obfuscation_ratio(message)
        if obfuscation_ratio >= self.alphanumeric_obfuscation_threshold:
             return {
                "is_spam": True,  # 의도적인 혼용 난독화는 즉시 스팸으로 판정
                "reason": f"Alphanumeric obfuscation detected (Ratio: {obfuscation_ratio:.2f})",
                "detected_pattern": "alphanumeric_obfuscation",
                "classification_code": "0" # 기타 스팸
            }

        # 5. Pass to Next Stage
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
