import sys
import os

# add path
sys.path.append(os.path.join(os.path.dirname(__file__), "backend/app"))

from graphs.batch_flow import create_batch_graph, BatchState

class MockContentAgent:
    def check(self, msg, s1, content_context=None):
        return {"is_spam": False, "reason": "Looks okay.", "classification_code": "0"}
    async def acheck(self, msg, s1, content_context=None):
        return self.check(msg, s1, content_context)

class MockUrlAgent:
    async def acheck(self, msg, content_context=None, decoded_text=None, pre_parsed_url=None, pre_parsed_only_mode=False, playwright_manager=None):
        return {"is_spam": True, "reason": "Mock malicious url found."}

class MockIbseService:
    async def process_message(self, msg):
        return {}

def test_router():
    graph_app = create_batch_graph(MockContentAgent(), MockUrlAgent(), MockIbseService())
    
    state = {
        "message": "안녕하세요. 이건 그냥 테스트입니다. (URL 없음)",
        "s1_result": {},
        "pre_parsed_url": "http://malicious.com",
        "pre_parsed_only_mode": True
    }
    
    import asyncio
    result = asyncio.run(graph_app.ainvoke(state))
    print("Final Result:", result.get("final_result"))

if __name__ == "__main__":
    test_router()
