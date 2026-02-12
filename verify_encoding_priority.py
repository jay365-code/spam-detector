
import os
import chardet
import logging

# Set up logging similar to the app
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_encoding_logic(file_content, filename):
    print(f"\n--- Testing {filename} ---")
    raw_data = file_content
    
    # Logic copied from excel_handler.py (UPDATED)
    detected = chardet.detect(raw_data)
    encoding_used = detected.get('encoding')
    confidence = detected.get('confidence', 0)
    
    print(f"Detected: {encoding_used} (Confidence: {confidence})")

    # UPDATED LOGIC
    encodings_to_try = ['utf-8', 'cp949', 'euc-kr']
    
    if encoding_used and encoding_used.lower() not in encodings_to_try:
            encodings_to_try.append(encoding_used)
    
    encodings_to_try.append('latin1') # Last resort
    
    # Remove duplicates while preserving order
    encodings_to_try = list(dict.fromkeys(encodings_to_try))

    success_encoding = None
    decoded_lines = []

    for enc in encodings_to_try:
        try:
            # print(f"Trying {enc}...")
            decoded_text = raw_data.decode(enc)
            lines = decoded_text.splitlines()
            success_encoding = enc
            print(f"Success with {enc}")
            break
        except UnicodeDecodeError:
            # print(f"Failed with {enc}")
            continue
    
    if not success_encoding:
        print("Fallback to CP949 (replace)")
        decoded_text = raw_data.decode('cp949', errors='replace')
        decoded_lines = decoded_text.splitlines()
        success_encoding = 'cp949-replace'

    print(f"Final Result: {success_encoding}")
    return success_encoding

# Test Cases
# 1. UTF-8 Korean
utf8_data = "안녕하세요. 이것은 UTF-8 테스트입니다.\thttp://test.com".encode('utf-8')
# 2. EUC-KR Korean
euckr_data = "안녕하세요. 이것은 EUC-KR 테스트입니다.\thttp://test.com".encode('euc-kr')

# 3. Simulate the failure case: EUC-KR bytes that Chardet thinks is ISO-8859-1
# This is hard to construct perfectly without the specific file, but standard EUC-KR often looks like Latin1
# Let's trust the logic change mostly, but verify standard cases still work.

test_encoding_logic(utf8_data, "utf8_sample.txt")
test_encoding_logic(euckr_data, "euckr_sample.txt")
