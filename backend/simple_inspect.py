import chromadb
import os

def run():
    db_path = "data/chroma_db"
    if not os.path.exists(db_path):
        print(f"Error: Path {db_path} does not exist.")
        return

    client = chromadb.PersistentClient(path=db_path)
    print(f"Collections: {client.list_collections()}")
    
    collection = client.get_collection("fn_examples")
    count = collection.count()
    print(f"Total count in 'fn_examples': {count}")
    
    # Peek at some documents
    results = collection.peek(limit=10)
    print("\n--- Peek at first 10 documents ---")
    for i in range(len(results['ids'])):
        print(f"ID: {results['ids'][i]}")
        content = results['documents'][i]
        # repr()로 숨겨진 문자 확인
        print(f"Content (repr): {repr(content[:150])}...")
        print(f"Content length: {len(content)}")
        print(f"Metadata: {results['metadatas'][i]}")
        print("-" * 40)

if __name__ == "__main__":
    run()
