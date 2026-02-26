import os
import chromadb

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(project_root, "data", "chroma_db")
    print(f"DB Path: {db_path}")

    client = chromadb.PersistentClient(path=db_path)
    
    # 1. Check old collection
    print("\n--- NEW Collection (spam_rag_intent_v2) ---")
    try:
        col_new = client.get_collection("spam_rag_intent_v2")
        print(f"Count: {col_new.count()}")
        
        # Fetch all metadata and documents to see if the message exists
        results = col_new.get()
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        
        found = False
        target = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
        
        for d, m in zip(docs, metas):
            orig = m.get("original_message", "")
            if target in orig or target in d:
                print(f"FOUND in new DB!")
                print(f"Summary: {d}")
                print(f"Meta: {m}")
                found = True
                break
                
        if not found:
            print(f"NOT FOUND in new DB!")
            
    except Exception as e:
        print(f"Error accessing new DB: {e}")

    print("\n--- OLD Collection (spam_rag_intent) ---")
    try:
        col_old = client.get_collection("spam_rag_intent")
        print(f"Count: {col_old.count()}")
        
        results = col_old.get()
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        
        found = False
        target = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
        
        for d, m in zip(docs, metas):
            orig = m.get("original_message", "")
            if target in orig or target in d:
                print(f"FOUND in old DB!")
                print(f"Summary: {d}")
                print(f"Meta: {m}")
                found = True
                break
                
        if not found:
            print(f"NOT FOUND in old DB!")
            
    except Exception as e:
        print(f"Error accessing old DB: {e}")

if __name__ == '__main__':
    main()
