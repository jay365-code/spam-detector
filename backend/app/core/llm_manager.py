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
    _quota_exhausted: Dict[str, bool] = {}

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
            self._quota_exhausted[p] = False
            
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
            self._quota_exhausted[provider] = True
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
            if new_idx == 0:
                self._quota_exhausted[provider] = True
                logger.warning(f"[KeyManager] {provider} all keys exhausted (full circle).")
            return new_idx != 0

    def set_current_index(self, provider: str, index: int) -> bool:
        """
        수동으로 특정 인덱스의 키를 사용하도록 설정합니다 (UI에서 강제 지정용).
        """
        provider = provider.upper()
        keys = self._keys_pool.get(provider, [])
        if not keys or index < 0 or index >= len(keys):
            logger.error(f"[KeyManager] Invalid index {index} for {provider}. (Total keys: {len(keys)})")
            return False

        with self._lock:
            self._current_index[provider] = index
            self._quota_exhausted[provider] = False  # 새 키를 설정했으므로 Exhausted 해제
            masked_key = f"{self.get_key(provider)[:10]}..."
            logger.info(f"[KeyManager] Manually set {provider} key to index {index} (Key: {masked_key})")
            return True

    def is_quota_exhausted(self, provider: str) -> bool:
        """해당 공급자의 모든 키가 quota 소진되었는지 여부 (병렬 처리 시 즉시 중단용)"""
        provider = provider.upper()
        return self._quota_exhausted.get(provider, False)

    def reset_quota_exhausted(self, provider: str = None) -> dict:
        """
        Quota Exhausted 플래그 해제 (UI 버튼으로 재시도 가능하게).
        :param provider: None이면 모든 공급자, "GEMINI" 등 특정 공급자만
        :return: {"reset": [provider list], "message": str}
        """
        if provider:
            provider = provider.upper()
            if provider in self._quota_exhausted:
                self._quota_exhausted[provider] = False
                logger.info(f"[KeyManager] Reset quota_exhausted for {provider}.")
                return {"reset": [provider], "message": f"{provider} quota exhausted 플래그 해제됨."}
            return {"reset": [], "message": f"{provider} not found."}
        # 모든 공급자 리셋
        for p in self._quota_exhausted:
            self._quota_exhausted[p] = False
        logger.info("[KeyManager] Reset quota_exhausted for all providers.")
        return {"reset": list(self._quota_exhausted.keys()), "message": "모든 공급자 quota exhausted 플래그 해제됨."}

    def get_quota_status(self) -> dict:
        """각 공급자별 quota exhausted 상태 조회 (UI용)"""
        return {
            p: {
                "exhausted": self._quota_exhausted.get(p, False),
                "total": len(self._keys_pool.get(p, [])),
                "current_index": self._current_index.get(p, 0)
            }
            for p in ["GEMINI", "OPENAI", "CLAUDE"]
        }

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
