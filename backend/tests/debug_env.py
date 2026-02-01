
import os
from dotenv import load_dotenv

load_dotenv(override=True)

print(f"LLM_PROVIDER: {os.getenv('LLM_PROVIDER')}")
print(f"LLM_MODEL: {os.getenv('LLM_MODEL')}")
print(f"OPENAI_API_KEY: {'Set' if os.getenv('OPENAI_API_KEY') else 'Not Set'}")
print(f"GEMINI_API_KEY: {'Set' if os.getenv('GEMINI_API_KEY') else 'Not Set'}")
print(f"CLAUDE_API_KEY: {'Set' if os.getenv('CLAUDE_API_KEY') else 'Not Set'}")
