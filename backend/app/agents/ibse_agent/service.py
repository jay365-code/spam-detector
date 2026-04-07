import logging
import uuid
from typing import Dict, Any

from app.agents.ibse_agent.state import IBSEState
from app.agents.ibse_agent.utils import preprocess_text
from app.agents.ibse_agent.agent import ibse_graph

logger = logging.getLogger(__name__)

class IBSEAgentService:
    def __init__(self):
        # [NEW] 실시간 시그니처 글로벌 캐시
        self.signature_cache = []

    from typing import Callable, Optional

    async def process_message(self, text: str, message_id: str = None, status_callback: Optional[Callable[[str], None]] = None, obfuscated_urls: list[str] = None) -> Dict[str, Any]:
        """
        Processes a single message text through the IBSE pipeline using LangGraph.
        """
        if message_id is None:
            message_id = str(uuid.uuid4())
            
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
            
        if status_callback: status_callback("텍스트 전처리 중...")
        match_text = preprocess_text(text)
        
        # 시스템 메모리 캐시 체크 (LLM 호출 방지 및 완벽한 파편화 제어)
        import re
        spaceless_text = re.sub(r'[ \t\r\n\f\v]+', '', match_text)
        for cached_sig in self.signature_cache:
            if cached_sig in spaceless_text:
                if status_callback: status_callback(f"캐시 매칭 완료: {cached_sig}")
                logger.info(f"IBSE Cache Hit for {message_id}: {cached_sig}")
                return {
                    "message_id": message_id,
                    "decision": "use_string (cached)",
                    "signature": cached_sig,
                    "reason": "사전 추출된 시그니처 캐시 매칭으로 LLM 호출 생략 및 통일화",
                    "byte_len": len(cached_sig.encode('cp949', errors='ignore')),
                    "candidates_count": 0
                }
        
        # (URL 감지 시 IBSE 추출을 생략하던 Pre-LLM Optimization 제거됨)
        
        state: IBSEState = {
            "message_id": message_id,
            "original_text": text,
            "match_text": match_text,
            "candidates_20": [],
            "candidates_40": [],
            "selected_decision": None,
            "selected_candidate": None,
            "final_result": None,
            "retry_count": 0,
            "error": None,
            "obfuscated_urls": obfuscated_urls or []
        }
        
        final_state = state # Fallback
        
        try:
            logger.info(f"Starting IBSE Analysis for {message_id} (LangGraph)")
            
            # Use astream to track progress (it's an async graph now)
            if status_callback: status_callback("분석 시작 (Graph Init)...")
            
            async for output in ibse_graph.astream(state):
                for node_name, node_state in output.items():
                    logger.info(f"IBSE Node Finished: {node_name}")
                    
                    if node_name == "generate_candidates":
                        c20 = len(node_state.get("candidates_20", []))
                        c40 = len(node_state.get("candidates_40", []))
                        if status_callback: 
                           status_callback(f"후보 생성 완료 (20byte: {c20}개, 40byte: {c40}개)")
                           status_callback("LLM 최적 시그니처 선택 중...")
                           
                    elif node_name == "select_signature":
                        if status_callback: 
                            status_callback("선택된 시그니처 검증 중...")
                            
                    elif node_name == "validate":
                         # Check if retry is happening
                         if node_state.get("error") and node_state.get("retry_count", 0) < 1:
                             if status_callback: status_callback("검증 실패. 재시도 중 (Repair)...")
                    
                    elif node_name == "increment_retry":
                         if status_callback: status_callback("재시도 준비 완료.")
                    
                    # Update final state tracker
                    final_state = node_state

            if status_callback: status_callback("분석 완료")
                
        except Exception as e:
            logger.error(f"IBSE Pipeline Error for {message_id}: {e}")
            return {
                "message_id": message_id,
                "decision": "ERROR",
                "signature": None,
                "reason": str(e),
                "byte_len": 0,
                "error": str(e)
            }
            
        final = final_state.get("final_result", {}) or {}
        
        # [중요] 모든 재시도 루프가 종료되었음에도 에러가 남아있다면, 최종 실패로 간주하고 unextractable로 덮어씌움
        if final_state.get("error"):
            logger.warning(f"IBSE Pipeline finished with unresolved error for {message_id}: {final_state.get('error')}. Forcing 'unextractable'.")
            final["decision"] = "unextractable"
            final["signature"] = None
            final["reason"] = f"검증 실패 (Retry 초과): {final_state.get('error')}"
            final["byte_len_cp949"] = 0
        
        # Calculate Candidate Count safely
        c_count = len(final_state.get("candidates_20", [])) + len(final_state.get("candidates_40", []))

        result = {
            "message_id": message_id,
            "decision": final.get("decision", "unknown"),
            "signature": final.get("signature"),
            "reason": final.get("reason", "No reason provided"),
            "byte_len": final.get("byte_len_cp949", 0),
            "candidates_count": c_count
        }
        
        # 성공적으로 추출된 시그니처를 캐시에 등록 (추후 재사용 위해)
        sig_val = result.get("signature")
        # 단, 예외 판정("unextractable", "NONE", 빈값)은 캐시하지 않음
        if sig_val and str(sig_val).strip() and str(sig_val).upper() != "NONE":
            # 중복 등록 방지
            if sig_val not in self.signature_cache:
                self.signature_cache.append(sig_val)
                logger.info(f"IBSE Cache Added: {sig_val}")
        
        logger.info(f"IBSE Result for {message_id}: decision={result['decision']}, sig={result['signature']}, len={result['byte_len']}")
        return result
