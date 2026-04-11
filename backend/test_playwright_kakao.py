import asyncio
import os
import sys

# Ensure backend directory is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.url_agent.tools import PlaywrightManager

async def test_kakao_desktop_scrape():
    print('Testing kakao URL scrape...')
    manager = PlaywrightManager(headless=True)
    result = await manager.scrape_url('http://pf.kakao.com/_IQmuT')
    print('Status:', result.get('status'))
    print('Error:', result.get('error'))
    print('Title:', result.get('title'))
    text = result.get('text', '')
    print('Extracted Text (first 600 chars):', text[:600].replace('\n', ' '))
    if '친구' in text or '채널' in text:
        print('\nSUCCESS: Found visual friend count / channel text.')
    else:
        print('\nFAILED to find visual friend count / channel text.')
    
    await manager.stop()

if __name__ == '__main__':
    asyncio.run(test_kakao_desktop_scrape())
