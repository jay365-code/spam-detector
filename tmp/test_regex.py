import re
import unicodedata

# 1. Test Sentence Gluing Logic for '비트.ly'
message = "(광고)[NH]쉿!!일일 1900만 급등주bit.ly/밴드정보방선착순 마감무료거부 0801560190"
domain_pattern = r'(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]{2,}(?:/[^\s\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]*)?'
raw_candidates = re.findall(domain_pattern, message)

print(f"Candidates for bit.ly message: {raw_candidates}")

# What happens to '급등주bit.ly/밴드정보방선착순' at the COMMON_TLDS check?
COMMON_TLDS = {'com', 'net', 'org', 'info', 'biz', 'co', 'kr', 'me', 'tv', 'us', 'app', 'site', 'io', 'ai', 'store', 'shop'}
# Wait, 'ly' is missing from COMMON_TLDS in url_agent/nodes.py !!!
print(f"Is 'ly' in COMMON_TLDS? {'ly' in COMMON_TLDS}")

# 2. Test Numeric Prefix Stripping for 'http://3nwdavin84.com'
url = "http://3nwdavin84.com"
domain_match = re.match(r'(https?://)(\d+)([^/\s]+)(/.*)?', url)
if domain_match:
    prefix = domain_match.group(1)
    digits = domain_match.group(2)
    rest_domain = domain_match.group(3)
    path = domain_match.group(4) or ""
    print(f"Matched Prefix. prefix: {prefix}, digits: {digits}, rest: {rest_domain}, path: {path}")
else:
    print("Prefix match failed!")

# 3. Test is_broken_short_url
from urllib.parse import urlparse
parsed = urlparse("http://3nwdavin84.com")
path = parsed.path.strip('/')
print(f"Path len for 3nwdavin84.com: {len(path)}. So is_broken_short_url: {len(path) <= 3 and not parsed.query and not parsed.fragment}")
