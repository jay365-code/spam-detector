import os
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=".env", override=True)

def inspect_chroma_db():
    db_path = "data/chroma_db"
    
    if not os.path.exists(db_path):
        print(f"Error: DB path not found at {db_path}")
        return

    print(f"Loading Vector DB from {db_path}...")
    
    # Must use the SAME embedding model as ingest
    embedding_function = OpenAIEmbeddings(model="text-embedding-ada-002")
    
    db = Chroma(
        persist_directory=db_path,
        embedding_function=embedding_function,
        collection_name="spam_guide"
    )
    
    # 1. Get Count
    try:
        # Accessing internal collection to get stats
        collection_count = db._collection.count()
        print(f"\n[Stats] Total Chunks Stored: {collection_count}")
        
        # 2. Peek Data (Get first 3 items)
        print("\n[Sample Data - Top 3]")
        # Explicitly include 'embeddings' in the retrieval
        data = db._collection.get(limit=5, include=['documents', 'metadatas', 'embeddings'])
        
        print(f"\n[Debug] Keys returned from DB: {list(data.keys())}")
        
        if data.get('embeddings') is None:
             print("[Debug] 'embeddings' key is None!")
        elif len(data['embeddings']) == 0:
             print("[Debug] 'embeddings' list is empty!")
        else:
             print(f"[Debug] Found {len(data['embeddings'])} embeddings.")

        for i, text in enumerate(data['documents']):
            print(f"\n--- Chunk {i+1} ---")
            print(f"[Text]: {text[:100]}..." if len(text) > 100 else f"[Text]: {text}") 
            
            # Print Vector preview
            if data.get('embeddings') is not None and len(data['embeddings']) > i:
                vector = data['embeddings'][i]
                print(f"[Vector Type]: {type(vector)}")
                print(f"[Vector Size]: {len(vector)}")
                print(f"[Vector Preview]: {vector[:5]} ... (total 1536 dims)")
            else:
                print("[Vector]: Not available")

    except Exception as e:
        print(f"Error inspecting DB: {e}")

if __name__ == "__main__":
    inspect_chroma_db()
