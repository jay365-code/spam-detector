"""
RAG Re-migration Script
========================
기존 spam_rag_intent_v2 컬렉션의 모든 entry를:
1. original_message 기준으로 현재 LLM을 통해 Intent Summary 재생성
2. text-embedding-3-small로 재임베딩
3. 새로운 클린 컬렉션(spam_rag_intent_v2)에 교체 저장

실행 방법:
    cd backend
    python remigrate_rag.py [--dry-run] [--batch-size 10]

    --dry-run    : 실제 저장 없이 처음 5개만 Intent Summary 생성하여 미리 확인
    --batch-size : LLM 호출 동시 처리 수 (기본: 5)
"""
import os
import sys
import asyncio
import argparse
import time
import uuid
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

COLLECTION_NAME = "spam_rag_intent_v2"
TEMP_COLLECTION_NAME = "spam_rag_intent_v2_remigrating"
EMBEDDING_MODEL = "text-embedding-3-small"


# ──────────────────────────────────────────────
# Intent Summary 생성 (현재 LLM 사용)
# ──────────────────────────────────────────────
INTENT_SUMMARY_PROMPT = """[GOAL]
Understand the input message and summarize its "Core Intent" in 1-2 sentences.
Remove all variable values (amounts, phone numbers, URLs, specifics) and focus on the *Pattern* and *Action*.

[INPUT]
{message}

[OUTPUT GUIDELINES]
- Format: "Principal Intent / Tactics / Action Request"
- Do NOT include any PII (Person Identifiable Information) or specific numbers.
- Example:
    Input: "Deposit 300 today, contact 010-1234-5678"
    Output: "Illegal Loan Advertisement / Immediate Deposit Promise / Request for contact via personal number"
"""


async def generate_intent_summary(message: str, llm) -> str:
    """LLM으로 Intent Summary 생성"""
    from langchain_core.messages import HumanMessage
    prompt = INTENT_SUMMARY_PROMPT.format(message=message)
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                return first.get("text", "")
            return str(first)
        return str(content).strip()
    except Exception as e:
        logger.error(f"  [Error] Intent summary generation failed: {e}")
        return ""


def get_llm():
    """환경변수 기반으로 현재 설정된 LLM 클라이언트 반환"""
    provider = os.getenv("LLM_PROVIDER", "GEMINI").upper()
    model = os.getenv("LLM_MODEL", "gemini-3-flash-preview")

    if provider == "GEMINI":
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY", "").split(",")[0].strip()
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in .env")
        logger.info(f"LLM: GEMINI / Model: {model}")
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0.0,
            max_retries=2,
        )
    elif provider == "OPENAI":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY", "").split(",")[0].strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set in .env")
        logger.info(f"LLM: OPENAI / Model: {model}")
        return ChatOpenAI(model=model, api_key=api_key, temperature=0.0, max_retries=2)
    elif provider == "CLAUDE":
        from langchain_anthropic import ChatAnthropic
        api_key = os.getenv("CLAUDE_API_KEY", "").split(",")[0].strip()
        if not api_key:
            raise ValueError("CLAUDE_API_KEY is not set in .env")
        logger.info(f"LLM: CLAUDE / Model: {model}")
        return ChatAnthropic(model=model, anthropic_api_key=api_key, temperature=0.0, max_retries=2)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def get_chroma_collection(collection_name: str, embedding_func):
    """ChromaDB 컬렉션 연결"""
    from langchain_chroma import Chroma
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(backend_dir, "data", "chroma_db")
    logger.info(f"ChromaDB Path: {db_path}")
    return Chroma(
        collection_name=collection_name,
        embedding_function=embedding_func,
        persist_directory=db_path,
    )


def get_embedding_func():
    """text-embedding-3-small 임베딩 함수 반환"""
    from langchain_openai import OpenAIEmbeddings
    api_key = os.getenv("OPENAI_API_KEY", "").split(",")[0].strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set (required for embedding)")
    return OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=api_key)


# ──────────────────────────────────────────────
# 메인 Migration 로직
# ──────────────────────────────────────────────
async def run_migration(dry_run: bool = False, batch_size: int = 5):
    logger.info("=" * 60)
    logger.info("RAG Re-migration 시작")
    logger.info(f"  대상 컬렉션 : {COLLECTION_NAME}")
    logger.info(f"  임베딩 모델 : {EMBEDDING_MODEL}")
    logger.info(f"  dry-run     : {dry_run}")
    logger.info(f"  batch-size  : {batch_size}")
    logger.info("=" * 60)

    # 1. 기존 데이터 전체 읽기
    embedding_func = get_embedding_func()
    old_db = get_chroma_collection(COLLECTION_NAME, embedding_func)
    old_collection = old_db._collection

    raw = old_collection.get(include=["documents", "metadatas"])
    ids = raw.get("ids", [])
    docs = raw.get("documents", [])
    metas = raw.get("metadatas", [])

    if not ids:
        logger.warning("❌ 컬렉션에 데이터가 없습니다. 종료합니다.")
        return

    total = len(ids)
    logger.info(f"✅ 총 {total}개 entry 발견")

    if dry_run:
        logger.info("🔍 [DRY-RUN] 처음 5개만 Intent Summary 생성 후 종료합니다.\n")
        ids, docs, metas = ids[:5], docs[:5], metas[:5]

    # 2. LLM 준비
    llm = get_llm()

    # 3. 배치 단위로 Intent Summary 재생성
    all_new_entries = []
    failed_ids = []

    for batch_start in range(0, len(ids), batch_size):
        batch_ids = ids[batch_start:batch_start + batch_size]
        batch_docs = docs[batch_start:batch_start + batch_size]
        batch_metas = metas[batch_start:batch_start + batch_size]

        logger.info(f"\n[Batch {batch_start // batch_size + 1}] {batch_start + 1} ~ {batch_start + len(batch_ids)} / {len(ids)}")

        # 배치 내에서 병렬로 Intent Summary 생성
        tasks = []
        for i, meta in enumerate(batch_metas):
            original_msg = meta.get("original_message", "") or batch_docs[i]
            tasks.append(generate_intent_summary(original_msg, llm))

        summaries = await asyncio.gather(*tasks)

        for i, (old_id, meta, summary) in enumerate(zip(batch_ids, batch_metas, summaries)):
            original_msg = meta.get("original_message", "") or batch_docs[i]
            if not summary:
                logger.warning(f"  ⚠️  [{old_id}] Intent Summary 생성 실패, 스킵")
                failed_ids.append(old_id)
                continue

            logger.info(f"  ✓ [{old_id}] {original_msg[:40]}...")
            logger.info(f"         → {summary[:80]}...")

            all_new_entries.append({
                "intent_summary": summary,
                "metadata": {**meta, "remigrated_at": datetime.now().isoformat()},
            })

        # Rate limit 방지: 배치 간 잠시 대기
        if batch_start + batch_size < len(ids):
            time.sleep(0.5)

    logger.info(f"\n[요약] 성공: {len(all_new_entries)}개 / 실패: {len(failed_ids)}개")

    if dry_run:
        logger.info("🔍 [DRY-RUN] 저장 없이 종료합니다.")
        return

    if not all_new_entries:
        logger.error("❌ 저장할 entry가 없습니다. 종료합니다.")
        return

    # 4. 기존 컬렉션 전체 삭제 후 재삽입
    logger.info(f"\n♻️  기존 컬렉션({COLLECTION_NAME}) 전체 삭제 후 재삽입 시작...")

    # 기존 entry 전부 삭제
    all_existing_ids = old_collection.get()["ids"]
    if all_existing_ids:
        old_collection.delete(ids=all_existing_ids)
        logger.info(f"  🗑️  {len(all_existing_ids)}개 기존 entry 삭제 완료")

    # 신규 entry 배치 삽입 (새 ID 부여)
    insert_batch_size = 50
    inserted = 0
    for i in range(0, len(all_new_entries), insert_batch_size):
        batch = all_new_entries[i:i + insert_batch_size]
        new_ids = [f"rag_{uuid.uuid4().hex[:8]}" for _ in batch]
        texts = [e["intent_summary"] for e in batch]
        metadatas = [e["metadata"] for e in batch]

        old_db.add_texts(texts=texts, metadatas=metadatas, ids=new_ids)
        inserted += len(batch)
        logger.info(f"  📥 삽입 중... {inserted}/{len(all_new_entries)}")
        time.sleep(0.3)

    logger.info("=" * 60)
    logger.info(f"🎉 Re-migration 완료!")
    logger.info(f"   삽입 성공 : {inserted}개")
    logger.info(f"   실패 스킵 : {len(failed_ids)}개")
    if failed_ids:
        logger.warning(f"   실패 IDs  : {failed_ids}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="RAG Re-migration: Intent Summary 재생성 + 재임베딩")
    parser.add_argument("--dry-run", action="store_true", help="처음 5개만 테스트 (저장 안 함)")
    parser.add_argument("--batch-size", type=int, default=5, help="LLM 병렬 처리 배치 크기 (기본: 5)")
    args = parser.parse_args()

    asyncio.run(run_migration(dry_run=args.dry_run, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
