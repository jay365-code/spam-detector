
print("Debug: Starting ContentAnalysisAgent imports...")

try:
    print("Debug: Importing Chroma...")
    from langchain_community.vectorstores import Chroma
    print("Debug: Chroma OK!")
except Exception as e:
    print(f"Debug: Chroma Error: {e}")

try:
    print("Debug: Importing OpenAIEmbeddings...")
    from langchain_openai import OpenAIEmbeddings
    print("Debug: OpenAIEmbeddings OK!")
except Exception as e:
    print(f"Debug: OpenAIEmbeddings Error: {e}")

try:
    print("Debug: Importing ChatOpenAI...")
    from langchain_openai import ChatOpenAI
    print("Debug: ChatOpenAI OK!")
except Exception as e:
    print(f"Debug: ChatOpenAI Error: {e}")

print("Debug: All content agent imports done.")
