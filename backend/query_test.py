from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
import os

# Load .env
load_dotenv(dotenv_path=".env")

def test_query():
    db_path = "data/chroma_db"
    
    if not os.path.exists(db_path):
        print(f"Error: DB not found at {db_path}. Run ingest.py first.")
        return

    print("Connecting to Vector DB...")
    embedding_function = OpenAIEmbeddings()
    db = Chroma(
        persist_directory=db_path, 
        embedding_function=embedding_function,
        collection_name="spam_guide"
    )

    query = input("검색할 내용을 입력하세요 (예: 대출): ") or "대출"
    print(f"\nSearching for: '{query}'...\n")

    results = db.similarity_search(query, k=3)

    if not results:
        print("No results found.")
    else:
        for i, doc in enumerate(results):
            print(f"--- Result {i+1} ---")
            print(doc.page_content)
            print("------------------\n")

if __name__ == "__main__":
    test_query()
