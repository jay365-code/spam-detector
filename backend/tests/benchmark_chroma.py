import time
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def benchmark():
    print("--- Benchmark Start ---", flush=True)
    
    start_total = time.time()
    
    print("Importing openai...", end=" ", flush=True)
    s = time.time()
    import openai
    print(f"Done ({time.time() - s:.4f}s)", flush=True)

    print("Importing tiktoken...", end=" ", flush=True)
    s = time.time()
    import tiktoken
    print(f"Done ({time.time() - s:.4f}s)", flush=True)

    print("Importing langchain_core...", end=" ", flush=True)
    s = time.time()
    import langchain_core
    print(f"Done ({time.time() - s:.4f}s)", flush=True)

    print("Importing langchain_openai...", end=" ", flush=True)
    s = time.time()
    from langchain_openai import OpenAIEmbeddings
    print(f"Done ({time.time() - s:.4f}s)", flush=True)

    print("Importing langchain_chroma...", end=" ", flush=True)
    s = time.time()
    from langchain_chroma import Chroma
    print(f"Done ({time.time() - s:.4f}s)", flush=True)

    print(f"--- Benchmark End (Total: {time.time() - start_total:.4f}s) ---", flush=True)

if __name__ == "__main__":
    benchmark()
