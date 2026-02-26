import os
import shutil
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

# Load environment variables (Override system variables)
load_dotenv(dotenv_path=".env", override=True)

def ingest_data():
    file_path = "data/spam_guide.md"
    db_path = "data/chroma_db"
    
    # Check API Key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is missing in .env")
        return
    print(os.getenv("OPENAI_API_KEY"))
    
    if not os.path.exists(file_path):
        print(f"Error: Guide file not found at {file_path}")
        return

    # 1. Safer Reset: Only delete 'spam_guide' collection
    # Do NOT delete the entire directory, as it deletes 'fn_examples' too.
    print(f"Connecting to ChromaDB at {db_path}...")
    # Initialize Persistent Client
    import chromadb
    client = chromadb.PersistentClient(path=db_path)
    
    try:
        # Check if collection exists and delete it
        collections = client.list_collections()
        collection_names = [c.name for c in collections]
        
        if "spam_guide" in collection_names:
            print("Deleting existing 'spam_guide' collection...")
            client.delete_collection("spam_guide")
        else:
            print("'spam_guide' collection does not exist, creating new...")
            
    except Exception as e:
        print(f"Error resetting collection: {e}")
        # Fallback (safety): If completely broken, maybe warn user?
        # But we continue to try creating it.

    print(f"Loading data from {file_path}...")
    loader = TextLoader(file_path, encoding='utf-8')
    documents = loader.load()

    # 2. Key Improvement: Recursive Splitting
    # Respects sentences/paragraphs better than simple char splitting
    print("Splitting text...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    docs = text_splitter.split_documents(documents)
    print(f"Split into {len(docs)} chunks.")

    # 3. Create Chroma Vector Store
    # Consistent Model: text-embedding-3-small
    print("Creating Vector DB (using OpenAI Embeddings: text-embedding-3-small)...")
    embedding_function = OpenAIEmbeddings(model="text-embedding-3-small")
    
    db = Chroma.from_documents(
        documents=docs, 
        embedding=embedding_function, 
        persist_directory=db_path,
        collection_name="spam_guide"
    )
    
    print(f"Successfully ingested data into {db_path}")

if __name__ == "__main__":
    ingest_data()
