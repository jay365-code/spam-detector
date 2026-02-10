import re
import unicodedata

def extract_urls(message):
    # Logic extracted from nodes.py
    url_pattern = r'(?:http[s]?://)?(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z가-힣]{2,}(?:/[^\s]*)?'
    
    found_urls = re.findall(url_pattern, message)
    
    # Normalization check
    try:
        normalized_message = unicodedata.normalize('NFKC', message)
        if normalized_message != message:
            found_urls_normalized = re.findall(url_pattern, normalized_message)
            found_urls.extend(found_urls_normalized)
    except Exception as e:
        print(f"Normalization failed: {e}")
    
    urls = []
    for url in found_urls:
        if len(url) < 4: continue
        if not url.startswith("http"):
            url = "http://" + url
        urls.append(url)
        
    return list(set(urls))

test_cases = [
    "신년맞이 이벤트 양주및 오징어.오뎅탕. 치킨 등 서비스 새해 복 많이 받으세요 갈매동 벌떼",
    "http://두산위브.kr",
    "google.com",
    "치킨.맥주",
    "안녕하세요.반갑습니다",
    "kisa.or.kr",
    "http://xn--oh5b1hw1h.xn--oo1b366awyh"
]

print("=== URL Extraction Test ===")
for msg in test_cases:
    extracted = extract_urls(msg)
    print(f"Input: '{msg}'\nExtracted: {extracted}\n")
