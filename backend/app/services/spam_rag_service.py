"""
Spam RAG Service (Reference Examples)
ChromaDB를 사용하여 스팸 참조 예시(Reference Examples)를 저장하고 검색하는 서비스
(구 FnExamplesService)
"""
import os
import uuid
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

import logging
from app.core.logging_config import get_logger

# 중앙 집중식 로거 사용
logger = get_logger(__name__)

class SpamRagService:
    def __init__(self):
        self.collection_name = "spam_rag"
        self.db = None
        self._embedding_function = None
        logger.info("SpamRagService initialized")
    
    def _get_embedding_function(self):
        """Lazy load embedding function"""
        if self._embedding_function is None:
            from langchain_openai import OpenAIEmbeddings
            self._embedding_function = OpenAIEmbeddings(model="text-embedding-ada-002")
        return self._embedding_function
    
    def _get_db(self):
        """Lazy load ChromaDB connection"""
        if self.db is None:
            from langchain_chroma import Chroma
            
            # Project Root의 data 폴더 사용
            db_path = os.path.join(os.path.dirname(__file__), "../../../data/chroma_db")
            logger.info(f"[SpamRagService] Connecting to ChromaDB at {db_path}")
            
            self.db = Chroma(
                collection_name=self.collection_name,
                embedding_function=self._get_embedding_function(),
                persist_directory=db_path
            )
        return self.db
    
    def add_example(self, message: str, label: str, code: str, category: str, reason: str) -> Dict[str, Any]:
        """
        새 참조 예시 추가
        
        Args:
            message: 메시지 원문
            label: "SPAM" or "HAM"
            code: 분류 코드 (예: "1", "2", "3")
            category: 카테고리 (예: "술집/유흥업소 광고")
            reason: 판단 근거
        
        Returns:
            추가된 예시 정보
            
        Raises:
            ValueError: 이미 동일한 메시지가 존재하는 경우
        """
        # 1. 중복 검사 (벡터 유사도 + 완전 일치)
        # 유사도 검색
        similar_items = self.search_similar(message, k=1)
        
        if similar_items:
            img = similar_items[0]
            existing_msg = img.get("message", "")
            score = img.get("score", 1.0)
            
            logger.info(f"[SpamRagService] Duplicate checking: Input='{message[:20]}...', Found='{existing_msg[:20]}...', Score={score}")
            
            # Condition 1: 완전 일치 (공백 제거 후 비교)
            if message.strip() == existing_msg.strip():
                 logger.warning("[SpamRagService] Exact string match detected!")
                 raise ValueError("Duplicate message detected: This message already exists in the database.")
                 
            # Condition 2: 벡터 유사도가 매우 높음 (0.01 미만)
            if score < 0.01:
                logger.warning(f"[SpamRagService] High vector similarity ({score}) detected!")
                raise ValueError("Duplicate message detected: This message already exists in the database.")

        db = self._get_db()
        example_id = f"rag_{uuid.uuid4().hex[:8]}"
        
        # 현재 시간 (ISO 8601)
        from datetime import datetime
        created_at = datetime.now().isoformat()

        metadata = {
            "label": label,
            "code": code,
            "category": category,
            "reason": reason,
            "created_at": created_at
        }
        
        db.add_texts(
            texts=[message],
            metadatas=[metadata],
            ids=[example_id]
        )
        
        return {
            "id": example_id,
            "message": message,
            **metadata
        }
    
    def get_all_examples(self) -> List[Dict[str, Any]]:
        """모든 참조 예시 조회"""
        db = self._get_db()
        
        # ChromaDB의 _collection을 직접 사용하여 모든 데이터 가져오기
        collection = db._collection
        results = collection.get(include=["documents", "metadatas"])
        
        examples = []
        if results and results.get("ids"):
            for i, id_ in enumerate(results["ids"]):
                examples.append({
                    "id": id_,
                    "message": results["documents"][i] if results["documents"] else "",
                    **(results["metadatas"][i] if results["metadatas"] else {})
                })
        
        return examples
    
    def get_example_by_id(self, example_id: str) -> Optional[Dict[str, Any]]:
        """ID로 특정 예시 조회"""
        db = self._get_db()
        collection = db._collection
        
        results = collection.get(
            ids=[example_id],
            include=["documents", "metadatas"]
        )
        
        if results and results["ids"]:
            return {
                "id": results["ids"][0],
                "message": results["documents"][0] if results["documents"] else "",
                **(results["metadatas"][0] if results["metadatas"] else {})
            }
        return None
    
    def update_example(self, example_id: str, message: str = None, label: str = None, 
                       code: str = None, category: str = None, reason: str = None) -> Optional[Dict[str, Any]]:
        """
        참조 예시 업데이트
        """
        db = self._get_db()
        collection = db._collection
        
        # 기존 데이터 조회
        existing = self.get_example_by_id(example_id)
        if not existing:
            return None
        
        # 새 메시지 결정
        new_message = message if message is not None else existing["message"]
        
        # 기존 메타데이터 복사 (created_at 등 보존)
        new_metadata = existing.copy()
        
        # id, message, score 등 메타데이터가 아닌 필드는 제거 (저장 시 메타데이터로 들어가지 않도록)
        for key in ["id", "message", "score"]:
            new_metadata.pop(key, None)

        # 업데이트할 필드 덮어쓰기
        if label is not None: new_metadata["label"] = label
        if code is not None: new_metadata["code"] = code
        if category is not None: new_metadata["category"] = category
        if reason is not None: new_metadata["reason"] = reason
        
        # 삭제 후 재추가 (ChromaDB는 update가 제한적)
        collection.delete(ids=[example_id])
        
        db.add_texts(
            texts=[new_message],
            metadatas=[new_metadata],
            ids=[example_id]
        )
        
        return {
            "id": example_id,
            "message": new_message,
            **new_metadata
        }
    
    def delete_example(self, example_id: str) -> bool:
        """참조 예시 삭제"""
        db = self._get_db()
        collection = db._collection
        
        try:
            collection.delete(ids=[example_id])
            return True
        except Exception as e:
            logger.error(f"[SpamRagService] Delete error: {e}")
            return False
    
    def search_similar(self, message: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        유사한 스팸 참조 예시 검색
        """
        logger.debug(f"Searching similar: '{message[:20]}...'")
        try:
            db = self._get_db()
            collection = db._collection
            
            # Collection이 비어있는지 먼저 확인
            count = collection.count()
            # logger.debug(f"Collection count: {count}")
            if count == 0:
                logger.debug("[SpamRagService] Collection is empty, skipping search")
                return []
            
            # k가 실제 데이터 수보다 크면 조정
            actual_k = min(k, count)
            
            # 1. 쿼리 텍스트를 직접 임베딩 (LangChain Embedding Function 사용)
            # _collection.query에 텍스트를 바로 넣으면 Chroma 기본 임베딩(ONNX)을 쓰려다가 에러가 남.
            embedding_func = self._get_embedding_function()
            query_vector = embedding_func.embed_query(message)
            
            # 2. 임베딩 벡터로 검색 (ID 포함)
            query_results = collection.query(
                query_embeddings=[query_vector],
                n_results=actual_k,
                include=["documents", "metadatas", "distances"]
            )
            
            examples = []
            if query_results and query_results.get("ids") and query_results["ids"][0]:
                ids = query_results["ids"][0]
                
                # documents가 None이거나 [None]일 경우 처리
                docs = query_results.get("documents")
                documents = docs[0] if (docs and docs[0] is not None) else []
                
                # metadatas가 None이거나 [None]일 경우 처리
                metas = query_results.get("metadatas")
                metadatas = metas[0] if (metas and metas[0] is not None) else []
                
                # distances가 None이거나 [None]일 경우 처리
                dists = query_results.get("distances")
                distances = dists[0] if (dists and dists[0] is not None) else []
                
                for i, id_ in enumerate(ids):
                    ex_msg = documents[i] if i < len(documents) else ""
                    ex_score = float(distances[i]) if i < len(distances) else 0.0
                    
                    # 상세 로그 출력 (메시지 앞부분과 점수)
                    logger.debug(f"  - Found: '{ex_msg[:30]}...' (Score: {ex_score:.4f})")
                    
                    # 메타 데이터 안전하게 가져오기
                    meta = metadatas[i] if (i < len(metadatas) and metadatas[i]) else {}
                    
                    examples.append({
                        "id": id_,
                        "message": ex_msg,
                        "score": ex_score,
                        **meta
                    })
            
            return examples
        except Exception as e:
            logger.error(f"[SpamRagService] Search error: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """참조 예시 통계 조회"""
        examples = self.get_all_examples()
        
        stats = {
            "total": len(examples),
            "by_code": {},
            "by_category": {}
        }
        
        for ex in examples:
            code = ex.get("code", "unknown")
            category = ex.get("category", "unknown")
            
            stats["by_code"][code] = stats["by_code"].get(code, 0) + 1
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
        
        return stats


# Singleton instance
_spam_rag_service_instance = None

def get_spam_rag_service() -> SpamRagService:
    """싱글톤 서비스 인스턴스 반환"""
    global _spam_rag_service_instance
    if _spam_rag_service_instance is None:
        _spam_rag_service_instance = SpamRagService()
    return _spam_rag_service_instance
