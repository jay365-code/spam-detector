import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load .env explicitly
load_dotenv("backend/.env")

api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("LLM_MODEL", "gemini-1.5-flash")

print(f"DEBUG: API Key present? {bool(api_key)}")
print(f"DEBUG: Model Name: {model_name}")

if not api_key:
    print("ERROR: No API Key found.")
    exit(1)

try:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    print("DEBUG: Sending request...")
    response = model.generate_content("Hello, simply say 'Hi'.")
    
    print("\n--- Response Inspection ---")
    print(f"Type: {type(response)}")
    print(f"Has usage_metadata? {hasattr(response, 'usage_metadata')}")
    
    if hasattr(response, 'usage_metadata'):
        print(f"usage_metadata: {response.usage_metadata}")
        # Try to inspect usage_metadata fields
        try:
            print(f"prompt_token_count: {response.usage_metadata.prompt_token_count}")
        except Exception as e:
            print(f"Error accessing prompt_token_count: {e}")
            
        try:
            print(f"candidates_token_count: {response.usage_metadata.candidates_token_count}")
        except Exception as e:
            print(f"Error accessing candidates_token_count: {e}")
            
    else:
        print("usage_metadata attribute NOT found.")
        print("Dir(response):", dir(response))
        
    print("\n--- Text Content ---")
    print(response.text)

except Exception as e:
    print(f"CRITICAL ERROR: {e}")
