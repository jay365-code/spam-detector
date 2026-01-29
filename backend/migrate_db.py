
import os
import sys
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv(override=True)

def migrate_data():
    logger.info("🚀 Starting Migration: fn_examples -> spam_rag")

    # DB Path (Project Root/data/chroma_db)
    # This script is in backend/, so ../../data/chroma_db is mistakenly backend/data/chroma_db?
    # No, ingest.py used data/chroma_db relative to backend.
    # Let's verify the path used in spam_rag_service.py: "../../../data/chroma_db" from services/
    # So from backend/ it should be "../data/chroma_db"
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data/chroma_db")
    logger.info(f"📂 DB Path: {db_path}")

    if not os.path.exists(db_path):
        logger.error(f"❌ DB Path does not exist: {db_path}")
        return

    embedding_func = OpenAIEmbeddings(model="text-embedding-ada-002")

    # 1. Connect to Old Collection
    logger.info("🔌 Connecting to OLD collection (fn_examples)...")
    try:
        old_db = Chroma(
            collection_name="fn_examples",
            embedding_function=embedding_func,
            persist_directory=db_path
        )
        old_data = old_db.get(include=["documents", "metadatas"])
        
        if not old_data["ids"]:
            logger.warning("⚠️ No data found in 'fn_examples'. Migration skipped.")
            return

        total_docs = len(old_data["ids"])
        logger.info(f"✅ Found {total_docs} documents in 'fn_examples'.")

    except Exception as e:
        logger.error(f"❌ Failed to load old collection: {e}")
        return

    # 2. Connect to New Collection
    logger.info("🔌 Connecting to NEW collection (spam_rag)...")
    try:
        new_db = Chroma(
            collection_name="spam_rag",
            embedding_function=embedding_func,
            persist_directory=db_path
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize new collection: {e}")
        return

    # 3. Migrate Data
    logger.info("🔄 Migrating data...")
    count = 0
    try:
        # Check for duplicates before adding? Chroma handles ID collisions, but we might want just strict copy
        # We will iterate and add.
        
        ids = old_data["ids"]
        documents = old_data["documents"]
        metadatas = old_data["metadatas"]
        
        # Batch add?
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i+batch_size]
            batch_docs = documents[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]
            
            # Use new IDs to be clean? Or keep old IDs?
            # Keeping old IDs is fine if they are unique. fn_examples used "fn_..."
            # spam_rag service uses "rag_...".
            # Let's generate NEW IDs to be safe and consistent with new service format "rag_"
            import uuid
            new_ids = [f"rag_{uuid.uuid4().hex[:8]}" for _ in batch_ids]
            
            new_db.add_texts(
                texts=batch_docs,
                metadatas=batch_metas,
                ids=new_ids
            )
            count += len(batch_ids)
            logger.info(f"   - Migrated {count}/{total_docs}...")
            
        logger.info(f"🎉 Migration Completed! {count} documents moved to 'spam_rag'.")
        
    except Exception as e:
        logger.error(f"❌ Error during migration: {e}")

if __name__ == "__main__":
    migrate_data()
