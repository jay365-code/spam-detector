import os
import logging
import threading
from typing import List, Dict

logger = logging.getLogger(__name__)

class LLMKeyManager:
    """
    동일 공급자 내의 여러 API 키를 관리하고 로테이션하는 유틸리티 클래스.
    threading.Lock을 사용하여 멀티스레드 환경에서 안전하게 동작합니다.
    """
    _instance = None
    _lock = threading.Lock()
    _keys_pool: Dict[str, List[str]] = {}
    _current_index: Dict[str, int] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMKeyManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """환경변수에서 키 리스트를 로드하여 풀(Pool) 구성"""
        providers = ["GEMINI", "OPENAI", "CLAUDE"]
        for p in providers:
            # 기존 _API_KEY 환경변수에서 콤마 구분 리스트 로드 (단일 키와 멀티 키 통합 처리)
            keys_str = os.getenv(f"{p}_API_KEY", "")
            if keys_str:
                keys = [k.strip() for k in keys_str.split(",") if k.strip()]
            else:
                keys = []
            
            self._keys_pool[p] = keys
            self._current_index[p] = 0
            
            if keys:
                logger.info(f"[KeyManager] Initialized {p} with {len(keys)} key(s).")
            else:
                logger.warning(f"[KeyManager] No keys found for {p}.")

    def get_key(self, provider: str) -> str:
        """현재 활성화된 키 반환"""
        provider = provider.upper()
        keys = self._keys_pool.get(provider, [])
        if not keys:
            return ""
        
        idx = self._current_index.get(provider, 0)
        # 인덱스 범위 초과 방지
        if idx >= len(keys):
            idx = 0
            self._current_index[provider] = 0
            
        return keys[idx]

    def rotate_key(self, provider: str, failed_key: str = None) -> bool:
        """
        다음 키로 인덱스 전환.
        대량 병렬 처리 시 여러 스레드가 동시에 전환을 시도하는 것을 방지하기 위해 Lock과 failed_key 체크를 수행합니다.
        
        :param provider: LLM 공급자 (GEMINI, OPENAI 등)
        :param failed_key: 에러를 발생시킨 당시의 API 키. 현재 키와 다르면 이미 다른 스레드가 전환한 것으로 간주.
        :return: 전환 성공 여부 (한 바퀴 다 돌았으면 False)
        """
        provider = provider.upper()
        keys = self._keys_pool.get(provider, [])
        
        if len(keys) <= 1:
            logger.warning(f"[KeyManager] {provider} has only one/no key. Cannot rotate.")
            return False
            
        with self._lock:
            current_key = self.get_key(provider)
            
            # [동시성 제어] 이미 다른 스레드에 의해 키가 바뀌었다면 추가 전환 불필요
            if failed_key and current_key != failed_key:
                logger.info(f"[KeyManager] {provider} key already rotated by another thread. (Current: {current_key[:10]}...)")
                return True
                
            new_idx = (self._current_index.get(provider, 0) + 1) % len(keys)
            self._current_index[provider] = new_idx
            
            # 바뀐 키의 앞부분만 로그 출력
            masked_key = f"{self.get_key(provider)[:10]}..."
            logger.info(f"[KeyManager] Rotated {provider} key to index {new_idx} (Key: {masked_key})")
            
            # 인덱스가 0으로 돌아왔다면 한 바퀴 다 돈 것임
            return new_idx != 0

    def get_active_info(self, provider: str) -> dict:
        """현재 상태 정보 반환"""
        provider = provider.upper()
        keys = self._keys_pool.get(provider, [])
        return {
            "total": len(keys),
            "current_index": self._current_index.get(provider, 0),
            "has_rotation": len(keys) > 1
        }

# 싱글톤 인스턴스
key_manager = LLMKeyManager()
