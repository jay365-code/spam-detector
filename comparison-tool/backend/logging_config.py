"""
Spam Validator - 로깅 설정
==========================

Spam Detector의 logging_config.py 간소화 버전
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 로그 디렉토리 설정
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "spam_validator.log"


class ConsoleFormatter(logging.Formatter):
    """컬러 콘솔 출력 포맷터"""
    
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%H:%M:%S")
        level = record.levelname[0]
        name = record.name.split(".")[-1][:15]
        message = record.getMessage()
        
        formatted = f"{color}[{timestamp}] [{level}] [{name:15s}]{self.RESET} {message}"
        
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted


def _parse_log_level(level_str: str, default: int = logging.INFO) -> int:
    """문자열 로그 레벨을 logging 상수로 변환"""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return level_map.get(level_str.upper(), default)


def setup_logging(
    console_level: int = None,
    file_level: int = None
) -> None:
    """로깅 시스템 초기화"""
    
    # 환경변수에서 로그 레벨 읽기
    env_console = os.getenv("LOG_LEVEL_CONSOLE")
    env_file = os.getenv("LOG_LEVEL_FILE")
    env_console_enabled = os.getenv("LOG_CONSOLE_ENABLED", "1")  # 기본값: 활성화
    
    if console_level is None:
        console_level = _parse_log_level(env_console, logging.INFO) if env_console else logging.INFO
    if file_level is None:
        file_level = _parse_log_level(env_file, logging.DEBUG) if env_file else logging.DEBUG
    
    console_enabled = env_console_enabled == "1"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    
    # 콘솔 핸들러 (환경변수로 비활성화 가능)
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(ConsoleFormatter())
        root_logger.addHandler(console_handler)
    
    # 파일 핸들러
    file_handler = TimedRotatingFileHandler(
        filename=str(LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root_logger.addHandler(file_handler)
    
    # 외부 라이브러리 노이즈 감소
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    console_name = logging.getLevelName(console_level)
    file_name = logging.getLevelName(file_level)
    logger.info(f"로깅 초기화 완료 | Console={console_name} | File={file_name}")


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 가져오기"""
    return logging.getLogger(name)


# ============================================================
# 런타임 로그 레벨/콘솔 제어 함수
# ============================================================

def get_log_levels() -> dict:
    """현재 로그 레벨 및 콘솔 상태 조회"""
    root_logger = logging.getLogger()
    
    console_level = None
    console_enabled = False
    file_level = None
    
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            console_level = logging.getLevelName(handler.level)
            console_enabled = True
        elif isinstance(handler, TimedRotatingFileHandler):
            file_level = logging.getLevelName(handler.level)
    
    return {
        "console": console_level or "OFF",
        "console_enabled": console_enabled,
        "file": file_level or "UNKNOWN",
        "available_levels": ["DEBUG", "INFO", "WARNING", "ERROR"]
    }


def set_log_level(target: str, level: str) -> dict:
    """
    런타임에 로그 레벨 변경
    
    Args:
        target: "console" 또는 "file"
        level: "DEBUG", "INFO", "WARNING", "ERROR"
    """
    new_level = _parse_log_level(level.upper(), None)
    
    if new_level is None:
        return {"success": False, "error": f"Invalid level: {level}"}
    
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
        logger.info(f"로그 레벨 변경됨 | {target}={level.upper()}")
        return {"success": True, "target": target, "level": level.upper()}
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
