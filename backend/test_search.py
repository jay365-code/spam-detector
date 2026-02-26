import os
from dotenv import load_dotenv

load_dotenv(override=True)

from langchain_openai import OpenAIEmbeddings
import chromadb
import sys

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(project_root, "data", "chroma_db")
    
    # The user query
    query_text = "ㅈㅣ속적인 연락두절은 ㅅㅏ기 지유신"
    
    # Initialize embeddings
    emb_3_small = OpenAIEmbeddings(model="text-embedding-3-small")
    emb_ada = OpenAIEmbeddings(model="text-embedding-ada-002")
    
    # What would be the intent summary for this? Let's just use the query itself for this test, as if it was the summary
    # Or ideally, we search using the exact summary in the DB
    target_summary = "Fraud Accusation / Bypassing spam filters using decomposed characters / Warning that persistent loss of contact is evidence of a scam."
    
    client = chromadb.PersistentClient(path=db_path)
    
    print("\n=== NEW DB (spam_rag_intent_v2) with 3-small ===")
    col_new = client.get_collection("spam_rag_intent_v2")
    vec_3 = emb_3_small.embed_query(target_summary)
    
    res = col_new.query(query_embeddings=[vec_3], n_results=3, include=["documents", "metadatas", "distances"])
    for i in range(len(res["ids"][0])):
        dist = res["distances"][0][i]
        doc = res["documents"][0][i]
        print(f"[{i}] Distance: {dist:.4f} | Doc: {doc[:80]}")

    print("\n=== OLD DB (spam_rag_intent) with ada-002 ===")
    col_old = client.get_collection("spam_rag_intent")
    vec_ada = emb_ada.embed_query(target_summary)
    
    res = col_old.query(query_embeddings=[vec_ada], n_results=3, include=["documents", "metadatas", "distances"])
    for i in range(len(res["ids"][0])):
        dist = res["distances"][0][i]
        doc = res["documents"][0][i]
        print(f"[{i}] Distance: {dist:.4f} | Doc: {doc[:80]}")

if __name__ == '__main__':
    main()
