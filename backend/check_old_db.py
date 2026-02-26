import os
import chromadb

def check_encoding_old_db():
    project_root = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(project_root, "data", "chroma_db")
    
    print(f"DB Path: {db_path}")

    client = chromadb.PersistentClient(path=db_path)
    
    # 1. Check old collection
    print("\n--- OLD Collection (spam_rag_intent) ---")
    try:
        col_old = client.get_collection("spam_rag_intent")
        
        results = col_old.get()
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        
        target = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
        
        for d, m in zip(docs, metas):
            orig = m.get("original_message", "")
            # Since orig might be corrupted in python print but fine in DB, let's encode/decode
            
            # Simple check
            if target in str(orig) or target in str(d):
                print("Found target directly!")
                print(f"Meta: {m}")
            elif "" in orig: # Has replacement character
                # Let's see if we can find it by intent
                if "Fraud Accusation / Bypassing" in d:
                    print("Found by document intent but text uses replacement chars:")
                    print(f"Raw string rep: {repr(orig)}")
                    
    except Exception as e:
        print(f"Error accessing old DB: {e}")

if __name__ == '__main__':
    check_encoding_old_db()
