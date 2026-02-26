import os
import sys
from dotenv import load_dotenv
import chromadb

load_dotenv(override=True)

def check_all_hits():
    project_root = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(project_root, "data", "chroma_db")
    
    query = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
    
    print(f"Connecting to {db_path}...")
    client = chromadb.PersistentClient(path=db_path)
    col = client.get_collection("spam_rag_intent_v2")
    
    # We don't want to use embeddings here, just get the documents directly and print them
    res = col.get()
    
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])
    
    print(f"\nTotal Docs: {len(docs)}")
    
    found_idx = -1
    for i, (d, m) in enumerate(zip(docs, metas)):
        orig = m.get("original_message", "")
        if query in orig or query in d:
            found_idx = i
            print(f"\n--- MATCH FOUND AT INDEX {i} ---")
            print(f"Summary (Document stored for embedding): {d}")
            print(f"Meta: {m}")
            
    if found_idx == -1:
        print("Not found anywhere in DB.")

if __name__ == "__main__":
    check_all_hits()
