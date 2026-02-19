import chromadb
import os
from chromadb.config import Settings

def reset_chroma_db():
    # Define path relative to this script (.../backend/reset_db.py)
    # We want .../data/chroma_db (Project Root)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, "data", "chroma_db")
    
    print(f"Target ChromaDB Path: {db_path}")
    
    if os.path.exists(db_path):
        response = input(f"Warning: This will DELETE ALL DATA (Collections) in '{db_path}'.\nArc you sure? (y/n): ")
        if response.lower() == 'y':
            try:
                # connect to the database
                client = chromadb.PersistentClient(path=db_path)
                
                # List all collections
                collections = client.list_collections()
                
                if not collections:
                    print("No collections found in the database.")
                    return

                print(f"Found {len(collections)} collections: {[c.name for c in collections]}")
                
                # Delete each collection
                for collection in collections:
                    print(f"Deleting collection: {collection.name}...")
                    client.delete_collection(collection.name)
                
                print("✅ Successfully cleared all data from ChromaDB.")
                
            except Exception as e:
                print(f"❌ Error clearing data: {e}")
                print("Tip: If you see a locking error, please STOP the server and try again.")
        else:
            print("Operation cancelled.")
    else:
        print("⚠️ Path does not exist. Nothing to delete.")

if __name__ == "__main__":
    reset_chroma_db()
