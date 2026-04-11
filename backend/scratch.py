import asyncio
import re
from playwright.async_api import async_playwright

def parse_kakao_subscribers(text):
    # '친구 1만명', '친구 1,024명', '채널 추가 1,234'
    text = text.replace('\n', ' ')
    match = re.search(r'(?:친구|친구수|채널\s*추가)\s*([\d,\.]+)(만명|만|명|\+)?', text)
    if not match:
        return 0
    num_str = match.group(1).replace(',', '')
    unit = match.group(2) or ''
    try:
        val = float(num_str)
        if '만' in unit or '만명' in unit:
            val *= 10000
        return int(val)
    except:
        return 0

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()
        await page.goto("http://pf.kakao.com/_xcaxhZX", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        text = await page.evaluate("document.body.innerText")
        print("Subscribers via regex:", parse_kakao_subscribers(text))
        print("Text sample:", [t for t in text.split() if '명' in t or '만' in t or '친구' in t][:10])
        await browser.close()

asyncio.run(main())
