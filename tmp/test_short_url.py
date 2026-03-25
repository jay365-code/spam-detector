import re

def is_short_url(url: str) -> bool:
    if not url: return False
    
    shortener_domains = [
        "bit.ly", "goo.gl", "tinyurl.com", "ow.ly", "t.co", 
        "is.gd", "buff.ly", "adf.ly", "bit.do", "mcaf.ee", 
        "me2.do", "kakaolink.com", "buly.kr", 
        "vo.la", "url.kr", "zrr.kr", "yun.kr", "han.gl",
        "shorter.me", "shrl.me", "link24.kr", "myip.kr",
        "sbz.kr", "tne.kr", "dokdo.in", "uto.kr",
        "rb.gy", "short.io", "dub.co", "bl.ink", "tiny.cc", 
        "t.ly", "tr.ee", "reurl.kr", "abit.ly", "blow.pw", 
        "c11.kr", "di.do", "koe.kr", "lrl.kr", "muz.so", 
        "t2m.kr", "ouo.io", "adfoc.us",
        "ii.ad", "vvd.bz", "gooal.kr", "ko.gl", "qrco.de", "linktr.ee"
    ]
    
    try:
        clean_url = re.sub(r'^https?://', '', url.lower())
        clean_url = re.sub(r'^www\.', '', clean_url)
        print(f"URL: {url} -> Clean URL: {clean_url}")
        
        for domain in shortener_domains:
            if clean_url.startswith(domain):
                print(f"  Matched domain: {domain}")
                return True
        return False
    except:
        return False

urls_to_test = [
    "https://vvd.bz/hgGq",
    "https://vo.la/B6xZd1",
    "https://sbz.kr/2NYp",
    "ii.ad/b45a37",
    "https://app.tq.cfd/Kr",
    "pf.kakao.com/_XkzEX/chat"
]

for url in urls_to_test:
    res = is_short_url(url)
    print(f"Result for {url}: {res}\n")
