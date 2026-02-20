from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Form, BackgroundTasks, Body
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil
import os
import asyncio
import sys
import logging
import warnings
import json
import time
import re
import unicodedata

# **CRITICAL**: 다른 앱 모듈 import 전에 로깅 설정 먼저 초기화
from dotenv import load_dotenv, set_key
load_dotenv(override=True)  # .env 파일 로드

from app.core.logging_config import setup_logging, get_logger, batch_id_context, set_log_level, set_console_enabled
from app.core.models import LLM_MODELS, CONFIG_METADATA

# 로깅 시스템 초기화 (앱 모듈 import 전에 반드시 호출!)
# 환경변수: LOG_LEVEL_CONSOLE, LOG_LEVEL_FILE, LOG_JSON_ENABLED
setup_logging()

logger = get_logger(__name__)

# Suppress noisy warnings and verbose SDK logs
warnings.filterwarnings("ignore")
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google.generativeai").setLevel(logging.WARNING)

# **CRITICAL FIX**: Force ProactorEventLoop on Windows for Playwright/Subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uuid
from typing import List, Dict, Any

# 이제 앱 모듈들을 import (로깅 설정 완료 후)
from app.services.rule_service import RuleBasedFilter
from app.agents.content_agent.agent import ContentAnalysisAgent
from app.agents.url_agent.agent import UrlAnalysisAgent
from app.utils.excel_handler import ExcelHandler
from app.core.constants import SPAM_CODE_MAP

# Custom Exception for Cancellation
class CancellationException(Exception):
    """처리 취소 예외"""
    pass

app = FastAPI()


# Global Executor to prevent Thread Leak
global_executor = None

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        # Map client_id to WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        # Map client_id to list of buffered messages (offline queue)
        self.message_queue: Dict[str, List[dict]] = {}
        # Cancellation flags for processing
        self.cancellation_flags: Dict[str, bool] = {}
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
    
    # Cancellation Methods
    def request_cancellation(self, client_id: str):
        """클라이언트의 처리 취소 요청"""
        self.cancellation_flags[client_id] = True
        logger.info(f"Cancellation requested for client {client_id}")
    
    def is_cancelled(self, client_id: str) -> bool:
        """취소 요청 확인"""
        return self.cancellation_flags.get(client_id, False)
    
    def clear_cancellation(self, client_id: str):
        """취소 플래그 초기화"""
        self.cancellation_flags.pop(client_id, None)

manager = ConnectionManager()


def _log_env_config():
    """서버 기동 시 .env 설정값 출력 (API 키 제외)"""
    # 민감 정보 패턴 - 이 키들은 값 출력 생략
    SENSITIVE_PATTERNS = ("KEY", "SECRET", "PASSWORD", "TOKEN")
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        lines = []
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"\'')
                    # 민감 키 스킵
                    key_upper = key.upper()
                    if any(p in key_upper for p in SENSITIVE_PATTERNS):
                        lines.append(f"  {key}=***")
                    else:
                        lines.append(f"  {key}={val}")
        if lines:
            logger.info("📋 [Config] .env loaded:\n" + "\n".join(lines))
    except Exception as e:
        logger.warning(f"Could not read .env for config log: {e}")


@app.on_event("startup")
async def startup_event():
    # [Config] .env 값 출력 (API 키 제외)
    _log_env_config()

    # [Performance Fix] Initialize Global ThreadPoolExecutor ONCE
    # Preventing thread leak (4320 threads issue)
    global global_executor
    workers = int(os.getenv("MAX_THREAD_WORKERS", 70))
    from concurrent.futures import ThreadPoolExecutor
    global_executor = ThreadPoolExecutor(max_workers=workers)
    
    # Set as default for the main loop
    loop = asyncio.get_event_loop()
    loop.set_default_executor(global_executor)

    # [Performance Optimization] Warm-up Heavy Components
    # Eliminate 30s+ delay on first request by initializing resources here
    logger.info("🔥 [Startup] Warming up AI Components (Vector DB & LLM)...")
    import time
    t0 = time.time()
    
    try:
        # 1. Warm-up SpamRagService (loads Chroma, OpenAIEmbeddings)
        from app.services.spam_rag_service import get_spam_rag_service
        rag_service = get_spam_rag_service()
        # Force initialization of lazy properties
        _ = rag_service._get_db() 
        logger.info(f"   -> SpamRagService Warmed up.")

        # 2. Warm-up ContentAnalysisAgent (loads Guide Chroma)
        from app.agents.content_agent.agent import ContentAnalysisAgent
        content_agent = ContentAnalysisAgent()
        # Force initialization
        _ = content_agent._get_vector_db() 
        logger.info(f"   -> ContentAnalysisAgent Warmed up.")
        
    except Exception as e:
        logger.warning(f"⚠️ [Startup] Warm-up failed (non-critical): {e}")

    logger.info(f"✅ Server Application Started! (Startup took {time.time() - t0:.2f}s) | Global ThreadPool: {workers} workers.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Server shutting down...")
    global global_executor
    if global_executor:
        global_executor.shutdown(wait=False)
        logger.info("Global ThreadPoolExecutor shutdown.")

@app.get("/health")
async def health_check():
    logger.info("✅ Health Check Endpoint Reached!")
    return {"status": "ok"}

# ========== 로그 레벨 런타임 변경 API ==========
from app.core.logging_config import get_log_levels, set_log_level, set_console_enabled

@app.get("/api/log-level")
async def get_current_log_level():
    """현재 로그 레벨 조회"""
    return get_log_levels()

class LogLevelChange(BaseModel):
    target: str  # "console" 또는 "file"
    level: str   # "DEBUG", "INFO", "WARNING", "ERROR"

class ConsoleToggle(BaseModel):
    enabled: bool  # True=ON, False=OFF

@app.post("/api/log-level")
async def change_log_level(request: LogLevelChange):
    """런타임에 로그 레벨 변경 (서버 재시작 없이)"""
    result = set_log_level(request.target, request.level)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@app.post("/api/log-console")
async def toggle_console_log(request: ConsoleToggle):
    """콘솔 로그 출력 ON/OFF"""
    return set_console_enabled(request.enabled)

# ========== 런타임 환경설정 관리 API ==========

@app.get("/api/models")
async def get_supported_models():
    """지원하는 LLM 모델 리스트 조회"""
    return LLM_MODELS

@app.get("/api/config")
async def get_current_config():
    """현재 시스템 설정값 조회 (마스킹 처리)"""
    config_values = {}
    SENSITIVE_KEYS = ["KEY", "SECRET", "PASSWORD", "TOKEN"]
    
    for item in CONFIG_METADATA:
        key = item["key"]
        val = os.getenv(key, "")
        
        # 민감 정보 마스킹
        if any(sk in key.upper() for sk in SENSITIVE_KEYS) and val:
            config_values[key] = "***"
        else:
            config_values[key] = val
            
    return {
        "metadata": CONFIG_METADATA,
        "values": config_values
    }

class ConfigUpdate(BaseModel):
    settings: Dict[str, Any]

@app.post("/api/config")
async def update_config(request: ConfigUpdate):
    """런타임에 설정값 변경 및 .env 저장"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    updated_keys = []
    
    try:
        for key, value in request.settings.items():
            # 1. 메모리(os.environ) 업데이트
            str_val = str(value)
            os.environ[key] = str_val
            
            # 2. .env 파일 영구 저장 (민감정보 제외 - 민감정보는 별도 처리 권장되나 여기서는 일단 저장 지원)
            # 유효성 검증 로직 추가 가능
            set_key(env_path, key, str_val)
            updated_keys.append(key)
            
        logger.info(f"⚙️ [Config] Updated keys: {', '.join(updated_keys)}")
        
        # 3. 로그 레벨 관련 설정 즉시 반영
        from app.core.logging_config import set_log_level, set_console_enabled
        if "LOG_LEVEL_CONSOLE" in updated_keys:
            set_log_level("console", os.environ["LOG_LEVEL_CONSOLE"])
        if "LOG_LEVEL_FILE" in updated_keys:
            set_log_level("file", os.environ["LOG_LEVEL_FILE"])
        if "LOG_CONSOLE_ENABLED" in updated_keys:
            set_console_enabled(os.environ["LOG_CONSOLE_ENABLED"] == "1")
        
        # 4. 필터 임계값 관련 설정 즉시 반영
        if "MIN_MESSAGE_LENGTH" in updated_keys or "ALPHANUMERIC_OBFUSCATION_RATIO_THRESHOLD" in updated_keys:
            rule_filter.update_thresholds()
        
        # 5. 변경 사항 즉시 로그 출력 (마스킹 적용)
        _log_env_config()
        
        return {"success": True, "updated": updated_keys}
    except Exception as e:
        logger.error(f"Config update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/quota-status")
async def get_quota_status():
    """LLM 공급자별 Quota Exhausted 상태 조회 (설정 UI용)"""
    from app.core.llm_manager import key_manager
    return {"success": True, "quota_status": key_manager.get_quota_status()}


class ResetQuotaRequest(BaseModel):
    provider: str | None = None  # None이면 전체 리셋


@app.post("/api/config/reset-quota")
async def reset_quota(request: ResetQuotaRequest | None = Body(default=None)):
    """Quota Exhausted 플래그 수동 리셋 (설정 UI 버튼용)"""
    from app.core.llm_manager import key_manager
    provider = request.provider if request else None
    result = key_manager.reset_quota_exhausted(provider)
    return {"success": True, **result}


# ========== Spam RAG API (Reference Examples) ==========
from app.services.spam_rag_service import get_spam_rag_service

class SpamRagCreate(BaseModel):
    message: str
    label: str = "SPAM"
    code: str
    category: str
    reason: str

class SpamRagUpdate(BaseModel):
    message: str = None
    label: str = None
    code: str = None
    category: str = None
    reason: str = None

@app.get("/api/spam-rag")
async def get_spam_rag_examples():
    """참조 예시 전체 조회"""
    try:
        service = get_spam_rag_service()
        examples = service.get_all_examples()
        return {"success": True, "data": examples, "total": len(examples)}
    except Exception as e:
        logger.error(f"Spam RAG GET Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spam-rag/stats")
async def get_spam_rag_stats():
    """참조 예시 통계 조회"""
    try:
        service = get_spam_rag_service()
        stats = service.get_stats()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"Spam RAG Stats Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spam-rag/search")
async def search_spam_rag_examples(query: str, k: int = 3):
    """유사 참조 예시 검색 (Intent-based, Threshold-filtered)"""
    try:
        # 1. Generate Intent Summary for the query (to align with stored vectors)
        from app.agents.content_agent.agent import ContentAnalysisAgent
        agent = ContentAnalysisAgent()
        intent_summary = await agent.agenerate_intent_summary(query)
        
        logger.info(f"RAG Search Query: '{query}' -> Intent: '{intent_summary}'")

        # 2. Search using the Intent Summary
        service = get_spam_rag_service()
        results = service.search_similar(intent_summary, k=k)
        
        # 3. Filter by RAG_DISTANCE_THRESHOLD (align with LLM prompt injection logic)
        distance_threshold = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.35"))
        hits = results.get("hits", [])
        filtered_hits = [
            hit for hit in hits 
            if hit.get("distance", 999) <= distance_threshold
        ]
        
        logger.info(f"RAG Search: {len(hits)} raw results, {len(filtered_hits)} within threshold ({distance_threshold})")
        
        return {
            "success": True, 
            "data": {"hits": filtered_hits, "stats": results.get("stats", {})}, 
            "total": len(filtered_hits)
        }
    except Exception as e:
        logger.error(f"Spam RAG Search Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spam-rag/{example_id}")
async def get_spam_rag_example(example_id: str):
    """특정 참조 예시 조회"""
    try:
        service = get_spam_rag_service()
        example = service.get_example_by_id(example_id)
        if not example:
            raise HTTPException(status_code=404, detail="Example not found")
        return {"success": True, "data": example}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spam RAG GET Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/spam-rag")
async def create_spam_rag_example(example: SpamRagCreate):
    """
    Spam RAG: 새로운 참조 예시 추가 (Intent-based)
    1. ContentAnalysisAgent를 통해 의도 요약 생성
    2. Intent Summary를 임베딩 저장, 원본은 메타데이터 저장
    """
    try:
        # 1. Generate Intent Summary
        # Import inside to ensure availability or avoid circular deps if any (though unlikely here)
        from app.agents.content_agent.agent import ContentAnalysisAgent
        agent = ContentAnalysisAgent()
        intent_summary = await agent.agenerate_intent_summary(example.message)
        logger.info(f"Generated Intent Summary for RAG: '{intent_summary}' (Original: {example.message[:20]}...)")

        # 2. Save to RAG (Intent Summary based)
        service = get_spam_rag_service()
        result = service.add_example(
            intent_summary=intent_summary,  # Embedding Target
            original_message=example.message, # Metadata
            label=example.label,
            code=example.code,
            category=example.category,
            reason=example.reason
        )
        logger.info(f"Spam RAG Example Created: {result['id']}")
        return {"success": True, "data": result}
    except ValueError as e:
        # 중복 에러 처리 (409 Conflict)
        logger.warning(f"Spam RAG Create Conflict: {e}")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Spam RAG Create Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/spam-rag/{example_id}")
async def update_spam_rag_example(example_id: str, example: SpamRagUpdate):
    """참조 예시 수정"""
    try:
        service = get_spam_rag_service()
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
        logger.info(f"Spam RAG Example Updated: {example_id}")
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spam RAG Update Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/spam-rag/{example_id}")
async def delete_spam_rag_example(example_id: str):
    """참조 예시 삭제"""
    try:
        service = get_spam_rag_service()
        success = service.delete_example(example_id)
        if not success:
            raise HTTPException(status_code=404, detail="Example not found or delete failed")
        logger.info(f"Spam RAG Example Deleted: {example_id}")
        return {"success": True, "message": "Deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spam RAG Delete Error: {e}")
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
REPORTS_DIR = "../data/reports"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ========== Report Management API ==========
class ReportSaveRequest(BaseModel):
    report_name: str
    source_filename: str
    logs: List[dict]

@app.post("/api/reports/save")
async def save_report(request: ReportSaveRequest):
    """현재 로그를 리포트 파일로 저장"""
    import json
    from datetime import datetime
    try:
        timestamp = datetime.now().isoformat()
        report_data = {
            "report_name": request.report_name,
            "source_filename": request.source_filename,
            "timestamp": timestamp,
            "logs": request.logs
        }
        
        # 파일명 생성: report_name_timestamp.json
        safe_name = "".join([c for c in request.report_name if c.isalnum() or c in (' ', '_', '-')]).strip()
        if not safe_name: safe_name = "report"
        filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(REPORTS_DIR, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Report saved: {filename}")
        return {"success": True, "filename": filename}
    except Exception as e:
        logger.error(f"Report Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reports")
async def list_reports():
    """저장된 리포트 목록 조회"""
    try:
        if not os.path.exists(REPORTS_DIR):
            return {"success": True, "reports": []}
        files = [f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")]
        reports = []
        for f in files:
             filepath = os.path.join(REPORTS_DIR, f)
             reports.append({
                 "filename": f,
                 "mtime": os.path.getmtime(filepath)
             })
        # 최신 수정순 정렬
        reports.sort(key=lambda x: x["mtime"], reverse=True)
        return {"success": True, "reports": reports}
    except Exception as e:
        logger.error(f"List Reports Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/reports/{filename}")
async def get_report(filename: str):
    """특정 리포트 내용 로드"""
    import json
    try:
        filepath = os.path.join(REPORTS_DIR, filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Report not found")
            
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get Report Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
            "output_tokens": 0,
            "exclude_from_excel": s1_result.get("exclude_from_excel", False)
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
    # url_pattern = re.compile(r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})')
    url_pattern = re.compile(r'(?:https?://|www\.)\S+|[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.[a-zA-Z가-힣]{2,}')
    
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
        
        if is_inconclusive or url_is_spam is None:
             # URL 심층 분석 불가 (404, 내용 없음, 오류 등) -> 본문 분석 결과(Content Agent)를 전적으로 따름
             logger.info("    -> URL Analysis Inconclusive/Error. Falling back to Content Agent verdict.")
             final_reason += f" | [URL: Inaccessible/Empty - Using Content Verdict]"
        elif url_is_spam:
             # 1차: 실질적 유해성(Harmful Intent) 여부 확인
             url_reason = isaa_result.get("reason", "").lower()
             url_code = isaa_result.get('classification_code')
             
             # 단순 문맥 불일치(Inconsistency)나 사칭(Impersonation)만으로는 HAM을 SPAM으로 뒤집지 않음.
             # 실질적 유해성(도박, 성인, 불법, 사기 등)이 언급되거나 관련 코드가 있는 경우에만 SPAM 전환.
             harm_keywords = ["gambling", "adult", "phishing", "malicious", "fraud", "scam", "illegal", "유해", "도박", "성인", "피싱", "사기"]
             has_harmful_intent = any(k in url_reason for k in harm_keywords) or (url_code and str(url_code) != "0")
             
             if not final_is_spam and not has_harmful_intent:
                  # 본문은 HAM인데 URL은 단순 불일치/낚시성인 경우 -> HAM 유지 (의도 중심)
                  logger.info("    -> URL shows inconsistency but no harmful intent. Maintaining HAM.")
                  final_reason += " | [URL: Inconsistent but no clear harm (HAM maintained)]"
             else:
                  # 실제 유해성이 확인되었거나 본문이 이미 SPAM인 경우 -> SPAM 확정
                  logger.info("    -> Suspicious URL with Harmful Intent Confirmed! Finalizing as SPAM.")
                  final_is_spam = True
                  final_reason += f" | [URL: DETECTED SPAM]"
                  
                  # 확률 업데이트
                  url_prob = isaa_result.get("spam_probability", 0.95)
                  if url_prob > final_prob:
                      final_prob = url_prob
                  
                  # 코드 업데이트 (본문이 HAM이었거나 코드가 없으면 URL 코드 사용, 기본값 '0')
                  if url_code and str(url_code) != "0":
                       final_code = url_code
                  elif not final_code or str(final_code).startswith("HAM"):
                       final_code = "0" 
                  
                  logger.info(f"[URL Override] Final Verdict: SPAM, Code: {final_code}")
        else:
             # Confirmed Safe -> Force HAM (Override Content SPAM if confirmed as safe institution/service)
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
                    
                    logger.info(f"\n{'='*60}\n[Chat] Mode: {mode}\n[Chat] 메시지 원문:\n  {user_msg}\n{'='*60}")
                    
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
                            # url_pattern = re.compile(r'(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})')
                            url_pattern = re.compile(r'(?:https?://|www\.)\S+|[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.[a-zA-Z가-힣]{2,}')
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
                                is_inconclusive = any(x in reason_lower for x in ["error", "inconclusive", "insufficient", "image only", "no url found", "no url extracted", "no url to scrape"]) or url_is_spam is None
                                
                                if is_inconclusive:
                                     # URL 심층 분석 불가 -> 본문 결과(Content Agent) 폴백 지지
                                     await send_text_chunk("\nℹ️ **URL 분석 불가**: 링크가 만료되었거나 접근할 수 없습니다. 문자 본문 분석 결과를 우선하여 판정합니다.\n")
                                     pass 
                                elif url_is_spam:
                                     # Case 4: Content(HAM) -> URL(SPAM) : SPAM Confirmed conditionally
                                     # 실질적 유해성(Harmful Intent) 여부 확인
                                     url_reason = isaa_result.get("reason", "").lower()
                                     url_code = isaa_result.get('classification_code')
                                     
                                     harm_keywords = ["gambling", "adult", "phishing", "malicious", "fraud", "scam", "illegal", "유해", "도박", "성인", "피싱", "사기"]
                                     has_harmful_intent = any(k in url_reason for k in harm_keywords) or (url_code and str(url_code) != "0")

                                     if not final_is_spam and not has_harmful_intent:
                                          # 본문 HAM인데 URL은 단순 불일치 -> HAM 유지 (의도 중심)
                                          await send_text_chunk("\nℹ️ **의도 중심 판정**: 본문과 URL의 문맥이 다르나, 페이지에서 명확한 피해 의도가 확인되지 않아 **정상(HAM)**으로 처리합니다.\n")
                                     else:
                                          # 실제 유해성이 확인되었거나 본문이 이미 SPAM인 경우 -> SPAM 확정
                                          final_is_spam = True
                                          
                                          # Update Probability
                                          url_prob = isaa_result.get("spam_probability", 0.95)
                                          if url_prob > prob:
                                              prob = url_prob
                                          
                                          # Update Reason
                                          url_reason_text = isaa_result.get("reason", "Malicious URL detected")
                                          content_reason += f" | [URL SPAM: {url_reason_text}]"

                                          # URL Agent의 classification_code로 업데이트 (URL 분석이 Ground Truth)
                                          original_code = code
                                          
                                          # URL 코드가 존재하고 '0'(기타)이 아니면 업데이트. 
                                          # 그렇지 않더라도 기존 코드가 HAM 계열이면 일반 스팸 코드('0')로 전환하여 불일치 방지
                                          if url_code and str(url_code) != "0":
                                               code = url_code
                                          elif str(original_code).startswith("HAM") or not original_code:
                                               code = "0" # Default SPAM code
                                               
                                          logger.info(f"[URL Override] Updated code from '{original_code}' to '{code}' based on URL analysis")
                                          # 코드 변경 알림 출력
                                          new_code_desc = code_map.get(str(code), "기타")
                                          await send_text_chunk(f"\n⚠️ **스팸 확정**: {original_code} → **{code}. {new_code_desc}** (유해 URL 탐지)\n")
                                elif isaa_result: # result가 있을 때만 처리 (Case 2: Content(SPAM) -> URL(Safe))
                                     # Case 2: Content(SPAM) -> URL(Safe) : HAM Confirmed
                                     if final_is_spam:
                                          final_is_spam = False
                                          code = None  # HAM으로 바뀌면 코드도 초기화
                                          content_reason += " | [URL: Confirmed Safe (Override)]" # Update display reason
                                          await send_text_chunk("\n✅ **정상 확인**: URL 분석 결과 안전한 기관/서비스로 확인되어 정상으로 판정합니다.\n")

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

@app.post("/cancel/{client_id}")
async def cancel_processing(client_id: str):
    """파일 처리 취소 요청"""
    manager.request_cancellation(client_id)
       
    logger.info(f"Cancellation requested for client {client_id}")
    return {"message": f"Cancellation requested for {client_id}"}


    ws.cell(row=excel_row, column=output_columns["Reason"]).value = sanitize(reason)

# ==========================================
# [Helper] URL Detection for Smart Concurrency
# ==========================================
def has_potential_url(message: str) -> bool:
    """
    메시지에 URL이 포함되어 있는지 확인 (난독화된 URL 포함)
    Smart Concurrency: URL이 있으면 Browser Queue(Slow), 없으면 LLM Queue(Fast)로 배정하기 위한 판단
    """
    if not message:
        return False
        
    # nodes.py와 동일한 강력한 정규식 (http(s) 옵션 + 도메인 패턴)
    # 한글, 영문, 숫자, 특수문자 도메인 지원
    url_pattern = r'(?:http[s]?://)?(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z가-힣]{2,}'
    
    # 1. 원본 텍스트 검사
    if re.search(url_pattern, message):
        return True
        
    # 2. 난독화 해제 후 검사 (NFKC 정규화)
    # 예: "lⓔtⓩ.kr" -> "letz.kr"
    try:
        normalized = unicodedata.normalize('NFKC', message)
        if normalized != message:
            if re.search(url_pattern, normalized):
                # logger.debug(f"De-obfuscated URL detected: {message} -> {normalized}")
                return True
    except:
        pass
        
    return False

@app.post("/upload")
async def upload_file(client_id: str = Form(...), file: UploadFile = File(...)):
    logger.info(f"DEBUG: Receive file upload request from Client {client_id}: {file.filename}")
    
    # [Safe Cleanup] Zombie process killing via 'taskkill' removed.
    # New architecture uses localized PlaywrightManager with auto-cleanup (finally block).
    # This prevents accidental termination of user's local Chrome browser.
    # loop = asyncio.get_running_loop()
    # await loop.run_in_executor(None, kill_zombie_processes)

    try:
        # Clear any previous cancellation flags
        manager.clear_cancellation(client_id)
        
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
        def process_message_with_hitl(messages: list, start_index: int = 0, total_count: int = 0) -> list:
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
                    s1_results.append({"is_spam": False, "detected_pattern": "Empty", "exclude_from_excel": True})
                else:
                    s1_results.append(rule_filter.check(msg))
            
            # Async Batch Orchestrator
            async def run_batch_pipeline():
                # [Performance Fix] Use Global ThreadPoolExecutor
                # We do NOT create a new executor here.
                # loop.set_default_executor is NOT called. 
                # The global executor (size=70) handles all blocking I/O.
                try:

                    
                    # [JIT Optimization] Global pre-processing removed to eliminate startup delay.
                    # Context will be prepared individually within process_single_item.

                    # A. Define Single Item Processing Function (Wraps Content + URL Logic per item)
                    from app.graphs.batch_flow import create_batch_graph
                    from app.agents.url_agent.tools import PlaywrightManager
                    
                    # [Infrastructure] Create Local PlaywrightManager for this batch to ensure isolation
                    # This fixes race conditions where global manager was closed by other threads.
                    local_manager = PlaywrightManager() 

                    # Use global agents (Thread-safe/Async-safe assumed)
                    batch_graph = create_batch_graph(rag_filter, url_filter, ibse_service, playwright_manager=local_manager)

                    async def process_single_item(index, message, s1_res):
                        import time
                        start_time = time.time() # [Time Tracking] Start

                        # Set Batch ID for this context (automatically prefixes all logs in this task)
                        batch_id_context.set(f"Batch {index+1}")
                        
                        # Construct context Just-In-Time (JIT)
                        try:
                            # Use list wrap [message] to reuse batch logic for single item
                            jit_contexts = await rag_filter.prepare_batch_contexts([message])
                            context_data = jit_contexts[0] if jit_contexts else None
                        except Exception as e:
                            logger.error(f"Context Prep Error: {e}")
                            context_data = None

                        # 배치 Item 시작 로그
                        logger.info(f"분석 시작 | msg={message[:80]}{'...' if len(message) > 80 else ''}")
                        
                        # Rule-based HAM (e.g., Non-Korean message) - Skip Graph
                        if s1_res.get("is_spam") is False:
                            s1_code = s1_res.get("classification_code")
                            s1_reason = s1_res.get("reason", "Rule-based HAM")
                            logger.info(f"Rule-based HAM | code={s1_code}")
                            duration = round(time.time() - start_time, 2)
                            return index, {
                                "is_spam": False,
                                "classification_code": s1_code,
                                "spam_probability": 0.0,
                                "reason": s1_reason,
                                "duration_seconds": duration,
                                "exclude_from_excel": s1_res.get("exclude_from_excel", False)
                            }
                        
                        # Construct Input State
                        input_state = {
                            "message": message,
                            "s1_result": s1_res,
                            "prefetched_context": context_data, # [Batch Optimization] Inject Context
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
                            verdict = "SPAM" if final_is_spam else ("HITL" if final_is_spam is None else "HAM")
                            
                            duration = round(time.time() - start_time, 2)
                            logger.info(f"완료 | {verdict} | code={final_code} | prob={final_prob} | {duration}s")
                            
                            # [User Request] Generate Final Summary for Logging (Batch Mode)
                            # graph output contains content/url results needed for summary
                            content_res = graph_output.get("content_result")
                            url_res = graph_output.get("url_result")
                            
                            if content_res:
                                # We fire and forget (audit log) - ensuring it logs to console
                                try:
                                    await rag_filter.generate_final_summary(message, content_res, url_res)
                                except Exception as ex:
                                    logger.warning(f"Batch Summary Gen Error: {ex}")
                            
                            # Add duration to result
                            final_res["duration_seconds"] = duration
                            return index, final_res
                            
                        except Exception as e:
                            logger.error(f"Graph Execution Error: {e}")
                            duration = round(time.time() - start_time, 2)
                            return index, {"is_spam": None, "reason": f"Graph Error: {e}", "duration_seconds": duration}

                    # Create Two Priority Queues (Semaphores)
                    # 1. Browser Queue: For messages with URLs (High Resource) -> Limited by MAX_BROWSER_CONCURRENCY
                    # 2. LLM Queue: For text-only messages (Low Resource) -> Limited by LLM_BATCH_SIZE
                    
                    max_browser = int(os.getenv("MAX_BROWSER_CONCURRENCY", 10))
                    max_llm = int(os.getenv("LLM_BATCH_SIZE", 50))
                    
                    sem_browser = asyncio.Semaphore(max_browser)
                    sem_llm = asyncio.Semaphore(max_llm)
                    
                    logger.info(f"Initialized Dual Concurrency: Browser={max_browser}, LLM-Only={max_llm}")
                    
                    # Monotonic counter for progress
                    completed_count = 0
                    
                    async def sem_task(index, msg, s1):
                        # Set Batch ID for this context task
                        batch_id_context.set(f"Batch {index+1}")
                        if manager.is_cancelled(client_id):
                            logger.info(f"Cancelled before start.")
                            return index, {"is_spam": None, "reason": "Cancelled"}
                            
                        # Smart Concurrency: Check for URL (including obfuscated)
                        is_url_msg = has_potential_url(msg)
                        selected_sem = sem_browser if is_url_msg else sem_llm
                        queue_type = "Browser" if is_url_msg else "LLM-Only"
                        
                        # Terminology: 'Queued' means created and waiting for worker slot
                        logger.debug(f"Queued in {queue_type} Queue (Waiting for semaphore...)")
                        async with selected_sem:
                            if manager.is_cancelled(client_id):
                                logger.info(f"Cancelled after semaphore acquisition.")
                                return index, {"is_spam": None, "reason": "Cancelled"}
                                
                            logger.debug(f"Acquired {queue_type} semaphore. Starting process...")
                            idx, res = await process_single_item(index, msg, s1)
                            # [Real-time Streaming] Send result to client immediately
                            try:
                                nonlocal completed_count
                                completed_count += 1
                                
                                # [Optimization] Strip large binary/b64 data that frontend doesn't need
                                ws_res = res.copy()
                                if "screenshot_b64" in ws_res:
                                    del ws_res["screenshot_b64"]
                                
                                # [UI Fix] Use run_coroutine_threadsafe to send to main event loop
                                asyncio.run_coroutine_threadsafe(
                                    manager.send_personal_message({
                                        "type": "BATCH_PROCESS_UPDATE",
                                        "index": idx + start_index,  # Use Global Index for updating specific row
                                        "message": msg,
                                        "status": "done",
                                        "result": ws_res,
                                        "current": start_index + completed_count, # Monotonic progress
                                        "total": total_count # Total rows in file
                                    }, client_id), loop
                                )
                            except Exception as ws_ex:
                                logger.warning(f"WS Streaming Failed: {ws_ex}")
                            return idx, res

                    # Create all tasks (they will wait on semaphore)
                    tasks = [sem_task(i, messages[i], s1_results[i]) for i in range(len(messages))]
                    
                    # Run All and Wait (Still need to collect all for Excel save)
                    logger.info(f"Starting asyncio.gather for {len(tasks)} tasks...")
                    results_with_idx = await asyncio.gather(*tasks)
                    logger.info("asyncio.gather finished.")
                    
                    # Sort just in case (though gather guarantees order) and extract
                    # results_with_idx is list of (index, result)
                    sorted_results = sorted(results_with_idx, key=lambda x: x[0])
                    completed_results = [r[1] for r in sorted_results]
                        
                    return completed_results

                finally:
                    # Cleanup Playwright after batch loop finishes
                    try:
                        if local_manager:
                             await local_manager.stop()
                        logger.info("Local PlaywrightManager cleaned up.")
                    except Exception as cleanup_err:
                        logger.warning(f"Cleanup warning: {cleanup_err}")

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
                # User Request (2026-02-06): Non-blocking notification only. No waiting.
                # If prob >= 0.9, auto-confirm SPAM. Otherwise, mark as HAM (30) with [확인 필요].
                spam_prob = result.get("spam_probability", 0.0)
                
                if result.get("classification_code") == "30":
                    if spam_prob >= 0.9:
                        logger.info(f"[HITL Override] Probability {spam_prob} >= 0.9. Marking as SPAM-1 without user check.")
                        result["is_spam"] = True
                        result["classification_code"] = "1" # Default to General/Illegal Spam
                        result["reason"] += " [Auto-Confirmed due to High Probability]"
                    else:
                        logger.info(f"[HITL] Non-blocking Notification: {msg[:20]}...")
                    
                        # Notify Client (Visual Notification Only)
                        hitl_notification = {
                            "type": "HITL_NOTIFICATION", # Changed from REQUEST to NOTIFICATION
                            "message": msg,
                            "spam_probability": result.get("spam_probability"),
                            "reason": result.get("reason"),
                            "index": i + start_index # Global Index for Frontend Highlight
                        }
                        try:
                            # Send asynchronously without waiting for result blocking heavily
                            asyncio.run_coroutine_threadsafe(
                                manager.send_personal_message(hitl_notification, client_id), loop
                            )
                        except Exception as noti_err:
                            logger.warning(f"Failed to send HITL notification: {noti_err}")
                        
                        # ** Non-blocking Default Decision **
                        # Mark as HAM (is_spam=False) but keep Code 30 so user can review later.
                        result["is_spam"] = False
                        result["classification_code"] = "30" 
                        result["reason"] += " [판단 보류 - 확인 필요]"
                        logger.info("[HITL] Defaulted to HAM(30) (Non-blocking mode).")
                
                final_results.append(result)
                
            return final_results
 
        
        # Determine Batch Size
        batch_size_env = int(os.getenv("LLM_BATCH_SIZE", 10))
        
        if file_ext.lower() == '.txt':
            # Process TXT
            # [Optimization] Pass a large batch_chunk_size (e.g. 1000) to ExcelHandler
            # so it feeds many items to process_message_with_hitl at once.
            # Then process_message_with_hitl uses Semaphore(LLM_BATCH_SIZE) to throttle concurrency.
            # This enables "Sliding Window" instead of blocking after every 10 items.
            batch_chunk_size = 1000 
            
            result = await loop.run_in_executor(
                None, 
                lambda: excel_handler.process_kisa_txt(
                    input_path, OUTPUT_DIR, process_message_with_hitl, progress_callback, 
                    batch_size=batch_chunk_size, original_filename=file.filename,
                    manager=manager, client_id=client_id
                )
            )
            if isinstance(result, dict) and "filename" in result:
                output_filename = result["filename"]
        else:
            # Process Excel
            batch_chunk_size = 1000
            await loop.run_in_executor(
                None, 
                lambda: excel_handler.process_file(input_path, output_path, process_message_with_hitl, progress_callback, batch_size=batch_chunk_size)
            )
        
        return {"id": file_id, "filename": output_filename, "message": "Processing complete"}
    
    except CancellationException as e:
        logger.info(f"Processing cancelled: {e}")
        try:
            await manager.send_personal_message({
                "type": "cancellation_confirmed",
                "message": "처리가 중지되었습니다."
            }, client_id)
        except Exception as ws_error:
            logger.warning(f"Failed to send cancellation confirmation: {ws_error}")
            
        # Safe variable access
        safe_file_id = locals().get('file_id', 'unknown')
        safe_filename = locals().get('output_filename', None)
        
        return {
            "id": safe_file_id, 
            "filename": safe_filename,
            "message": "Processing cancelled by user",
            "status": "cancelled"
        }
        
    except Exception as e:
        logger.error(f"Error during upload/processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ExcelRowUpdate(BaseModel):
    """엑셀 행 업데이트 요청"""
    filename: str
    excel_row_number: int  # Required: Direct row number for update
    message: str  # For validation only
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
        
        # 행 번호로 직접 접근 + 검증
        found_row = update.excel_row_number
        
        # 검증 1: 행 번호 범위 확인
        if found_row < 2 or found_row > ws.max_row:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid row number: {found_row} (valid range: 2-{ws.max_row})"
            )
        
        # 검증 2: 메시지 일치 확인
        cell_value = ws.cell(row=found_row, column=msg_col).value
        if not cell_value or str(cell_value).strip() != update.message.strip():
            logger.warning(f"Row {found_row} mismatch. Verification failed. Expected: '{update.message[:30]}...', Found: '{str(cell_value)[:30] if cell_value else 'None'}...'")
            logger.info("Attempting to find the correct row by message content scan...")
            
            # [Smart Recovery] Scan entire file for ALL matches and pick the CLOSEST one
            candidates = []
            for r in range(2, ws.max_row + 1):
                r_msg = ws.cell(row=r, column=msg_col).value
                if r_msg and str(r_msg).strip() == update.message.strip():
                    candidates.append(r)
            
            if candidates:
                # Find the candidate row closest to the requested row (handling slight shifts/duplicates)
                best_match = min(candidates, key=lambda r: abs(r - found_row))
                dist = abs(best_match - found_row)
                
                # Safety Check: If deviation is too large, it might be a different instance (ambiguous)
                # But since content is identical, "closest" is the best logical guess for "the row the user clicked"
                logger.info(f"Recovered! Found {len(candidates)} matches. Closest is {best_match} (dist: {dist})")
                found_row = best_match
            else:
                # Still not found -> Fatal Error
                logger.error("Recovery failed. Message not found in any row.")
                raise HTTPException(
                    status_code=400,
                    detail=f"Row {found_row} message mismatch AND message not found in file. Expected: '{update.message[:50]}...', Found: '{str(cell_value)[:50] if cell_value else 'None'}...'"
                )
        
        logger.info(f"Updating Excel row {found_row}: {update.message[:50]}...")
        
        # 현재 상태 저장
        was_spam = False
        old_code = ""
        if gubun_col:
            gubun_val = ws.cell(row=found_row, column=gubun_col).value
            was_spam = (gubun_val == "o")
        if code_col:
            old_code = str(ws.cell(row=found_row, column=code_col).value or "")
        
        # 새 코드 값 계산
        if update.is_spam:
            match = re.search(r'\d+', str(update.classification_code))
            new_code = match.group(0) if match else update.classification_code
        else:
            new_code = ""
        
        # Helper for sanitization
        def sanitize(val):
            if isinstance(val, str) and val.startswith(('=', '+', '-', '@')):
                 return "'" + val
            return val

        # ========== 메인 시트 업데이트 ==========
        if gubun_col:
            ws.cell(row=found_row, column=gubun_col, value=sanitize("o" if update.is_spam else ""))
        
        if code_col:
            ws.cell(row=found_row, column=code_col, value=sanitize(new_code))
        
        if prob_col:
            prob_val = f"{int(update.spam_probability * 100)}%"
            ws.cell(row=found_row, column=prob_col, value=sanitize(prob_val))
        
        if reason_col:
            ws.cell(row=found_row, column=reason_col, value=sanitize(update.reason))
        
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
        
        # ========== SPAM↔HAM 변경 시 시트 재정렬 ==========
        if was_spam != update.is_spam and gubun_col:
            # 모든 데이터 행 읽기 (헤더 제외)
            data_rows = []
            for row_idx in range(2, ws.max_row + 1):
                row_data = []
                for col_idx in range(1, ws.max_column + 1):
                    row_data.append(ws.cell(row=row_idx, column=col_idx).value)
                data_rows.append(row_data)
            
            # 구분 컬럼 기준 정렬 (SPAM "o" 먼저, HAM "" 나중)
            def sort_key(row):
                gubun_val = row[gubun_col - 1] if len(row) >= gubun_col else ""
                return 0 if gubun_val == "o" else 1
            
            data_rows.sort(key=sort_key)
            
            # 정렬된 데이터로 다시 쓰기
            for i, row_data in enumerate(data_rows):
                row_idx = i + 2  # 헤더가 1행이므로 2행부터
                for col_idx, value in enumerate(row_data, start=1):
                    ws.cell(row=row_idx, column=col_idx, value=value)
            
            # 재정렬 후 서식 재적용 (채우기 색)
            for row_idx in range(2, ws.max_row + 1):
                gubun_val = ws.cell(row=row_idx, column=gubun_col).value
                if msg_col:
                    cell = ws.cell(row=row_idx, column=msg_col)
                    if gubun_val == "o":  # SPAM
                        cell.fill = spam_fill
                    else:  # HAM
                        cell.fill = no_fill
                    cell.alignment = wrap_vcenter_align
        
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
async def download_file(filename: str, suggested_name: str = None):
    file_path = os.path.join(OUTPUT_DIR, filename)
    
    if os.path.exists(file_path):
        from urllib.parse import quote
        # Use suggested_name if provided, otherwise use original filename
        download_name = suggested_name if suggested_name else filename
        # Ensure it has the correct extension if suggested_name forgot it
        if download_name and not download_name.lower().endswith('.xlsx') and filename.lower().endswith('.xlsx'):
             download_name += '.xlsx'
             
        encoded_filename = quote(download_name, safe='')
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
        return FileResponse(file_path, filename=None, headers=headers)
    raise HTTPException(status_code=404, detail="File not found")


if __name__ == "__main__":
    import uvicorn
    # Use generic run config; reload might still be tricky in script but let's try without reload first or with simple config
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
