import asyncio
import os
import sys
import json
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from dotenv import load_dotenv
load_dotenv(override=True)

from app.core.logging_config import setup_logging
setup_logging()

from app.agents.content_agent.agent import ContentAnalysisAgent
from app.agents.url_agent.agent import UrlAnalysisAgent
from app.agents.ibse_agent.service import IBSEAgentService
from app.graphs.batch_flow import create_batch_graph

async def main():
    content_agent = ContentAnalysisAgent()
    url_agent = UrlAnalysisAgent()
    ibse_service = IBSEAgentService()
    
    batch_graph = create_batch_graph(content_agent, url_agent, ibse_service)
    
    test_file = r"c:\Users\leejo\Project\AI Agent\Spam Detector\spams\safe_url_test.txt"
    with open(test_file, "r", encoding="utf-8") as f:
        messages = [line.strip() for line in f.readlines() if line.strip()]
        
    print(f"Testing {len(messages)} messages...")
    
    for i, msg in enumerate(messages):
        out_str = []
        out_str.append(f"\n==============================================")
        out_str.append(f"--- [Test {i+1}] ---")
        out_str.append(f"Message: {msg}")
        state = {
            "message": msg,
            "s1_result": {},
            "prefetched_context": None,
            "pre_parsed_url": None,
            "pre_parsed_only_mode": False
        }
        res = await batch_graph.ainvoke(state)
        final = res.get("final_result", {})
        
        out_str.append(f"==============================================")
        out_str.append(f"IS_SPAM: {final.get('is_spam')}")
        out_str.append(f"CLASS: {final.get('semantic_class')} ({final.get('learning_label')})")
        out_str.append(f"REASON: {final.get('reason')}")
        out_str.append(f"DROP_URL: {final.get('drop_url', False)}")
        out_str.append(f"IBSE_SIG: {final.get('ibse_signature')}")
        
        with open("test_safe_url_result.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(out_str) + "\n")
            
if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
