import sys
import os
import asyncio
import pprint
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.agents.url_agent.nodes import scrape_node

class MockManager:
    async def scrape_url(self, url):
        return {"status": "failed", "error": "ERR_NAME_NOT_RESOLVED", "url": url}

async def run_test():
    state = {
        "current_url": "http://3nwdavin84.com",
        "playwright_manager": MockManager(),
        "visited_history": [],
        "sms_content": "선물:50000[원]불 사 조 출 현5 0 0 장 획 득 추 8 4 3nwdvin84.com"
    }
    
    res1 = await scrape_node(state)
    pprint.pprint(res1)

asyncio.run(run_test())
