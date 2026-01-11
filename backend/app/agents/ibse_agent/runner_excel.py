import os
import sys
import pandas as pd
import logging
from tqdm import tqdm
import unicodedata

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../../"))
sys.path.append(os.path.join(project_root, "backend"))

# Load Env
from dotenv import load_dotenv
env_path = os.path.join(project_root, "backend", ".env")
load_dotenv(env_path)

from app.agents.ibse_agent.utils import preprocess_text
from app.agents.ibse_agent.candidate import generate_candidates_node
from app.agents.ibse_agent.selector import select_signature_node
from app.agents.ibse_agent.validator import validate_node
from app.agents.ibse_agent.state import IBSEState

# Logging
logging.basicConfig(level=logging.WARNING) # Reduce logs for batch
logger = logging.getLogger("IBSE_Excel")
logger.setLevel(logging.INFO)

def process_text(message_id: str, text: str):
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
        
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
    
    # Pipeline
    try:
        gen_res = generate_candidates_node(state)
        state.update(gen_res)
        
        sel_res = select_signature_node(state)
        state.update(sel_res)
        
        val_res = validate_node(state)
        state.update(val_res)
        
        # Repair
        if state.get("error"):
            state["retry_count"] += 1
            # Retry Selection
            sel_res = select_signature_node(state)
            state.update(sel_res)
            # Retry Validation
            val_res = validate_node(state)
            state.update(val_res)
            
    except Exception as e:
        logger.error(f"Error processing {message_id}: {e}")
        return {
            "decision": "ERROR",
            "signature": "",
            "reason": str(e),
            "byte_len": 0
        }
            
    final = state.get("final_result", {}) or {}
    return {
        "decision": final.get("decision", "unknown"),
        "signature": final.get("signature", ""),
        "reason": final.get("reason", ""),
        "byte_len": final.get("byte_len_cp949", 0)
    }

def main():
    input_file = "sample_test.xlsx"
    input_path = os.path.join(project_root, input_file)
    
    if not os.path.exists(input_path):
        logger.error(f"File not found: {input_path}")
        return

    logger.info(f"Loading {input_path}...")
    df = pd.read_excel(input_path)
    
    target_col = "메시지"
    if target_col not in df.columns:
        # Fallback to 'message' or first column
        if "message" in df.columns: 
            target_col = "message"
        else:
            target_col = df.columns[0]
            logger.warning(f"'메시지' column not found. Using '{target_col}'")
            
    logger.info(f"Target Column: {target_col}")
    logger.info(f"Total Rows: {len(df)}")
    
    results = []
    
    # Process
    for idx, row in tqdm(df.iterrows(), total=len(df)):
        text = row[target_col]
        res = process_text(f"row_{idx}", text)
        results.append(res)
        
    # Append to DF
    df["IBSE_Decision"] = [r["decision"] for r in results]
    df["IBSE_Signature"] = [r["signature"] for r in results]
    df["IBSE_Reason"] = [r["reason"] for r in results]
    df["IBSE_ByteLen"] = [r["byte_len"] for r in results]
    
    output_file = input_file.replace(".xlsx", "_ibse_result.xlsx")
    output_path = os.path.join(project_root, output_file)
    
    df.to_excel(output_path, index=False)
    logger.info(f"Saved results to {output_path}")

if __name__ == "__main__":
    main()
