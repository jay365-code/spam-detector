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

    # 1. Clear existing DB to prevent duplicates
    if os.path.exists(db_path):
        print(f"Cleaning persistent directory: {db_path}...")
        shutil.rmtree(db_path)

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
    # Consistent Model: text-embedding-ada-002
    print("Creating Vector DB (using OpenAI Embeddings: text-embedding-ada-002)...")
    embedding_function = OpenAIEmbeddings(model="text-embedding-ada-002")
    
    db = Chroma.from_documents(
        documents=docs, 
        embedding=embedding_function, 
        persist_directory=db_path,
        collection_name="spam_guide"
    )
    
    print(f"Successfully ingested data into {db_path}")

if __name__ == "__main__":
    ingest_data()
