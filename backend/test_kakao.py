import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Test KGM Service URL
url = 'https://pf.kakao.com/_mnUdX'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req, context=ctx).read().decode('utf-8')
    title = re.search(r'<meta property=\"og:title\" content=\"(.*?)\"', html)
    desc = re.search(r'<meta property=\"og:description\" content=\"(.*?)\"', html)
    print('Title:', title.group(1) if title else None)
    print('Desc:', desc.group(1) if desc else None)
except Exception as e:
    print('Error:', e)
