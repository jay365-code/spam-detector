import sys
import os
import re

message = "(광고)[NH]쉿!!일일 1900만 급등주bit.ly/밴드정보방선착순 마감무료거부 0801560190"

domain_pattern = r'(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]{2,}(?:/[^\s\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]*)?'
raw_candidates = re.findall(domain_pattern, message)

print("1. raw_candidates:", raw_candidates)

COMMON_TLDS = {'com', 'net', 'org', 'info', 'biz', 'co', 'kr', 'me', 'tv', 'us', 'app', 'site', 'io', 'ai', 'store', 'shop', 'click', 'link', 'top', 'vip', 'club', 'cc', 'ly', 'gl', 'do', 'la', 'to'}

urls = []
suffix_regex = r'(?i)(code|tel|id|kakao|line|best|pw|password|상담|문의)[\.,;:!\?\)\]\}\"\'\s]*$'
strip_chars = '.,;:!?)]}"\''

for cand in raw_candidates:
    cand = re.sub(suffix_regex, '', cand)
    cand = cand.rstrip(strip_chars)
    print(f"2. Processing cand: {cand}")
    
    domain_part = cand.split('/')[0]
    print(f"2a. domain_part: {domain_part}")
    
    parts = domain_part.split('.')
    print(f"2b. parts: {parts}")
    
    if len(parts) == 2:
        sld = parts[0]
        tld = parts[1].lower()
        print(f"2c. SLD: {sld}, TLD: {tld}")
        if tld in COMMON_TLDS or tld.startswith('xn--'):
            print(f"2d. TLD {tld} is in COMMON_TLDS")
            m = re.search(r'[\uac00-\ud7a3\u3131-\u3163%↑↓]+([a-zA-Z0-9-]+)$', sld)
            if m:
                new_sld = m.group(1)
                new_domain_part = f"{new_sld}.{parts[1]}"
                print(f"2e. Replaced SLD: {sld} -> {new_sld}")
                cand = new_domain_part + cand[len(domain_part):]
                domain_part = new_domain_part
                parts = domain_part.split('.')
            else:
                print("2f. Regex to find Korean failed on SLD:", sld)
        else:
            print(f"TLD {tld} NOT IN COMMON_TLDS")

    tld = parts[-1].lower()
    if tld not in COMMON_TLDS:
        print(f"REJECTED at end because {tld} not in COMMON_TLDS")
        continue
    print(f"ACCEPTED -> {cand}")
    urls.append(f"http://{cand}")

print("\nFinal URLs:", urls)
