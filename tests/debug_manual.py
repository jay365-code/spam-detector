
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

load_dotenv(override=True)

from app.core.logging_config import setup_logging
setup_logging()

from app.agents.content_agent.agent import ContentAnalysisAgent

async def main():
    agent = ContentAnalysisAgent()
    
    # Message from the text file
    message = "A 77 muⓩ.so/anicsn016a"
    print(f"--- Processing Message: {message} ---")
    
    # Stage 1 dummy result (Content Agent needs s1_result usually, or we can pass minimal)
    s1_result = {
        "is_spam": None,
        "decoded_text": message, # Assuming no obfuscation for this simple test, or passing as is
        "detected_pattern": "URL Pattern"
    }

    # Run check
    # We use acheck for async
    result = await agent.acheck(message, s1_result)
    
    print("\n--- Final Result ---")
    print(result)

    # Also generate final summary
    summary = await agent.generate_final_summary(message, result, url_result=None)
    print("\n--- Final Summary (LLM) ---")
    print(summary)

if __name__ == "__main__":
    asyncio.run(main())
