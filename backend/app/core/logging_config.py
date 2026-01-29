"""
Spam Detector - 중앙 집중식 로깅 설정
====================================

Features:
1. TimedRotatingFileHandler: 매일 자정에 새 로그 파일 생성, 7일 보관
2. Multi-Handler: 콘솔(INFO) + 파일(DEBUG) 동시 출력
3. JSON 형식 로그 지원 (분석 도구 연동용)
4. 예외 시 Traceback 전체 기록

Usage:
    from app.core.logging_config import setup_logging, get_logger
    
    # 앱 시작 시 한 번 호출
    setup_logging()
    
    # 각 모듈에서 로거 가져오기
    logger = get_logger(__name__)
    logger.info("메시지 분석 시작", extra={"message_id": 123})
"""

import os
import sys
import logging
import json
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from pathlib import Path

# 로그 디렉토리 설정
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 로그 파일 경로
LOG_FILE = LOG_DIR / "spam_detector.log"
JSON_LOG_FILE = LOG_DIR / "spam_detector.json.log"


class JsonFormatter(logging.Formatter):
    """JSON 형식 로그 포맷터 (분석 도구 연동용)"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # extra 필드 추가 (사용자 정의 데이터)
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data
        
        # 예외 정보 포함
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """컬러 콘솔 출력 포맷터"""
    
    # ANSI 색상 코드
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        # 색상 적용
        color = self.COLORS.get(record.levelname, self.RESET)
        
        # 간결한 포맷
        timestamp = datetime.now().strftime("%H:%M:%S")
        level = record.levelname[0]  # 첫 글자만 (I, D, W, E, C)
        
        # 로거 이름 간소화 (app.agents.content_agent.agent → content_agent)
        name = record.name.split(".")[-2] if "." in record.name else record.name
        name = name[:15]  # 최대 15자
        
        message = record.getMessage()
        
        formatted = f"{color}[{timestamp}] [{level}] [{name:15s}]{self.RESET} {message}"
        
        # 예외 정보 포함
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted


def _parse_log_level(level_str: str, default: int = logging.INFO) -> int:
    """문자열 로그 레벨을 logging 상수로 변환"""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str.upper(), default)


def setup_logging(
    console_level: int = None,
    file_level: int = None,
    enable_json: bool = True
) -> None:
    """
    로깅 시스템 초기화
    
    Args:
        console_level: 콘솔 출력 레벨 (기본: INFO, 환경변수 LOG_LEVEL_CONSOLE로 오버라이드)
        file_level: 파일 기록 레벨 (기본: DEBUG, 환경변수 LOG_LEVEL_FILE로 오버라이드)
        enable_json: JSON 로그 파일 활성화 (기본: True, 환경변수 LOG_JSON_ENABLED로 오버라이드)
    
    Environment Variables:
        LOG_LEVEL_CONSOLE: 콘솔 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        LOG_LEVEL_FILE: 파일 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        LOG_JSON_ENABLED: JSON 로그 활성화 (1 또는 0)
    """
    # 환경변수에서 로그 레벨 읽기 (인자보다 환경변수 우선)
    env_console = os.getenv("LOG_LEVEL_CONSOLE")
    env_file = os.getenv("LOG_LEVEL_FILE")
    env_json = os.getenv("LOG_JSON_ENABLED")
    env_console_enabled = os.getenv("LOG_CONSOLE_ENABLED", "1")  # 기본값: 활성화
    
    if console_level is None:
        console_level = _parse_log_level(env_console, logging.INFO) if env_console else logging.INFO
    if file_level is None:
        file_level = _parse_log_level(env_file, logging.DEBUG) if env_file else logging.DEBUG
    if env_json is not None:
        enable_json = env_json == "1"
    
    console_enabled = env_console_enabled == "1"
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 최하위 레벨로 설정
    
    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()
    
    # ============================================================
    # 1. 콘솔 핸들러 (INFO 이상, 컬러 출력) - 환경변수로 비활성화 가능
    # ============================================================
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(ConsoleFormatter())
        root_logger.addHandler(console_handler)
    
    # ============================================================
    # 2. 파일 핸들러 (DEBUG 이상, 매일 로테이션)
    # ============================================================
    file_handler = TimedRotatingFileHandler(
        filename=str(LOG_FILE),
        when="midnight",      # 매일 자정에 로테이션
        interval=1,
        backupCount=7,        # 7일치 보관
        encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    file_handler.suffix = "%Y-%m-%d"  # 파일명: spam_detector.log.2026-01-29
    root_logger.addHandler(file_handler)
    
    # ============================================================
    # 3. JSON 파일 핸들러 (분석 도구 연동용)
    # ============================================================
    if enable_json:
        json_handler = RotatingFileHandler(
            filename=str(JSON_LOG_FILE),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8"
        )
        json_handler.setLevel(logging.INFO)
        json_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(json_handler)
    
    # ============================================================
    # 4. 외부 라이브러리 로그 레벨 조정 (노이즈 감소)
    # ============================================================
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # 초기화 완료 로그
    logger = logging.getLogger(__name__)
    console_name = logging.getLevelName(console_level)
    file_name = logging.getLevelName(file_level)
    logger.info(f"로깅 초기화 완료 | Console={console_name} | File={file_name} | JSON={'ON' if enable_json else 'OFF'}")


def get_logger(name: str) -> logging.Logger:
    """
    모듈별 로거 가져오기
    
    Args:
        name: 모듈 이름 (보통 __name__ 사용)
    
    Returns:
        logging.Logger 인스턴스
    """
    return logging.getLogger(name)


# 편의 함수들
def log_message_analysis(logger: logging.Logger, message: str, result: dict) -> None:
    """메시지 분석 결과 로깅 (표준화된 형식)"""
    is_spam = result.get("is_spam")
    code = result.get("classification_code")
    prob = result.get("spam_probability", 0)
    reason = result.get("reason", "")
    
    verdict = "SPAM" if is_spam else ("HITL" if is_spam is None else "HAM")
    
    logger.info(
        f"분석완료 | {verdict} | code={code} | prob={prob:.2f} | "
        f"msg={message[:50]}{'...' if len(message) > 50 else ''} | "
        f"reason={reason[:80]}{'...' if len(reason) > 80 else ''}"
    )


def log_url_analysis(logger: logging.Logger, url: str, result: dict) -> None:
    """URL 분석 결과 로깅 (표준화된 형식)"""
    is_spam = result.get("is_spam")
    analysis_type = result.get("analysis_type", "unknown")
    reason = result.get("reason", "")
    
    verdict = "SPAM" if is_spam else ("INCONCLUSIVE" if is_spam is None else "HAM")
    
    logger.info(
        f"URL분석 | {verdict} | type={analysis_type} | "
        f"url={url[:50]}{'...' if len(url) > 50 else ''} | "
        f"reason={reason[:80]}{'...' if len(reason) > 80 else ''}"
    )


# ============================================================
# 런타임 로그 레벨 변경 함수
# ============================================================

def get_log_levels() -> dict:
    """현재 로그 레벨 조회"""
    root_logger = logging.getLogger()
    
    console_level = None
    file_level = None
    
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            console_level = logging.getLevelName(handler.level)
        elif isinstance(handler, (TimedRotatingFileHandler, RotatingFileHandler)):
            if "json" not in str(handler.baseFilename).lower():
                file_level = logging.getLevelName(handler.level)
    
    return {
        "console": console_level or "UNKNOWN",
        "file": file_level or "UNKNOWN",
        "available_levels": ["DEBUG", "INFO", "WARNING", "ERROR"]
    }


def set_log_level(target: str, level: str) -> dict:
    """
    런타임에 로그 레벨 변경
    
    Args:
        target: "console" 또는 "file"
        level: "DEBUG", "INFO", "WARNING", "ERROR"
    
    Returns:
        변경 결과
    """
    level_upper = level.upper()
    new_level = _parse_log_level(level_upper, None)
    
    if new_level is None:
        return {"success": False, "error": f"Invalid level: {level}. Use DEBUG, INFO, WARNING, or ERROR"}
    
    root_logger = logging.getLogger()
    changed = False
    
    for handler in root_logger.handlers:
        if target == "console":
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                handler.setLevel(new_level)
                changed = True
        elif target == "file":
            if isinstance(handler, TimedRotatingFileHandler):
                handler.setLevel(new_level)
                changed = True
    
    if changed:
        logger = logging.getLogger(__name__)
        logger.info(f"로그 레벨 변경됨 | {target}={level_upper}")
        return {"success": True, "target": target, "level": level_upper}
    else:
        return {"success": False, "error": f"Handler not found for target: {target}"}


def set_console_enabled(enabled: bool) -> dict:
    """
    콘솔 로그 출력 ON/OFF
    
    Args:
        enabled: True=콘솔 출력 ON, False=콘솔 출력 OFF
    """
    root_logger = logging.getLogger()
    logger = logging.getLogger(__name__)
    
    if enabled:
        # 이미 콘솔 핸들러가 있는지 확인
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                return {"success": True, "console_enabled": True, "message": "Already enabled"}
        
        # 콘솔 핸들러 추가
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(ConsoleFormatter())
        root_logger.addHandler(console_handler)
        logger.info("콘솔 로그 출력 활성화됨")
        return {"success": True, "console_enabled": True}
    else:
        # 콘솔 핸들러 제거
        for handler in root_logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                root_logger.removeHandler(handler)
                logger.info("콘솔 로그 출력 비활성화됨")
                return {"success": True, "console_enabled": False}
        
        return {"success": True, "console_enabled": False, "message": "Already disabled"}
