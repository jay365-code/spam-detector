import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

print(f"Loaded Key: {api_key[:8]}...****")

def run_tests():
    try:
        client = OpenAI(api_key=api_key)
        
        # 1. Models List
        print("\n1. [TEST] Models List")
        # .with_raw_response.list()
        response = client.models.with_raw_response.list()
        print(f"   -> HTTP Status: {response.http_response.status_code}")
        print("   -> Success (Connection OK)")

        # 2. Responses API (Requested by User)
        print("\n2. [TEST] Responses API (client.responses.create)")
        model_name = os.getenv("LLM_MODEL", "gpt-5-mini")
        print(f"   -> Using Model: {model_name}")
        
        try:
            response = client.responses.create(
                model=model_name,
                input="hi"
            )
            
            print("   -> Success (Responses API worked)")
            print(f"   -> Output: {response.output_text}")
            
        except Exception as e:
            print(f"   -> Failed: {e}")
            
    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")

if __name__ == "__main__":
    run_tests()
