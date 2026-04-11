import logging
from typing import Literal

from langgraph.graph import StateGraph, END

from app.agents.ibse_agent.state import IBSEState
from app.agents.ibse_agent.candidate import generate_candidates_node
from app.agents.ibse_agent.selector import select_signature_node
from app.agents.ibse_agent.validator import validate_node

logger = logging.getLogger(__name__)

def should_continue(state: IBSEState) -> Literal["retry", "end"]:
    """
    Decide whether to retry (repair) or end.
    """
    error = state.get("error")
    final_result = state.get("final_result", {})
    decision = final_result.get("decision") if final_result else None
    retry_count = state.get("retry_count", 0)
    
    if not error:
        return "end"
        
    # Do not retry at graph level if API failed or max retries were exceeded
    if decision == "unextractable":
        logger.warning(f"IBSE skipping graph retry due to unextractable decision or API error: {error}")
        return "end"
    
    # If error exists, gracefully end without graph-level retries (1 model, 1 execution rule)
    if error:
        logger.warning(f"IBSE Validation Failed with error: {error}. Graph retry is disabled. Ending.")
        return "end"

    return "end"

def update_retry_count(state: IBSEState):
    """
    Simple node to increment retry count before retrying.
    """
    return {"retry_count": state.get("retry_count", 0) + 1}

# --- Graph Definition ---
workflow = StateGraph(IBSEState)

# Add Nodes (Bypass candidate generation)
workflow.add_node("extract_signature", select_signature_node)
workflow.add_node("validate", validate_node)
workflow.add_node("increment_retry", update_retry_count)

# Set Entry Point
workflow.set_entry_point("extract_signature")

# Add Edges
workflow.add_edge("extract_signature", "validate")

# Conditional Edge from Validate
workflow.add_conditional_edges(
    "validate",
    should_continue,
    {
        "retry": "increment_retry",
        "end": END
    }
)

# Edge from Retry back to Select
workflow.add_edge("increment_retry", "extract_signature")

# Compile
ibse_graph = workflow.compile()
