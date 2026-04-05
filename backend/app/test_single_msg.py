import asyncio
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.logging_config import setup_logging
from app.agents.content_agent.agent import ContentAnalysisAgent
from app.agents.ibse_agent.service import IBSEAgentService
from dotenv import load_dotenv

async def fp_sentinel_logic(c_res, i_res):
    res_str = "\n--- Running Finalizer Logic ---\n"
    is_spam = c_res.get("is_spam", False)
    reason = c_res.get("reason", "")
    code = c_res.get("classification_code")
    ibse_sig = i_res.get("signature") if i_res else None

    if is_spam:
        res_str += " -> Hit Rulset 2: Type_A (Pure Spam)\n"
        semantic_class = "Type_A"
        learning_label = "SPAM"
    else:
        res_str += " -> Hit Rulset 3: Ham\n"
        semantic_class = "Ham"
        learning_label = "HAM"
        ibse_sig = None
        
    res_str += f"\n[FINAL] Spam: {is_spam}\n"
    res_str += f"[FINAL] Class: {semantic_class}\n"
    res_str += f"[FINAL] Code: {code}\n"
    res_str += f"[FINAL] Label: {learning_label}\n"
    res_str += f"[FINAL] Sig: {ibse_sig}\n"
    res_str += f"[FINAL] Reason: {reason}\n"
    return res_str
    

async def test_message():
    load_dotenv(".env")
    setup_logging()
    
    import logging
    logging.getLogger("content_agent").setLevel(logging.CRITICAL)
    logging.getLogger("url_agent").setLevel(logging.CRITICAL)
    logging.getLogger("ibse_agent").setLevel(logging.CRITICAL)
    logging.getLogger("google_genai").setLevel(logging.CRITICAL)
    logging.getLogger("langgraph").setLevel(logging.CRITICAL)

    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:])
    else:
        msg = "(광고) 컨디션 좋고, 새로운 가게 이사 완료했습니다! -강남 광수- 무료수신거부 080-888-8489"
    msg_id = "test_msg_001"
    
    out_str = "\n" + "="*50 + "\n"
    out_str += f"Testing Message MANUALLY: {msg}\n"
    out_str += "="*50 + "\n\n"
    
    out_str += "1. Running Content Node directly...\n"
    cat = ContentAnalysisAgent()
    c_res = await cat.acheck(msg, {"pre_parsed_url": None})
    out_str += f"  -> Content Spam: {c_res.get('is_spam')}, Impersonation: {c_res.get('is_impersonation')}, Vague CTA: {c_res.get('is_vague_cta')}\n"
    out_str += f"  -> Reason: {c_res.get('reason')}\n"
    
    out_str += "\n2. Running IBSE Node directly...\n"
    ibse_agent = IBSEAgentService()
    i_res = await ibse_agent.process_message(msg, msg_id)
    out_str += f"  -> IBSE Decision: {i_res.get('decision')}, Sig: {i_res.get('signature')}\n"
    
    out_str += await fp_sentinel_logic(c_res, i_res)
    
    with open("test_results_clean.txt", "w", encoding="utf-8") as f:
        f.write(out_str)
        
    print("FINISHED WRITING test_results_clean.txt")

if __name__ == "__main__":
    asyncio.run(test_message())
