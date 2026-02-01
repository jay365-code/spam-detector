
import re

def extract_urls(message: str):
    # Original pattern from nodes.py
    url_pattern = r'(?:http[s]?://)?(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z가-힣]{2,}(?:/[^\s]*)?'
    
    found_urls = re.findall(url_pattern, message)
    return found_urls

test_message = "· 새해 첫주말 · [50,000 원] 지급 · 출??? OK [ dⓢlp①③7⑤.cc ] · 돈방석 앉는길"
extracted = extract_urls(test_message)

print(f"Message: {test_message}")
print(f"Extracted: {extracted}")

expected = "dslp137.cc"
# Note: The current extraction logic expects to extraction *something* but since it doesn't normalize, it might extract 'd' then stop at 'ⓢ', or nothing.
# Ideally we want it to extract the normalized URL.

if "dⓢlp①③7⑤.cc" in extracted:
    print("FAIL: Extracted raw obfuscated URL (which might not be resolvable)")
elif "dslp137.cc" in extracted:
    print("SUCCESS: Extracted normalized URL")
else:
    print("FAIL: Failed to extract URL")
