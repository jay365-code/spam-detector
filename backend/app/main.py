from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
import asyncio
import sys

# **CRITICAL FIX**: Force ProactorEventLoop on Windows for Playwright/Subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uuid
from typing import List, Dict
from app.services.rule_service import RuleBasedFilter
from app.agents.content_agent.agent import ContentAnalysisAgent
from app.agents.url_agent.agent import UrlAnalysisAgent
from app.utils.excel_handler import ExcelHandler
from app.core.constants import SPAM_CODE_MAP

import logging

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

import warnings
# Suppress noisy warnings
warnings.filterwarnings("ignore")

app = FastAPI()

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        # Map client_id to WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        # Map client_id to list of buffered messages (offline queue)
        self.message_queue: Dict[str, List[dict]] = {}
        # HITL Events
        import threading
        self.hitl_events: Dict[str, threading.Event] = {}
        self.hitl_responses: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket Connected: Client {client_id}")
        
        # Replay buffered messages
        if client_id in self.message_queue:
            queue = self.message_queue[client_id]
            if queue:
                logger.info(f"Replaying {len(queue)} buffered messages for {client_id}")
                for msg in queue:
                    try:
                        await websocket.send_json(msg)
                    except Exception as e:
                        logger.error(f"Error replaying message: {e}")
                self.message_queue[client_id] = [] # Clear queue

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"WebSocket Disconnected: Client {client_id}")

    # HITL Methods (Thread-Safe Event Handling)
    def register_hitl_request(self, client_id: str):
        import threading
        event = threading.Event()
        self.hitl_events[client_id] = event
        return event

    def resolve_hitl_request(self, client_id: str, response_data: dict):
        if client_id in self.hitl_events:
            self.hitl_responses[client_id] = response_data
            self.hitl_events[client_id].set()

    def get_hitl_response(self, client_id: str) -> dict:
        return self.hitl_responses.get(client_id, {})

    def cleanup_hitl(self, client_id: str):
        self.hitl_events.pop(client_id, None)
        self.hitl_responses.pop(client_id, None)

    async def send_personal_message(self, message: dict, client_id: str):
        if client_id in self.active_connections:
            try:
                # logger.info(f"Sending to {client_id}: {message}") 
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send message to active client {client_id}: {e}")
                # Fallback to buffer if send fails
                self._buffer_message(client_id, message)
        else:
            # Client offline, buffer message
            self._buffer_message(client_id, message)

    def _buffer_message(self, client_id: str, message: dict):
        if client_id not in self.message_queue:
            self.message_queue[client_id] = []
        
        self.message_queue[client_id].append(message)
        
        # Limit buffer size (e.g., keep last 500 messages to prevent memory overflow)
        if len(self.message_queue[client_id]) > 500:
            self.message_queue[client_id].pop(0)

manager = ConnectionManager()


@app.on_event("startup")
async def startup_event():
    logger.info("✅ Server Application Started! Ready for requests.")

@app.get("/health")
async def health_check():
    logger.info("✅ Health Check Endpoint Reached!")
    return {"status": "ok"}

# ========== FN Examples RAG API ==========
from app.services.fn_examples_service import get_fn_examples_service
from pydantic import BaseModel

class FnExampleCreate(BaseModel):
    message: str
    label: str = "SPAM"
    code: str
    category: str
    reason: str

class FnExampleUpdate(BaseModel):
    message: str = None
    label: str = None
    code: str = None
    category: str = None
    reason: str = None

@app.get("/api/fn-examples")
async def get_fn_examples():
    """FN 예시 전체 조회"""
    try:
        service = get_fn_examples_service()
        examples = service.get_all_examples()
        return {"success": True, "data": examples, "total": len(examples)}
    except Exception as e:
        logger.error(f"FN Examples GET Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fn-examples/stats")
async def get_fn_examples_stats():
    """FN 예시 통계 조회"""
    try:
        service = get_fn_examples_service()
        stats = service.get_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"FN Examples Stats Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fn-examples/{example_id}")
async def get_fn_example(example_id: str):
    """특정 FN 예시 조회"""
    try:
        service = get_fn_examples_service()
        example = service.get_example_by_id(example_id)
        if not example:
            raise HTTPException(status_code=404, detail="Example not found")
        return {"success": True, "data": example}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FN Example GET Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fn-examples")
async def create_fn_example(example: FnExampleCreate):
    """새 FN 예시 추가"""
    try:
        service = get_fn_examples_service()
        result = service.add_example(
            message=example.message,
            label=example.label,
            code=example.code,
            category=example.category,
            reason=example.reason
        )
        logger.info(f"FN Example Created: {result['id']}")
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"FN Example Create Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/fn-examples/{example_id}")
async def update_fn_example(example_id: str, example: FnExampleUpdate):
    """FN 예시 수정"""
    try:
        service = get_fn_examples_service()
        result = service.update_example(
            example_id=example_id,
            message=example.message,
            label=example.label,
            code=example.code,
            category=example.category,
            reason=example.reason
        )
        if not result:
            raise HTTPException(status_code=404, detail="Example not found")
        logger.info(f"FN Example Updated: {example_id}")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FN Example Update Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/fn-examples/{example_id}")
async def delete_fn_example(example_id: str):
    """FN 예시 삭제"""
    try:
        service = get_fn_examples_service()
        success = service.delete_example(example_id)
        if not success:
            raise HTTPException(status_code=404, detail="Example not found or delete failed")
        logger.info(f"FN Example Deleted: {example_id}")
        return {"success": True, "message": "Deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FN Example Delete Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fn-examples/search/{query}")
async def search_fn_examples(query: str, k: int = 3):
    """유사 FN 예시 검색"""
    try:
        service = get_fn_examples_service()
        results = service.search_similar(query, k=k)
        return {"success": True, "data": results, "total": len(results)}
    except Exception as e:
        logger.error(f"FN Examples Search Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_DIR = "../data/uploads"
OUTPUT_DIR = "../data/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize Services & Agents
from app.agents.ibse_agent.service import IBSEAgentService

# Initialize Services & Agents
rule_filter = RuleBasedFilter()
rag_filter = ContentAnalysisAgent()
url_filter = UrlAnalysisAgent()
excel_handler = ExcelHandler()
ibse_service = IBSEAgentService()

def process_message(message: str) -> dict:
    """
    Orchestrates the 3-Stage Filtering Pipeline
    """
    # Stage 1: Rule-Based
    # logger.info("    [Stage 1] Rule Checking...")
    s1_result = rule_filter.check(message)
    
    # If HAM confirmed by Rule (e.g., Non-Korean message)
    if s1_result["is_spam"] is False:
        s1_code = s1_result.get("classification_code")
        s1_reason = s1_result.get("reason", "Rule-based HAM")
        logger.info(f"    -> Rule-based HAM (Code: {s1_code})")
        logger.info(f"\n[DEBUG RESULT]\nMessage: {message}\nIs Spam: False\nCode: {s1_code}\nReason: {s1_reason}\n")
        return {
            "is_spam": False,
            "classification_code": s1_code,
            "spam_probability": 0.0,
            "reason": s1_reason,
            "input_tokens": 0,
            "output_tokens": 0
        }

    # Stage 2: RAG + LLM + Antigravity
    # We pass s1_result to include detected patterns in prompt
    logger.info("    [Stage 2] AI Analysis (RAG + LLM)...")
    s2_result = rag_filter.check(message, s1_result)
    
    final_is_spam = s2_result["is_spam"]
    final_code = s2_result["classification_code"]
    final_reason = s2_result.get("reason", "No reason provided")
    final_prob = s2_result.get("spam_probability", 0.0)
    
    # Extract tokens (default to 0 if missing)
    input_tokens = s2_result.get("input_tokens", 0)
    output_tokens = s2_result.get("output_tokens", 0)

    # Common return dictionary builder
    def build_result(is_spam, code, reason):
        return {
            "is_spam": is_spam,
            "classification_code": code,
            "spam_probability": final_prob,
            "reason": reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    # Logic Update:
    # If Stage 2 is SPAM -> Finalize as SPAM (skip Stage 3)
    if final_is_spam:
        logger.info(f"    -> Identified as SPAM (Code: {final_code})")
        logger.info(f"\n[DEBUG RESULT]\nMessage: {message}\nIs Spam: {final_is_spam}\nProbability: {final_prob}\nCode: {final_code}\nReason: {final_reason}\nTokens: In={input_tokens}, Out={output_tokens}\n")
        return build_result(True, final_code, final_reason)
    
    # Step 3: URL Deep Dive (Conditional)
    # Check URL if Content is Spam OR if Content is Safe but URL exists
    import re
    url_pattern = re.compile(r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})')
    
    # 원본 메시지에서 URL 체크
    has_url = bool(url_pattern.search(message))
    
    # 난독화 디코딩된 텍스트에서도 URL 체크
    decoded_text = s1_result.get("decoded_text")
    if decoded_text and not has_url:
        has_url = bool(url_pattern.search(decoded_text))
    
    # s1에서 이미 추출한 decoded_urls가 있으면 URL 존재
    if s1_result.get("decoded_urls"):
        has_url = True
    
    if has_url:
        logger.info("    [Stage 3] URL Deep Dive...")
        isaa_result = url_filter.check(message, decoded_text=decoded_text)
        
        url_is_spam = isaa_result.get("is_spam")
        reason_lower = isaa_result.get("reason", "").lower()
        is_inconclusive = any(x in reason_lower for x in ["error", "inconclusive", "insufficient", "image only"])
        
        if is_inconclusive:
             # Inconclusive -> Trust Content Verdict
             final_reason += f" | [URL: Suspected but Inconclusive]"
        elif url_is_spam:
             # Confirmed Spam -> Force SPAM
             logger.info("    -> Suspicious URL Confirmed! Overriding to SPAM.")
             final_is_spam = True
             final_reason += f" | [URL: DETECTED SPAM]"
             # Ideally map code, but for now strictly override verdict
             if not final_code or final_code == "0":
                  final_code = isaa_result.get("classification_code")
        else:
             # Confirmed Safe -> Force HAM (Override Content SPAM if needed)
             if final_is_spam:
                  logger.info("    -> URL Confirmed Safe! Overriding Content SPAM to HAM.")
                  final_is_spam = False
                  final_reason += " | [URL: CONFIRMED SAFE (Override)]"
                  final_code = None


    logger.info("    -> Classified as HAM.")
    logger.info(f"\n[DEBUG RESULT]\nMessage: {message}\nIs Spam: {final_is_spam}\nProbability: {final_prob}\nCode: {final_code}\nReason: {final_reason}\nTokens: In={input_tokens}, Out={output_tokens}\n")
    return build_result(final_is_spam, final_code, final_reason)


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            # Listen for client messages
            data_str = await websocket.receive_text()
            try:
                import json
                data = json.loads(data_str)
                logger.info(f"Received from {client_id}: {data}")

                if data.get("type") == "HITL_RESPONSE":
                    logger.info(f"HITL Response Received for {client_id}: {data}")
                    manager.resolve_hitl_request(client_id, data)
                
                elif data.get("type") == "CHAT_MESSAGE":
                    user_msg = data.get("content", "")
                    mode = data.get("mode", "Unified") # Default to Unified "Smart" Mode
                    
                    logger.info(f"Chat Message from {client_id} (Mode: {mode}): {user_msg}")
                    
                    if user_msg:
                        # Signal Start of Stream
                        await manager.send_personal_message({
                            "type": "CHAT_STREAM_START",
                            "content": ""
                        }, client_id)
                        
                        # Helper for Status Updates
                        async def send_status(text: str):
                            await manager.send_personal_message({
                                "type": "PROCESS_STATUS",
                                "content": text
                            }, client_id)
                            
                        # Helper for generic text chunk
                        async def send_text_chunk(text: str):
                            await manager.send_personal_message({
                                "type": "CHAT_STREAM_CHUNK",
                                "content": text
                            }, client_id)

                        # --- MODE DISPATCHER ---
                        
                        # 1. IBSE Mode (Signature Only)
                        if mode == "IBSE":
                             await send_status("분석 준비 중...")
                             loop = asyncio.get_running_loop()
                             import re
                             spaceless_msg = re.sub(r'[ \t\r\n\f\v]+', '', user_msg)
                             
                             try:
                                 ibse_result = await loop.run_in_executor(
                                     None, 
                                     lambda: ibse_service.process_message(spaceless_msg, status_callback=send_status)
                                 )
                                 
                                 sig = ibse_result.get('signature')
                                 decision = ibse_result.get('decision')
                                 reason = ibse_result.get('reason')
                                 byte_len = ibse_result.get('byte_len', 0)
                                 
                                 response_text = f"**[IBSE 시그니처 추출 결과]**\n"
                                 response_text += f"🔧 **전처리(공백제거)**: `{spaceless_msg}`\n\n"
                                 
                                 if sig:
                                     response_text += f"✅ **추출 성공**\n- **시그니처**: `{sig}`\n- **길이**: {byte_len} bytes (CP949)\n"
                                 elif decision == "unextractable":
                                     response_text += f"🛑 **추출 생략 (대상 아님)**\n- **사유**: {reason}\n"
                                 else:
                                     response_text += f"⚠️ **오류/실패** (Type: {decision})\n- **사유**: {reason}\n"

                                 await send_text_chunk(response_text)
                                 
                             except Exception as e:
                                 logger.error(f"IBSE execution error: {e}")
                                 await send_text_chunk(f"⚠️ **오류 발생**: {str(e)}")

                        # 2. URL Mode (URL Only)
                        elif mode == "URL":
                            # URL 모드에서도 난독화 체크
                            s1_url = rule_filter.check(user_msg)
                            decoded_text_url = s1_url.get("decoded_text")
                            isaa_result = await url_filter.acheck(user_msg, status_callback=send_status, decoded_text=decoded_text_url)
                            
                            analysis_text = f"**[ISAA URL 분석 결과]**\n"
                            if isaa_result["is_spam"]:
                                analysis_text += f"🚫 **스팸 탐지됨** ({int(isaa_result.get('spam_probability',0)*100)}%)\n"
                                analysis_text += f"- 분류: {isaa_result.get('classification_code', 'Unknown')}\n"
                                analysis_text += f"- 사유: {isaa_result.get('reason')}\n"
                            else:
                                analysis_text += f"✅ **정상 URL**\n- 사유: {isaa_result.get('reason')}\n"
                                
                            details = isaa_result.get("details", {})
                            analysis_text += f"\n**[상세 분석 정보]**\n"
                            analysis_text += f"- URL 경로: {details.get('extracted_url', 'N/A')} → {details.get('final_url', 'N/A')}\n"
                            analysis_text += f"- 팝업/캡차: {details.get('popup_count', 0)}개 / {'있음' if details.get('captcha_detected') else '없음'}\n"

                            await send_text_chunk(analysis_text)

                        # 3. TEXT Mode (Content Only) - Isolated!
                        elif mode == "TEXT":
                            # Use new async check with callbacks
                            s1 = rule_filter.check(user_msg) # Stage 1 is fast/local
                            
                            # Rule-based HAM (e.g., Non-Korean message)
                            if s1.get("is_spam") is False:
                                s1_code = s1.get("classification_code", "HAM-5")
                                s1_reason = s1.get("reason", "Rule-based HAM")
                                code_map = SPAM_CODE_MAP
                                code_desc = code_map.get(s1_code, "외국어 메시지")
                                
                                msg_text = f"✅ **정상 문자** - {s1_code}. {code_desc}\n- 사유: {s1_reason}\n"
                                await send_text_chunk(msg_text)
                                
                                # Signal End of Stream
                                await manager.send_personal_message({
                                    "type": "CHAT_STREAM_END",
                                    "content": ""
                                }, client_id)
                                continue
                            
                            # Calls Content Agent asynchronously
                            s2_result = await rag_filter.acheck(user_msg, s1, status_callback=send_status)
                            
                            # Format & Send Result
                            final_is_spam = s2_result.get("is_spam")
                            reason = s2_result.get("reason")
                            prob = s2_result.get("spam_probability", 0)
                            code = s2_result.get("classification_code", "Unk")
                            
                            code_map = SPAM_CODE_MAP
                            import re
                            msg_text = ""
                            
                            if final_is_spam:
                                match = re.search(r'\d+', str(code))
                                raw_code = match.group(0) if match else str(code)
                                code_desc = code_map.get(raw_code, "기타")
                                msg_text = f"🚫 **스팸 의심** ({int(prob*100)}%) - {raw_code}. {code_desc}\n- 사유: {reason}\n"
                            elif final_is_spam is None:
                                msg_text = f"⚠️ **판단 보류 (HITL)**\n- 사유: {reason}\n"
                            else:
                                msg_text = f"✅ **정상 문자**\n- 사유: {reason}\n"
                                
                            await send_text_chunk(msg_text)
                            # NOTE: No Auto-IBSE or URL check here. Completely Isolated.

                        # 4. Unified / Smart Mode (Default)
                        else:
                            # Step A: Rule-based Check
                            s1 = rule_filter.check(user_msg)
                            
                            # Rule-based HAM (e.g., Non-Korean message)
                            if s1.get("is_spam") is False:
                                s1_code = s1.get("classification_code", "HAM-5")
                                s1_reason = s1.get("reason", "Rule-based HAM")
                                code_map = SPAM_CODE_MAP
                                code_desc = code_map.get(s1_code, "외국어 메시지")
                                
                                msg_text = f"✅ **정상 문자** - {s1_code}. {code_desc}\n- 사유: {s1_reason}\n\n"
                                await send_text_chunk(msg_text)
                                
                                # Signal End of Stream
                                await manager.send_personal_message({
                                    "type": "CHAT_STREAM_END",
                                    "content": ""
                                }, client_id)
                                continue
                            
                            # Step B: Content Analysis
                            s2_result = await rag_filter.acheck(user_msg, s1, status_callback=send_status)
                            
                            final_is_spam = s2_result.get("is_spam")
                            content_reason = s2_result.get("reason")
                            prob = s2_result.get("spam_probability", 0)
                            code = s2_result.get("classification_code", "Unk")
                            
                            code_map = SPAM_CODE_MAP
                            
                            # Display Content Result
                            msg_text = ""
                            if final_is_spam:
                                import re
                                match = re.search(r'\d+', str(code))
                                raw_code = match.group(0) if match else str(code)
                                code_desc = code_map.get(raw_code, "기타")
                                
                                msg_text = f"🚫 **스팸 의심** ({int(prob*100)}%) - {raw_code}. {code_desc}\n- 사유: {content_reason}\n\n"
                            elif final_is_spam is None:
                                msg_text = f"⚠️ **판단 보류 (HITL)**\n- 사유: {content_reason}\n\n"
                            else:
                                msg_text = f"✅ **정상 문자**\n- 사유: {content_reason}\n\n"
                            
                            await send_text_chunk(msg_text)

                            # Step B: Conditional URL Check
                            # Check URL if Content is Spam OR if Content is Safe but URL exists
                            import re
                            url_pattern = re.compile(r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})')
                            has_url = bool(url_pattern.search(user_msg))
                            
                            # 난독화 디코딩된 텍스트에서도 URL 체크
                            decoded_text = s1.get("decoded_text")
                            if decoded_text and not has_url:
                                has_url = bool(url_pattern.search(decoded_text))
                            
                            # s1에서 이미 추출한 decoded_urls가 있으면 URL 존재
                            if s1.get("decoded_urls"):
                                has_url = True
                            
                            isaa_result = None
                            
                            if has_url:
                                await send_text_chunk("---\n")
                                # Content Agent 결과를 URL Agent에 전달 (연관성 확보)
                                isaa_result = await url_filter.acheck(user_msg, status_callback=send_status, content_context=s2_result, decoded_text=decoded_text)
                                
                                url_text = f"**[URL 분석]** {'🚫 위험' if isaa_result.get('is_spam') else '✅ 안전'}\n"
                                url_text += f"- 사유: {isaa_result.get('reason')}\n"
                                await send_text_chunk(url_text)
                                
                                # Bidirectional Override Logic
                                url_is_spam = isaa_result.get('is_spam')
                                reason_lower = isaa_result.get("reason", "").lower()
                                is_inconclusive = any(x in reason_lower for x in ["error", "inconclusive", "insufficient", "image only"])
                                
                                if is_inconclusive:
                                     pass # Trust Content
                                elif url_is_spam:
                                     # Case 4: Content(HAM) -> URL(SPAM) : SPAM Confirmed
                                     final_is_spam = True
                                     # URL Agent의 classification_code로 업데이트 (Content가 "0" 기타이거나 없을 때)
                                     url_code = isaa_result.get('classification_code')
                                     original_code = code
                                     if url_code and (not code or code == "0" or code == "Unk"):
                                          code = url_code
                                          logger.info(f"[URL Override] Updated code from '{original_code}' to '{code}' based on URL analysis")
                                          # 코드 변경 알림 출력
                                          new_code_desc = code_map.get(str(code), "기타")
                                          await send_text_chunk(f"\n⚠️ **코드 업데이트**: {original_code} → **{code}. {new_code_desc}** (URL 분석 기반)\n")
                                else:
                                     # Case 2: Content(SPAM) -> URL(Safe) : HAM Confirmed
                                     if final_is_spam:
                                          final_is_spam = False
                                          code = None  # HAM으로 바뀌면 코드도 초기화
                                          content_reason += " | [URL: Confirmed Safe (Override)]" # Update display reason

                            # Step C: Auto-IBSE (Only if Spam)
                            if final_is_spam:
                                await send_text_chunk("---\n")
                                await send_status("[Auto] 시그니처 추출 시도...")
                                
                                loop = asyncio.get_running_loop()
                                ibse_res = await loop.run_in_executor(
                                     None, 
                                     lambda: ibse_service.process_message(user_msg, status_callback=send_status)
                                )
                                
                                sig = ibse_res.get('signature')
                                if sig:
                                    await send_text_chunk(f"**[시그니처]** ✅ `{sig}` 추출됨\n")
                                else:
                                    await send_text_chunk(f"**[시그니처]** 🛑 추출 없음 ({ibse_res.get('decision')})\n")

                            # Step D: Final Summary
                            if has_url: # Summary most useful when multiple factors exist
                                await send_text_chunk("\n---\n**📝 종합 의견**\n\n")
                                
                                # URL 분석 결과로 코드가 업데이트된 경우, s2_result 복사본에 반영
                                final_s2_result = s2_result.copy()
                                final_s2_result["is_spam"] = final_is_spam
                                final_s2_result["classification_code"] = code
                                
                                summary = await rag_filter.generate_final_summary(user_msg, final_s2_result, isaa_result)
                                await send_text_chunk(summary)

                        # Signal End of Stream
                        await manager.send_personal_message({
                            "type": "CHAT_STREAM_END",
                            "content": ""
                        }, client_id)

            except Exception as e:
                logger.error(f"Error parsing WS message: {e}")

    except WebSocketDisconnect:
        manager.disconnect(client_id)

@app.post("/upload")
async def upload_file(client_id: str = Form(...), file: UploadFile = File(...)):
    logger.info(f"DEBUG: Receive file upload request from Client {client_id}: {file.filename}")
    try:
        # Save uploaded file
        file_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file.filename)[1]
        input_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")
        
        llm_model = os.getenv("LLM_MODEL", "gpt-5-mini")
        original_name = os.path.splitext(file.filename)[0]
        output_filename = f"{original_name}_{llm_model}{file_ext}"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Define Progress Callback (Thread-safe)
        loop = asyncio.get_running_loop()
        
        def progress_callback(data: dict):
            asyncio.run_coroutine_threadsafe(
                manager.send_personal_message(data, client_id), loop
            )

        # Wrapper for process_message to inject HITL logic (Batch Compatible)
        def process_message_with_hitl(messages: list) -> list:
            """
            Processes a batch of messages.
            1. Rule Filter (Stage 1) - Individual
            2. RAG Filter (Stage 2) - Batch
            3. URL Filter (Stage 3) - Parallel for SPAM items
            4. HITL Check - Individual (Blocking)
            """
            
            import asyncio
            
            # Step 1: Stage 1 (Rule) for all
            s1_results = []
            for msg in messages:
                if not msg:
                    s1_results.append({"is_spam": False, "detected_pattern": "Empty"})
                else:
                    s1_results.append(rule_filter.check(msg))
            
            # Async Batch Orchestrator
            async def run_batch_pipeline():
                # A. Define Single Item Processing Function (Wraps Content + URL Logic per item)
                from app.graphs.batch_flow import create_batch_graph
                # Use global agents (Thread-safe/Async-safe assumed)
                batch_graph = create_batch_graph(rag_filter, url_filter, ibse_service)

                async def process_single_item(index, message, s1_res):
                    logger.info(f"    [Batch] Item {index+1} 분석 시작... (Unified Graph)")
                    
                    # Rule-based HAM (e.g., Non-Korean message) - Skip Graph
                    if s1_res.get("is_spam") is False:
                        s1_code = s1_res.get("classification_code")
                        s1_reason = s1_res.get("reason", "Rule-based HAM")
                        logger.info(f"    -> [Batch] Rule-based HAM (Code: {s1_code})")
                        logger.info(f"\n[DEBUG RESULT] (Rule-based HAM)\nMessage: {message}\nIs Spam: False\nCode: {s1_code}\nReason: {s1_reason}\n")
                        return index, {
                            "is_spam": False,
                            "classification_code": s1_code,
                            "spam_probability": 0.0,
                            "reason": s1_reason
                        }
                    
                    # Construct Input State
                    input_state = {
                        "message": message,
                        "s1_result": s1_res,
                        "content_result": None,
                        "url_result": None,
                        "ibse_result": None,
                        "final_result": None
                    }
                    
                    try:
                        # Invoke Graph
                        # ainvoke is async
                        graph_output = await batch_graph.ainvoke(input_state)
                        final_res = graph_output.get("final_result", {})
                        
                        # Logging
                        final_is_spam = final_res.get("is_spam")
                        final_code = final_res.get("classification_code")
                        final_prob = final_res.get("spam_probability", 0.0)
                        final_reason = final_res.get("reason", "")
                        
                        logger.info(f"\n[DEBUG RESULT] (Immediate)\nMessage: {message}\nIs Spam: {final_is_spam}\nProbability: {final_prob}\nCode: {final_code}\nReason: {final_reason}\n")
                        
                        return index, final_res
                        
                    except Exception as e:
                        logger.error(f"Graph Execution Error for Item {index}: {e}")
                        return index, {"is_spam": None, "reason": f"Graph Error: {e}"}

                # Create Tasks
                tasks = [process_single_item(i, messages[i], s1_results[i]) for i in range(len(messages))]
                
                # Run All
                # Note: Logging happens inside process_single_item immediately upon completion.
                # asyncio.gather preserves the order of results corresponding to the order of awaitables.
                results_with_idx = await asyncio.gather(*tasks)
                
                # Sort just in case (though gather guarantees order) and extract
                # results_with_idx is list of (index, result)
                sorted_results = sorted(results_with_idx, key=lambda x: x[0])
                completed_results = [r[1] for r in sorted_results]
                    
                return completed_results

            # Run Async Pipeline
            try:
                s2_results = asyncio.run(run_batch_pipeline())
            except Exception as e:
                logger.error(f"Batch Async Error: {e}")
                s2_results = [{"is_spam": None, "reason": f"Async Error: {e}"} for _ in messages]

            # Step 4: HITL & Finalize
            final_results = []
            for i, result in enumerate(s2_results):
                msg = messages[i]
                # Logging already done immediately above. 
                # Just HITL logic remains.
                
                # Check for HITL Condition (Code 30)
                # User Request: If prob >= 0.9, override Code 30 and mark as SPAM-1 (or similar) without asking user.
                spam_prob = result.get("spam_probability", 0.0)
                
                if result.get("classification_code") == "30":
                    if spam_prob >= 0.9:
                        logger.info(f"[HITL Override] Probability {spam_prob} >= 0.9. Marking as SPAM-1 without user check.")
                        result["is_spam"] = True
                        result["classification_code"] = "1" # Default to General/Illegal Spam
                        result["reason"] += " [Auto-Confirmed due to High Probability]"
                    else:
                        logger.info(f"[HITL] Triggered for message: {msg[:20]}...")
                    
                    # Notify Client
                    hitl_request = {
                        "type": "HITL_REQUEST",
                        "message": msg,
                        "spam_probability": result.get("spam_probability"),
                        "reason": result.get("reason")
                    }
                    asyncio.run_coroutine_threadsafe(
                        manager.send_personal_message(hitl_request, client_id), loop
                    ).result() # Wait for send
                    
                    # Block Thread & Wait
                    event = manager.register_hitl_request(client_id)
                    flag = event.wait(timeout=300) # Wait up to 5 mins
                    
                    if flag:
                        # User Responded
                        user_response = manager.get_hitl_response(client_id)
                        decision = user_response.get("decision", "HAM")
                        comment = user_response.get("comment")
                        
                        if decision == "SPAM":
                            result["is_spam"] = True
                            orig_code = result.get("classification_code", "0")
                            result["classification_code"] = orig_code if orig_code != "30" else "1" 
                            result["reason"] += " [Manually Marked as SPAM]"
                        else:
                            result["is_spam"] = False
                            result["classification_code"] = "0"
                            result["reason"] += " [Manually Marked as HAM]"
                            
                        if comment:
                             result["reason"] += f" 👤 {comment}"
                        else:
                             result["reason"] += " 👤"
                            
                        logger.info(f"[HITL] User decided: {decision}")
                        
                    else:
                        # Timeout
                        logger.warning("[HITL] Timeout. Defaulting to HAM.")
                        result["is_spam"] = False
                        result["classification_code"] = "0"
                        result["reason"] += " [HITL Timeout -> HAM]"
    
                    # Cleanup
                    manager.cleanup_hitl(client_id)
                
                final_results.append(result)
                
            return final_results
 
        
        # Determine Batch Size
        batch_size_env = int(os.getenv("LLM_BATCH_SIZE", 10))
        
        if file_ext.lower() == '.txt':
            # Process TXT (Blocking call -> Run in ThreadPool)
            # Process TXT (Blocking call -> Run in ThreadPool)
            result = await loop.run_in_executor(
                None, 
                lambda: excel_handler.process_kisa_txt(input_path, OUTPUT_DIR, process_message_with_hitl, progress_callback, batch_size=batch_size_env, original_filename=file.filename)
            )
            if isinstance(result, dict) and "filename" in result:
                output_filename = result["filename"]
        else:
            # Process Excel (Blocking call -> Run in ThreadPool)
            await loop.run_in_executor(
                None, 
                lambda: excel_handler.process_file(input_path, output_path, process_message_with_hitl, progress_callback, batch_size=batch_size_env)
            )
        
        return {"id": file_id, "filename": output_filename, "message": "Processing complete"}
        
    except Exception as e:
        logger.error(f"Error during upload/processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ExcelRowUpdate(BaseModel):
    """엑셀 행 업데이트 요청"""
    filename: str
    message: str  # 메시지로 행 찾기
    is_spam: bool
    classification_code: str
    reason: str
    spam_probability: float = 0.95

@app.put("/api/excel/update-row")
async def update_excel_row(update: ExcelRowUpdate):
    """엑셀 파일의 특정 행을 업데이트 + URL중복제거/문자문장차단등록 시트 동기화"""
    import re
    from openpyxl import load_workbook
    
    file_path = os.path.join(OUTPUT_DIR, update.filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {update.filename}")
    
    # URL 추출 헬퍼 함수
    def extract_urls_from_message(message: str) -> list:
        """메시지에서 URL 추출 (short URL 제외)"""
        url_pattern = r'(?:https?://|www\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        urls = re.findall(url_pattern, message)
        
        # Short URL 도메인 목록
        shortener_domains = [
            "bit.ly", "goo.gl", "tinyurl.com", "ow.ly", "t.co", 
            "is.gd", "buff.ly", "adf.ly", "bit.do", "mcaf.ee", 
            "me2.do", "naver.me", "kakaolink.com", "buly.kr", 
            "vo.la", "url.kr", "zrr.kr", "yun.kr", "han.gl",
            "shorter.me", "shrl.me"
        ]
        
        result = []
        for url in urls:
            url = url.rstrip('.,;!?)]}"\'')
            clean_url = re.sub(r'^https?://', '', url.lower())
            clean_url = re.sub(r'^www\.', '', clean_url)
            
            is_short = any(clean_url.startswith(domain) for domain in shortener_domains)
            if not is_short and url:
                result.append(url)
        return result
    
    def _lenb(text: str) -> int:
        """CP949 바이트 길이 계산"""
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        try:
            return len(text.encode('cp949'))
        except UnicodeEncodeError:
            return len(text.encode('utf-8'))
    
    try:
        wb = load_workbook(file_path)
        ws = wb.active
        
        # 헤더 찾기
        headers = [cell.value for cell in ws[1]]
        
        def get_col_idx(name):
            try:
                return headers.index(name) + 1
            except ValueError:
                return None
        
        msg_col = get_col_idx("메시지")
        gubun_col = get_col_idx("구분")
        code_col = get_col_idx("분류")
        prob_col = get_col_idx("Probability")
        reason_col = get_col_idx("Reason")
        
        if not msg_col:
            raise HTTPException(status_code=400, detail="'메시지' column not found in Excel")
        
        # 메시지로 행 찾기 + 현재 상태 저장
        found_row = None
        was_spam = False
        old_code = ""
        
        for row_idx in range(2, ws.max_row + 1):
            cell_value = ws.cell(row=row_idx, column=msg_col).value
            if cell_value and str(cell_value).strip() == update.message.strip():
                found_row = row_idx
                # 현재 상태 저장
                if gubun_col:
                    gubun_val = ws.cell(row=row_idx, column=gubun_col).value
                    was_spam = (gubun_val == "o")
                if code_col:
                    old_code = str(ws.cell(row=row_idx, column=code_col).value or "")
                break
        
        if not found_row:
            raise HTTPException(status_code=404, detail="Message not found in Excel")
        
        # 새 코드 값 계산
        if update.is_spam:
            match = re.search(r'\d+', str(update.classification_code))
            new_code = match.group(0) if match else update.classification_code
        else:
            new_code = ""
        
        # ========== 메인 시트 업데이트 ==========
        if gubun_col:
            ws.cell(row=found_row, column=gubun_col, value="o" if update.is_spam else "")
        
        if code_col:
            ws.cell(row=found_row, column=code_col, value=new_code)
        
        if prob_col:
            prob_val = f"{int(update.spam_probability * 100)}%"
            ws.cell(row=found_row, column=prob_col, value=prob_val)
        
        if reason_col:
            ws.cell(row=found_row, column=reason_col, value=update.reason)
        
        # ========== 메시지 셀 채우기 색 업데이트 ==========
        from openpyxl.styles import PatternFill, Alignment
        spam_fill = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")
        no_fill = PatternFill(fill_type=None)
        wrap_vcenter_align = Alignment(wrap_text=True, vertical='center')
        
        if msg_col:
            cell = ws.cell(row=found_row, column=msg_col)
            if not was_spam and update.is_spam:
                # HAM → SPAM: 황금색 채우기 적용
                cell.fill = spam_fill
                cell.alignment = wrap_vcenter_align
            elif was_spam and not update.is_spam:
                # SPAM → HAM: 채우기 제거
                cell.fill = no_fill
                cell.alignment = wrap_vcenter_align
        
        # ========== URL중복제거 시트 동기화 ==========
        urls_in_message = extract_urls_from_message(update.message)
        url_sheet_name = "URL중복 제거"
        
        if url_sheet_name in wb.sheetnames and urls_in_message:
            url_ws = wb[url_sheet_name]
            
            if was_spam and not update.is_spam:
                # SPAM → HAM: URL 삭제 (다른 SPAM이 사용하지 않는 경우만)
                # 먼저 다른 SPAM 메시지들의 URL 수집
                other_spam_urls = set()
                for row_idx in range(2, ws.max_row + 1):
                    if row_idx == found_row:
                        continue
                    gubun_val = ws.cell(row=row_idx, column=gubun_col).value if gubun_col else None
                    if gubun_val == "o":  # 다른 SPAM 메시지
                        other_msg = ws.cell(row=row_idx, column=msg_col).value
                        if other_msg:
                            other_spam_urls.update(extract_urls_from_message(str(other_msg)))
                
                # URL 시트에서 삭제할 행 찾기 (역순으로 삭제)
                rows_to_delete = []
                for url_row in range(2, url_ws.max_row + 1):
                    url_val = url_ws.cell(row=url_row, column=1).value  # URL(중복제거) 컬럼
                    if url_val and url_val in urls_in_message and url_val not in other_spam_urls:
                        rows_to_delete.append(url_row)
                
                for row in sorted(rows_to_delete, reverse=True):
                    url_ws.delete_rows(row)
                    
            elif not was_spam and update.is_spam:
                # HAM → SPAM: URL 추가
                existing_urls = set()
                for url_row in range(2, url_ws.max_row + 1):
                    url_val = url_ws.cell(row=url_row, column=1).value
                    if url_val:
                        existing_urls.add(url_val)
                
                for url in urls_in_message:
                    if url not in existing_urls:
                        url_ws.append([url, _lenb(url), new_code])
                        
            elif was_spam and update.is_spam and old_code != new_code:
                # SPAM 코드 변경: 분류 컬럼 업데이트
                for url_row in range(2, url_ws.max_row + 1):
                    url_val = url_ws.cell(row=url_row, column=1).value
                    if url_val and url_val in urls_in_message:
                        url_ws.cell(row=url_row, column=3, value=new_code)  # 분류 컬럼
        
        # ========== 문자문장차단등록 시트 동기화 ==========
        blocklist_sheet_name = "문자문장차단등록"
        clean_msg = re.sub(r'[ \t\r\n\f\v]+', '', update.message)  # 공백 제거된 메시지
        
        if blocklist_sheet_name in wb.sheetnames:
            bl_ws = wb[blocklist_sheet_name]
            
            if was_spam and not update.is_spam:
                # SPAM → HAM: 블록리스트에서 삭제
                rows_to_delete = []
                for bl_row in range(2, bl_ws.max_row + 1):
                    bl_msg = bl_ws.cell(row=bl_row, column=1).value  # 메시지 컬럼
                    if bl_msg and str(bl_msg).strip() == clean_msg.strip():
                        rows_to_delete.append(bl_row)
                
                for row in sorted(rows_to_delete, reverse=True):
                    bl_ws.delete_rows(row)
                    
            elif was_spam and update.is_spam and old_code != new_code:
                # SPAM 코드 변경: 분류 컬럼 업데이트
                for bl_row in range(2, bl_ws.max_row + 1):
                    bl_msg = bl_ws.cell(row=bl_row, column=1).value
                    if bl_msg and str(bl_msg).strip() == clean_msg.strip():
                        bl_ws.cell(row=bl_row, column=4, value=new_code)  # 분류 컬럼
            
            # HAM → SPAM: 블록리스트 추가 불가 (ibse_signature 없음)
        
        # 저장
        wb.save(file_path)
        
        # 동기화 결과 로깅
        sync_info = []
        if was_spam != update.is_spam:
            sync_info.append(f"{'SPAM→HAM' if was_spam else 'HAM→SPAM'}")
        if was_spam and update.is_spam and old_code != new_code:
            sync_info.append(f"Code: {old_code}→{new_code}")
        
        return {
            "success": True,
            "message": f"Row {found_row} updated successfully",
            "row": found_row,
            "sync": sync_info if sync_info else None,
            "urls_affected": len(urls_in_message) if urls_in_message else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating Excel row: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    
    if os.path.exists(file_path):
        from urllib.parse import quote
        # Encode all special characters including parentheses
        encoded_filename = quote(filename, safe='')
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
        return FileResponse(file_path, filename=None, headers=headers)
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    # Use generic run config; reload might still be tricky in script but let's try without reload first or with simple config
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
