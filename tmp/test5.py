import re

urls = ["http://ko.gl/1VP2차상담", "http://bit.ly/밴드정보방선착순", "http://naver.me/abcde테스트"]

path_cleaned_urls = []
for url in urls:
    if "://" in url:
        protocol, clean_cand = url.split("://", 1)
        protocol += "://"
        if '/' in clean_cand:
            domain_part = clean_cand.split('/', 1)[0]
            path_part = clean_cand[len(domain_part):]
            # Use lookbehind to only match Korean that comes AFTER an alphanumeric or hyphen
            kr_match = re.search(r'(?<=[a-zA-Z0-9_\-])[\uac00-\ud7a3\u3131-\u3163]', path_part)
            if kr_match:
                first_kr_idx = kr_match.start()
                cut_idx = first_kr_idx
                if first_kr_idx > 0 and path_part[first_kr_idx-1].isdigit():
                    num_match = re.search(r'\d+$', path_part[:first_kr_idx])
                    if num_match:
                        num_start = num_match.start()
                        kr_word = path_part[first_kr_idx:first_kr_idx+2]
                        units = ['차', '번', '위', '일', '명', '원', '만', '억', '퍼', '개', '건', '달', '주', '배', '년', '월', '시', '분', '초', '등', '백', '천', '조', '탄', '기']
                        if any(kr_word.startswith(u) for u in units) or any(kr_word.startswith(w) for w in ["프로", "만원", "억원", "종목", "코드", "상담", "수익"]):
                            cut_idx = num_start
                url = protocol + domain_part + path_part[:cut_idx]
    
    if url not in path_cleaned_urls:
        path_cleaned_urls.append(url)

print(path_cleaned_urls)
