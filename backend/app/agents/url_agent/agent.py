from langgraph.graph import StateGraph, END
from .state import SpamState
from .nodes import extract_node, scrape_node, analyze_node, select_link_node

# 그래프 정의
workflow = StateGraph(SpamState)

# 노드 등록
workflow.add_node("extract", extract_node)
workflow.add_node("scrape", scrape_node)
workflow.add_node("analyze", analyze_node)
workflow.add_node("select_link", select_link_node)

# 엣지(Edge) 정의 함수
def router_logic(state: SpamState):
    # URL이 없으면 종료
    if not state.get("target_urls"):
        return END
        
    # 최종 판단이 났으면 종료
    if state.get("is_final"):
        return END
        
    # 깊이 제한 도달 시 종료
    if state.get("depth", 0) >= state.get("max_depth", 2):
        return END
        
    # 그렇지 않으면 링크 선택 (재귀) - 현재는 단순화를 위해 종료로 연결될 수 있음
    return "select_link"

def extract_router(state: SpamState):
    if not state.get("target_urls"):
        return END
    return "scrape"

# 그래프 연결
workflow.set_entry_point("extract")

workflow.add_conditional_edges(
    "extract",
    extract_router,
    {
        "scrape": "scrape",
        END: END
    }
)

workflow.add_edge("scrape", "analyze")

workflow.add_conditional_edges(
    "analyze",
    router_logic,
    {
        END: END,
        "select_link": "select_link"
    }
)

# select_link 뒤에도 종료 조건 체크 (무한 루프 방지)
def select_link_router(state: SpamState):
    if state.get("is_final"):
        return END
    if not state.get("current_url"):
        return END
    return "scrape"

workflow.add_conditional_edges(
    "select_link",
    select_link_router,
    {
        END: END,
        "scrape": "scrape"
    }
)

# 컴파일
isaa_agent_app = workflow.compile()

import asyncio
from typing import Dict, Any, Callable, Awaitable
import logging

logger = logging.getLogger(__name__)

class UrlAnalysisAgent:
    """
    Wrapper class for ISAA LangGraph Agent to be compatible with main pipeline.
    """
    def __init__(self):
        pass

    def check(self, message: str, decoded_text: str = None) -> Dict[str, Any]:
        """
        Stage 3: URL Deep Dive
        
        Args:
            message: SMS 메시지 내용
            decoded_text: 난독화 디코딩된 텍스트 (있으면 URL 추출 시 사용)
        """
        initial_state = {
            "sms_content": message,
            "decoded_text": decoded_text,
            "target_urls": [],
            "visited_history": [],
            "scraped_data": {},
            "depth": 0,
            "max_depth": 2, 
            "is_final": False
        }
        
        try:
            # Sync wrapper for asyncio run
            result_state = asyncio.run(isaa_agent_app.ainvoke(initial_state))
            
            is_spam = result_state.get("is_spam")
            prob = result_state.get("spam_probability", 0.0)
            reason = result_state.get("reason", "Analysis completed")
            classification_code = result_state.get("classification_code")
            
            if is_spam is None:
                is_spam = False
                reason += " (Inconclusive)"

            return {
                "is_spam": is_spam,
                "spam_probability": prob,
                "classification_code": classification_code,
                "reason": reason
            }
            
        except Exception as e:
            print(f"ISAA Agent Error: {e}")
            return {
                "is_spam": False,
                "reason": f"ISAA Error: {str(e)}"
            }

    async def acheck(self, message: str, status_callback: Callable[[str], Awaitable[None]] = None, content_context: Dict[str, Any] = None, decoded_text: str = None) -> Dict[str, Any]:
        """
        Async version of check for WebSocket compatibility with Status Streaming
        
        Args:
            message: SMS 메시지 내용
            status_callback: 상태 업데이트 콜백
            content_context: Content Agent 분석 결과 (URL Agent 판단 시 참고용)
            decoded_text: 난독화 디코딩된 텍스트 (있으면 URL 추출 시 사용)
        """
        initial_state = {
            "sms_content": message,
            "decoded_text": decoded_text,  # 난독화 디코딩 텍스트
            "target_urls": [],
            "visited_history": [],
            "scraped_data": {},
            "depth": 0,
            "max_depth": 2, 
            "is_final": False,
            "content_context": content_context  # Content Agent 결과 전달
        }
        
        try:
            if status_callback:
                await status_callback("🔍 Initializing Analysis...")

            # Use astream to get updates from each node
            final_state = initial_state.copy()
            
            async for output in isaa_agent_app.astream(initial_state):
                for node_name, node_output in output.items():
                    # Update simple state accumulator
                    if isinstance(node_output, dict):
                        final_state.update(node_output)
                    
                    # Status messages based on node
                    log_msg = f"Completed node: {node_name}"
                    user_msg = f"Processing: {node_name}..."
                    
                    if node_name == "extract":
                        count = len(node_output.get('target_urls', []))
                        user_msg = f"🔗 Link Extraction: Found {count} URL(s)"
                    elif node_name == "scrape":
                        url = node_output.get('scraped_data', {}).get('url', 'Unknown')
                        user_msg = f"🌐 Web Scraping: {url}"
                    elif node_name == "analyze":
                        # If analysis is done
                        user_msg = f"🧠 AI Analysis Completed"

                    logger.info(f"[ISAA] {node_name.upper()} -> {log_msg}")
                    
                    if status_callback:
                        await status_callback(user_msg)

            # Use final_state for result
            result_state = final_state
            
            is_spam = result_state.get("is_spam")
            prob = result_state.get("spam_probability", 0.0)
            reason = result_state.get("reason", "Analysis completed")
            classification_code = result_state.get("classification_code")
            
            # Extract detailed metrics
            scraped_data = result_state.get("scraped_data", {})
            popup_count = scraped_data.get("popup_count", 0)
            captcha_detected = scraped_data.get("captcha_detected", False)
            depth = result_state.get("depth", 0)
            
            # URL Redirection Info
            extracted_url = result_state.get("current_url", "Unknown")
            final_url = scraped_data.get("url", "Unknown")
            
            if is_spam is None:
                is_spam = False
                reason += " (Inconclusive)"

            return {
                "is_spam": is_spam,
                "spam_probability": prob,
                "classification_code": classification_code,
                "reason": reason,
                "details": {
                    "popup_count": popup_count,
                    "captcha_detected": captcha_detected,
                    "depth": depth,
                    "extracted_url": extracted_url,
                    "final_url": final_url
                }
            }
        except Exception as e:
            logger.error(f"ISAA Agent Async Error: {e}")
            return {
                "is_spam": False,
                "reason": f"ISAA Error: {str(e)}"
            }
