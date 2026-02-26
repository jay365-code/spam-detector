import os
import chromadb
import json

def check_encoding_old_db():
    project_root = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(project_root, "data", "chroma_db")
    
    client = chromadb.PersistentClient(path=db_path)
    col_old = client.get_collection("spam_rag_intent")
    
    results = col_old.get()
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])
    ids = results.get("ids", [])
    
    target = "지유신"
    print("Searching for specific Korean letters directly in raw string...")
    
    for i, (d, m) in enumerate(zip(docs, metas)):
        orig = m.get("original_message", "")
        # Force encoding to see if the string actually holds it
        try:
            if target in orig:
                print(f"[{ids[i]}] FOUND! {repr(orig)}")
                print(json.dumps(m, ensure_ascii=False))
        except:
            pass
            
    # Also dump everything to a file to use grep
    with open("db_dump.txt", "w", encoding="utf-8") as f:
        for i, (d, m) in enumerate(zip(docs, metas)):
            f.write(f"ID: {ids[i]}\n")
            f.write(f"DOC: {d}\n")
            f.write(f"META: {json.dumps(m, ensure_ascii=False)}\n\n")
            
    print("Dumped to db_dump.txt")

if __name__ == '__main__':
    check_encoding_old_db()
