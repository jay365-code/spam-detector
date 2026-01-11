import os
import sys
import json
import logging

# Add project root to path to allow imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
sys.path.append(os.path.join(project_root, "backend"))

from app.agents.ibse_agent.utils import preprocess_text
from app.agents.ibse_agent.candidate import generate_candidates_node
from app.agents.ibse_agent.selector import select_signature_node
from app.agents.ibse_agent.validator import validate_node
from app.agents.ibse_agent.state import IBSEState

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("IBSE_Runner")

SAMPLES = [
    {
        "id": "test_01",
        "text": "(광고)삼성전자 특별공급 1차오픈! 수익률 보장 010-1234-5678 무료거부 080-123-4567"
    },
    {
        "id": "test_02",
        "text": "안녕하세요. 즐거운 하루 보내세요. 별다른 내용은 없습니다."
    },
    {
        "id": "test_03_cp949_limit",
        "text": "(광고)매우긴텍스트입니다이것은20바이트를넘어가는텍스트이며40바이트테스트를위한것입니다무료거부080"
    }
]

def run_pipeline(message_id: str, text: str):
    logger.info(f"--- Processing {message_id} ---")
    logger.info(f"Original Text: {text}")
    
    # 1. State Initialization & Preprocessing
    match_text = preprocess_text(text)
    state: IBSEState = {
        "message_id": message_id,
        "original_text": text,
        "match_text": match_text,
        "candidates_20": [],
        "candidates_40": [],
        "selected_decision": None,
        "selected_candidate": None,
        "final_result": None,
        "retry_count": 0,
        "error": None
    }
    
    # 2. Candidate Generation
    logger.info("[Step 1] Generating Candidates...")
    gen_result = generate_candidates_node(state)
    state.update(gen_result)
    logger.info(f"Generated {len(state['candidates_20'])} (20byte) / {len(state['candidates_40'])} (40byte) candidates")
    
    # 3. Selection (Round 1)
    logger.info("[Step 2] Selecting Signature (Round 1)...")
    sel_result = select_signature_node(state)
    state.update(sel_result)
    logger.info(f"Round 1 Result: {json.dumps(state['final_result'], ensure_ascii=False)}")
    
    # 4. Validation
    logger.info("[Step 3] Validating...")
    val_result = validate_node(state)
    state.update(val_result)
    
    # 5. Repair Loop (if failure)
    if state.get("error"):
        logger.warning(f"Validation Failed: {state['error']}. Retrying (Repair Mode)...")
        state["retry_count"] += 1
        
        # Repair Selection (Round 2)
        # select_signature_node detects 'error' in state and uses Repair Prompt
        sel_result = select_signature_node(state)
        state.update(sel_result)
        logger.info(f"Round 2 (Repair) Result: {json.dumps(state['final_result'], ensure_ascii=False)}")
        
        # Repair Validation
        val_result = validate_node(state)
        state.update(val_result)
        
        if state.get("error"):
             logger.error(f"Final Validation Failed after Repair: {state['error']}")
        else:
             logger.info("Repair Successful!")
             
    else:
        logger.info("Validation Passed directly.")

    # Final Output
    print(f"\n[{message_id}] Final Decision: {state['final_result'].get('decision')}")
    print(f"Signature: {state['final_result'].get('signature')}")
    print(f"Reason: {state['final_result'].get('reason')}\n")

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GEMINI_API_KEY"):
         logger.warning("API Keys not found in env. Attempting to load from backend/.env")
         from dotenv import load_dotenv
         env_path = os.path.join(project_root, "backend", ".env")
         load_dotenv(env_path)
         logger.info(f"Loaded .env from {env_path}")
    
    for sample in SAMPLES:
        run_pipeline(sample["id"], sample["text"])
