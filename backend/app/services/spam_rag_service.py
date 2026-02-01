"""
Spam RAG Service (Reference Examples)
ChromaDB를 사용하여 스팸 참조 예시(Reference Examples)를 저장하고 검색하는 서비스
(Legacy: FnExamplesService)
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
        # [Schema Update] v1.1 Intent-based RAG Collection
        self.collection_name = "spam_rag_intent"
        self.db = None
        self._embedding_function = None
        logger.info(f"SpamRagService initialized (Collection: {self.collection_name})")
    
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
    
    def add_example(self, intent_summary: str, original_message: str, label: str, code: str, category: str, reason: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        새 참조 예시 추가 (Intent-based)
        
        Args:
            intent_summary: [Embedding 대상] 의도/패턴/행위 요약문 (Judgement Semantic Unit)
            original_message: [Metadata] 원본 메시지
            label: "SPAM" or "HAM"
            code: 분류 코드
            category: 카테고리
            reason: 판단 근거
            metadata: 추가 메타데이터 (harm_anchor, verified 등)
        """
        if metadata is None:
            metadata = {}

        # 1. 중복 검사 (의도 요약 유사도)
        similar_items = self.search_similar(intent_summary, k=1)
        
        if similar_items:
            # Stats dictionary is not similar item, skip
             pass

        db = self._get_db()
        example_id = f"rag_{uuid.uuid4().hex[:8]}"
        
        # 현재 시간 (ISO 8601)
        from datetime import datetime
        created_at = datetime.now().isoformat()

        # [Schema Update] Original Message is now Metadata
        final_metadata = {
            "original_message": original_message,
            "label": label,
            "code": code,
            "category": category,
            "reason": reason,
            "created_at": created_at,
            **metadata
        }
        
        # [Schema Update] Embedding Target is Intent Summary
        db.add_texts(
            texts=[intent_summary], 
            metadatas=[final_metadata],
            ids=[example_id]
        )
        
        return {
            "id": example_id,
            "intent_summary": intent_summary,
            **final_metadata
        }
    
    def search_similar(self, query_intent_summary: str, k: int = 3) -> Dict[str, Any]:
        """
        유사 의도 검색 (Returns RAG Contract with Stats)
        
        Returns:
            {
                "metric": "cosine_distance",
                "query_summary": str,
                "hits": List[Dict],
                "stats": {
                    "d1": float,
                    "d2": float,
                    "gap": float,
                    "spam_count": int
                }
            }
        """
        logger.debug(f"Searching similar intent: '{query_intent_summary[:30]}...'")
        
        response = {
            "metric": "cosine_distance",
            "query_summary": query_intent_summary,
            "hits": [],
            "stats": {
                "d1": 9.9,
                "d2": 9.9,
                "gap": 0.0,
                "spam_count": 0
            }
        }

        try:
            db = self._get_db()
            collection = db._collection
            
            count = collection.count()
            if count == 0:
                return response
            
            actual_k = min(k, count)
            
            # 1. 의도 요약 임베딩
            embedding_func = self._get_embedding_function()
            query_vector = embedding_func.embed_query(query_intent_summary)
            
            # 2. 검색
            query_results = collection.query(
                query_embeddings=[query_vector],
                n_results=actual_k,
                include=["documents", "metadatas", "distances"]
            )
            
            hits = []
            distances_list = []
            spam_count = 0
            
            if query_results and query_results.get("ids") and query_results["ids"][0]:
                ids = query_results["ids"][0]
                docs = query_results.get("documents", [[]])[0]
                metas = query_results.get("metadatas", [[]])[0]
                dists = query_results.get("distances", [[]])[0]
                
                for i, id_ in enumerate(ids):
                    summary_text = docs[i] if docs else ""
                    dist = float(dists[i]) if dists else 0.0
                    meta = metas[i] if metas else {}
                    
                    distances_list.append(dist)
                    
                    # Count SPAM labels
                    if meta.get("label") == "SPAM":
                        spam_count += 1
                    
                    # Frontend Compat: Ensure 'message' field exists (prefer original_message)
                    original_msg = meta.get("original_message", "")
                    display_msg = original_msg if original_msg else summary_text

                    hits.append({
                        "id": id_,
                        "message": display_msg,       # For frontend display
                        "summary": summary_text,      # Intent summary
                        "distance": dist,
                        **meta
                    })
                    
                    logger.debug(f"  - Found Intent: '{summary_text[:20]}...' (Dist: {dist:.4f})")

            # 3. Calculate Stats
            if distances_list:
                d1 = distances_list[0]
                d2 = distances_list[1] if len(distances_list) > 1 else d1
                gap = d2 - d1
            else:
                d1, d2, gap = 9.9, 9.9, 0.0
            
            response["hits"] = hits
            response["stats"] = {
                "d1": d1,
                "d2": d2,
                "gap": gap,
                "spam_count": spam_count
            }
            
            return response

        except Exception as e:
            logger.error(f"[SpamRagService] Search error: {e}")
            return response
    
    
    def update_example(self, example_id: str, message: str = None, label: str = None, code: str = None, category: str = None, reason: str = None) -> Dict[str, Any]:
        """참조 예시 수정 (Metadata Update Only)"""
        try:
            db = self._get_db()
            # 1. Check existence
            existing = db._collection.get(ids=[example_id], include=["metadatas", "documents"])
            if not existing or not existing["ids"]:
                return None
            
            # 2. Prepare update
            current_meta = existing["metadatas"][0]
            current_doc = existing["documents"][0]
            
            new_meta = current_meta.copy()
            if message:
                new_meta["original_message"] = message
            if label:
                new_meta["label"] = label
            if code:
                new_meta["code"] = code
            if category:
                new_meta["category"] = category
            if reason:
                new_meta["reason"] = reason
                
            # Note: We are NOT updating the embedding (Intent Summary) here.
            # If the message content changes significantly, the intent might change,
            # but usually edits are for corrections. 
            # To update intent, we would need to regenerate summary and embedding.
            
            # 3. Execution (Use underlying collection directly)
            db._collection.update(
                ids=[example_id],
                metadatas=[new_meta]
                # maintain existing document/embedding
            )
            
            logger.info(f"Example updated: {example_id}")
            
            # Frontend Compat
            display_msg = new_meta.get("original_message", "")
            if not display_msg:
                display_msg = current_doc
                
            return {
                "id": example_id,
                "message": display_msg,
                "intent_summary": current_doc,
                **new_meta
            }
            
        except Exception as e:
            logger.error(f"[SpamRagService] Update error: {e}")
            raise e

    def delete_example(self, example_id: str) -> bool:
        """참조 예시 삭제"""
        try:
            db = self._get_db()
            db.delete(ids=[example_id])
            logger.info(f"Example deleted: {example_id}")
            return True
        except Exception as e:
            logger.error(f"[SpamRagService] Delete error: {e}")
            return False

    def get_all_examples(self) -> List[Dict[str, Any]]:
        """모든 참조 예시 조회"""
        try:
            db = self._get_db()
            # Chroma get (limit check via default behavior, or fetch all)
            results = db._collection.get(include=["documents", "metadatas"])
            
            examples = []
            if results and results.get("ids"):
                ids = results["ids"]
                docs = results.get("documents", [])
                metas = results.get("metadatas", [])
                
                for i, id_ in enumerate(ids):
                    summary_text = docs[i] if docs else ""
                    meta_data = metas[i] if metas else {}
                    
                    # Frontend Compat: Ensure 'message' field exists
                    original_msg = meta_data.get("original_message", "")
                    display_msg = original_msg if original_msg else summary_text
                    
                    examples.append({
                        "id": id_,
                        "message": display_msg,        # For frontend display
                        "intent_summary": summary_text,
                        **meta_data
                    })
            return examples
        except Exception as e:
            logger.error(f"[SpamRagService] Get all error: {e}")
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
