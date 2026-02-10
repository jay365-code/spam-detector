import re
import unicodedata

# Copied from nodes.py to verify logic without importing app dependencies
COMMON_TLDS = {
    'com', 'net', 'org', 'edu', 'gov', 'mil', 'int', 'kr', 'co.kr', 'or.kr', 'pe.kr', 'go.kr', 'ac.kr',
    'io', 'ai', 'me', 'info', 'biz', 'shop', 'site', 'top', 'xyz', 'club', 'online', 'pro',
    'id', 'vn', 'jp', 'cn', 'us', 'uk', 'de', 'fr', 'tv', 'cc', 'li', 'ly', 'be', 'it', 'to', 'gg',
    'ws', 'mobi', 'asia', 'name', 'store', 'news', 'app', 'dev', 'tech'
}

def extract_node_logic(message):
    
    # 1. 프로토콜이 있는 URL 추출 (가장 확실, 한글 포함 가능)
    # http://오징어.오뎅탕 -> 허용
    protocol_pattern = r'(?:http|https)://[^\s]+'
    protocol_urls = re.findall(protocol_pattern, message)
    
    # 2. 프로토콜이 없는 도메인 패턴 추출 (엄격한 검증 필요)
    # 한글.한글 -> 오징어.오뎅탕 (제외되어야 함)
    # google.com -> 허용
    # 정규식: (문자열.문자열) 형태
    domain_pattern = r'(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]{2,}'
    raw_candidates = re.findall(domain_pattern, message)
    
    # 정규화(NFKC)된 텍스트에서도 추출
    try:
        normalized_message = unicodedata.normalize('NFKC', message)
        if normalized_message != message:
            protocol_urls.extend(re.findall(protocol_pattern, normalized_message))
            raw_candidates.extend(re.findall(domain_pattern, normalized_message))
    except Exception as e:
        print(f"Normalization failed: {e}")
    
    urls = []
    
    # 2-1. 프로토콜 URL 처리
    for url in protocol_urls:
         # 뒤에 붙은 구두점 제거
        url = url.rstrip('.,;!?)]}"\'')
        if len(url) > 7: # http://...
            urls.append(url)
            
    # 2-2. 도메인 후보 검증
    for cand in raw_candidates:
        cand = cand.rstrip('.,;!?)]}"\'')
        if not cand: continue
        
        # 이미 프로토콜 URL에 포함된 경우 스킵
        if any(cand in u for u in urls):
            continue

        # TLD 확인
        try:
            parts = cand.split('.')
            if len(parts) < 2: continue
            
            tld = parts[-1].lower()
            
            # 한글이 포함된 TLD인 경우 (.한국 등)
            is_korean_tld = any('\uac00' <= char <= '\ud7a3' or '\u3131' <= char <= '\u3163' for char in tld)
            
            if is_korean_tld:
                # [Policy] 프로토콜 없는 한글 TLD는 스킵 (오징어.오뎅탕 방지)
                continue
            
            # 영문 TLD인 경우: Whitelist(COMMON_TLDS)에 있어야 허용
            if tld not in COMMON_TLDS:
                 # punycode TLD (xn--) 은 허용
                 if not tld.startswith('xn--'):
                     continue
            
            # 통과된 경우 http:// 붙여서 추가
            urls.append(f"http://{cand}")
            
        except Exception:
            continue

    # Removing duplication logic for brevity in test
    return list(set(urls))

test_cases = [
    "신년맞이 이벤트 양주및 오징어.오뎅탕. 치킨 등 서비스 새해 복 많이 받으세요",
    "http://두산위브.kr",
    "google.com",
    "치킨.맥주",
    "안녕하세요.반갑습니다",
    "kisa.or.kr",
    "http://xn--oh5b1hw1h.xn--oo1b366awyh",
    "notatld.xyz123", # Should be rejected
    "valid.site", # Should be accepted
    "http://오징어.오뎅탕" # Should be accepted because of protocol
]

print("=== URL Extraction Verification ===")
for msg in test_cases:
    extracted = extract_node_logic(msg)
    print(f"Input: '{msg}'\nExtracted: {extracted}\n")
