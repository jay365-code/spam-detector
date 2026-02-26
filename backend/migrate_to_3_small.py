import os
import sys
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
import logging
import uuid
import time

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv(override=True)

def migrate_data():
    logger.info("🚀 Starting Migration: spam_rag_intent(ada-002) -> spam_rag_intent_v2(3-small)")

    # DB Path (backend/data/chroma_db)
    # The script is in C:\Users\leejo\Project\AI Agent\Spam Detector\backend
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(backend_dir, "data", "chroma_db")
    logger.info(f"📂 DB Path: {db_path}")

    if not os.path.exists(db_path):
        logger.error(f"❌ DB Path does not exist: {db_path}")
        return

    # 1. Connect to Old Collection using text-embedding-ada-002 (Old Model)
    logger.info("🔌 Connecting to OLD collection (spam_rag_intent) with text-embedding-ada-002...")
    try:
        old_embedding_func = OpenAIEmbeddings(model="text-embedding-ada-002")
        old_db = Chroma(
            collection_name="spam_rag_intent",
            embedding_function=old_embedding_func,
            persist_directory=db_path
        )
        old_data = old_db.get(include=["documents", "metadatas"])
        
        if not old_data["ids"]:
            logger.warning("⚠️ No data found in 'spam_rag_intent'. Migration skipped.")
            return

        total_docs = len(old_data["ids"])
        logger.info(f"✅ Found {total_docs} documents in 'spam_rag_intent'.")

    except Exception as e:
        logger.error(f"❌ Failed to load old collection: {e}")
        return

    # 2. Connect to New Collection using text-embedding-3-small (New Model)
    logger.info("🔌 Connecting to NEW collection (spam_rag_intent_v2) with text-embedding-3-small...")
    try:
        new_embedding_func = OpenAIEmbeddings(model="text-embedding-3-small")
        new_db = Chroma(
            collection_name="spam_rag_intent_v2",
            embedding_function=new_embedding_func,
            persist_directory=db_path
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize new collection: {e}")
        return

    # 3. Migrate Data
    logger.info("🔄 Migrating data (This might take a while due to re-embedding)...")
    count = 0
    try:
        ids = old_data["ids"]
        documents = old_data["documents"]
        metadatas = old_data["metadatas"]
        
        # Rate limit/Stability를 위한 100건 단위 Batch 처리
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            batch_ids_old = ids[i:i+batch_size]
            batch_docs = documents[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]
            
            # 고유한 새로운 ID 생성 (형식: rag_...)
            new_ids = [f"rag_{uuid.uuid4().hex[:8]}" for _ in batch_ids_old]
            
            # add_texts 호출 시 new_embedding_func를 통해 자동으로 새로운 임베딩 벡터가 생성되어 저장됨
            new_db.add_texts(
                texts=batch_docs,
                metadatas=batch_metas,
                ids=new_ids
            )
            count += len(batch_ids_old)
            logger.info(f"   - Migrated {count}/{total_docs} documents...")
            
            # API Rate Limit을 고려하여 잠시 대기
            time.sleep(1)
            
        logger.info(f"🎉 Migration Completed! {count} documents moved and re-embedded into 'spam_rag_intent_v2'.")
        
    except Exception as e:
        logger.error(f"❌ Error during migration: {e}")

if __name__ == "__main__":
    migrate_data()
