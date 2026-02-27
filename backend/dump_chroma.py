"""
ChromaDB JSON Dump Script
==========================
spam_rag_intent_v2 컬렉션의 모든 데이터를 JSON 파일로 덤프합니다.

실행 방법:
    cd backend
    python dump_chroma.py                         # 기본: dump_chroma_YYYYMMDD_HHMMSS.json
    python dump_chroma.py -o my_backup.json       # 파일명 직접 지정
    python dump_chroma.py --pretty                # 들여쓰기 없이 저장 (기본은 pretty)
"""
import os
import sys
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

COLLECTION_NAME = "spam_rag_intent_v2"
EMBEDDING_MODEL = "text-embedding-3-small"


def main():
    parser = argparse.ArgumentParser(description="ChromaDB → JSON 덤프")
    parser.add_argument("-o", "--output", type=str, default=None, help="출력 파일명 (기본: dump_chroma_YYYYMMDD_HHMMSS.json)")
    parser.add_argument("--no-pretty", action="store_true", help="들여쓰기 없이 저장")
    args = parser.parse_args()

    # 출력 파일명
    output_file = args.output or f"dump_chroma_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    # ChromaDB 연결
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings

    api_key = os.getenv("OPENAI_API_KEY", "").split(",")[0].strip()
    if not api_key:
        print("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(backend_dir, "data", "chroma_db")

    print(f"📂 ChromaDB Path : {db_path}")
    print(f"📦 Collection    : {COLLECTION_NAME}")

    ef = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=api_key)
    db = Chroma(collection_name=COLLECTION_NAME, embedding_function=ef, persist_directory=db_path)
    collection = db._collection

    raw = collection.get(include=["documents", "metadatas"])
    ids      = raw.get("ids", [])
    docs     = raw.get("documents", [])
    metas    = raw.get("metadatas", [])

    if not ids:
        print("⚠️  컬렉션에 데이터가 없습니다.")
        sys.exit(0)

    entries = []
    for id_, doc, meta in zip(ids, docs, metas):
        entries.append({
            "id": id_,
            "intent_summary": doc,
            **meta,
        })

    dump = {
        "collection": COLLECTION_NAME,
        "exported_at": datetime.now().isoformat(),
        "total": len(entries),
        "entries": entries,
    }

    indent = None if args.no_pretty else 2
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=indent)

    print(f"✅ {len(entries)}개 entry → {output_file} 저장 완료")


if __name__ == "__main__":
    main()
