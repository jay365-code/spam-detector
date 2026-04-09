import asyncio
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()
from app.agents.ibse_agent.selector import LLMSelector, select_signature_node

logging.basicConfig(level=logging.INFO)

async def test_ibse():
    state1 = {
        "message_id": "test_1",
        "match_text": "(0ㅑ><마><)    탕탕탕~ <   `/,>      d111.",
        "obfuscated_urls": []
    }
    
    state2 = {
        "message_id": "test_2",
        "match_text": "(광고)#Happy All Day# 어제보다 편안하고 행복한 하루되세요~ *이.영.아* 무료거부 0808875572",
        "obfuscated_urls": []
    }

    test_states = [state1, state2]

    for state in test_states:
        print(f"\n======================")
        print(f"Testing MSG: {state['match_text']}")
        try:
            res = await select_signature_node(state)
            print(json.dumps(res, ensure_ascii=False, indent=2))
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test_ibse())
