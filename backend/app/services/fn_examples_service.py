"""
FN (False Negative) Examples Service
ChromaDB를 사용하여 FN 스팸 예시를 저장하고 검색하는 서비스
"""
import os
import uuid
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

class FnExamplesService:
    def __init__(self):
        self.collection_name = "fn_examples"
        self.db = None
        self._embedding_function = None
    
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
            
            db_path = os.path.join(os.path.dirname(__file__), "../../../data/chroma_db")
            print(f"[FnExamplesService] Connecting to ChromaDB at {db_path}")
            
            self.db = Chroma(
                collection_name=self.collection_name,
                embedding_function=self._get_embedding_function(),
                persist_directory=db_path
            )
        return self.db
    
    def add_example(self, message: str, label: str, code: str, category: str, reason: str) -> Dict[str, Any]:
        """
        새 FN 예시 추가
        
        Args:
            message: 스팸 메시지 원문
            label: "SPAM" or "HAM"
            code: 분류 코드 (예: "1", "2", "3")
            category: 카테고리 (예: "술집/유흥업소 광고")
            reason: 판단 근거
        
        Returns:
            추가된 예시 정보
        """
        db = self._get_db()
        example_id = f"fn_{uuid.uuid4().hex[:8]}"
        
        metadata = {
            "label": label,
            "code": code,
            "category": category,
            "reason": reason
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
        """모든 FN 예시 조회"""
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
        FN 예시 업데이트
        """
        db = self._get_db()
        collection = db._collection
        
        # 기존 데이터 조회
        existing = self.get_example_by_id(example_id)
        if not existing:
            return None
        
        # 업데이트할 필드 결정
        new_message = message if message is not None else existing["message"]
        new_metadata = {
            "label": label if label is not None else existing.get("label", "SPAM"),
            "code": code if code is not None else existing.get("code", ""),
            "category": category if category is not None else existing.get("category", ""),
            "reason": reason if reason is not None else existing.get("reason", "")
        }
        
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
        """FN 예시 삭제"""
        db = self._get_db()
        collection = db._collection
        
        try:
            collection.delete(ids=[example_id])
            return True
        except Exception as e:
            print(f"[FnExamplesService] Delete error: {e}")
            return False
    
    def search_similar(self, message: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        유사한 FN 예시 검색 (Content Agent에서 사용)
        
        Args:
            message: 검색할 메시지
            k: 반환할 결과 수
        
        Returns:
            유사 예시 목록 (유사도 점수 포함)
        """
        try:
            db = self._get_db()
            collection = db._collection
            
            # Collection이 비어있는지 먼저 확인
            count = collection.count()
            if count == 0:
                print("[FnExamplesService] Collection is empty, skipping search")
                return []
            
            # k가 실제 데이터 수보다 크면 조정
            actual_k = min(k, count)
            
            results = db.similarity_search_with_score(message, k=actual_k)
            
            examples = []
            for doc, score in results:
                examples.append({
                    "message": doc.page_content,
                    "score": float(score),  # L2 distance: 낮을수록 유사
                    **doc.metadata
                })
            
            return examples
        except Exception as e:
            print(f"[FnExamplesService] Search error: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """FN 예시 통계 조회"""
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
_fn_service_instance = None

def get_fn_examples_service() -> FnExamplesService:
    """싱글톤 서비스 인스턴스 반환"""
    global _fn_service_instance
    if _fn_service_instance is None:
        _fn_service_instance = FnExamplesService()
    return _fn_service_instance
