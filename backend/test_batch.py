import os
import sys

# add path
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from app.utils.excel_handler import ExcelHandler

handler = ExcelHandler()
result = {
    "is_spam": False,
    "malicious_url_extracted": True,
    "url_spam_code": "SPAM-12",
    "classification_code": "HAM-1",
    "reason": "테스트입니다 | [텍스트 HAM + 악성 URL 분리 감지: 이건스팸]",
    "spam_probability": 0.1
}

# dummy unique_urls dict
unique_urls = {}

msg_val = "1234님 확인 바랍니다 https://gogolink.kr/AI-GPT-1234"

import re

# Simulate block from excel_handler.py process_file
if result.get("is_spam") is True or result.get("malicious_url_extracted"):
    url_pattern = r'(?:https?://|www\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    # [BUG IDENTIFIED] -> The pattern matches ONLY the domain in re.findall because of the way we wrote it!
    # No, wait, let's test it:
    urls = re.findall(url_pattern, msg_val)
    print(f"Extracted URLs regex 1: {urls}")
    
    url_pattern2 = r'(?:https?://|www\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[a-zA-Z0-9./?=&%_-]*)?'
    urls2 = re.findall(url_pattern2, msg_val)
    print(f"Extracted URLs regex 2: {urls2}")
 
