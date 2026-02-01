
import sys
import os
import asyncio
import logging

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.agents.url_agent.nodes import extract_node

async def test():
    # Test case from user
    message = "· 새해 첫주말 · [50,000 원] 지급 · 출??? OK [ dⓢlp①③7⑤.cc ] · 돈방석 앉는길"
    state = {"sms_content": message, "decoded_text": None}
    
    print(f"Testing message: {message}")
    result = await extract_node(state)
    print(f"Result: {result}")
    
    urls = result.get("target_urls", [])
    expected = "http://dslp1375.cc"
    
    # Check if expected URL (or without http) is in the list
    if any(u == expected or u == "dslp1375.cc" for u in urls):
        print("SUCCESS: Found normalized URL")
    else:
        print("FAIL: Did not find normalized URL")

if __name__ == "__main__":
    asyncio.run(test())
