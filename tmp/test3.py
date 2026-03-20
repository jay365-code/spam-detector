import sys
import os
import asyncio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.agents.url_agent.nodes import scrape_node, analyze_node

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
    
    # 1. Run scrape_node
    print("Running scrape_node...")
    res1 = await scrape_node(state)
    print("scrape_node returned:", res1)
    
    # Update state with scrape_node output (like LangGraph does)
    state.update(res1)
    
    # 2. Run analyze_node
    print("\nRunning analyze_node...")
    res2 = await analyze_node(state)
    print("analyze_node returned:", res2)

asyncio.run(run_test())
