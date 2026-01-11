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
    retry_count = state.get("retry_count", 0)
    
    # If error exists and we haven't retried yet (max 1 retry)
    if error and retry_count < 1:
        logger.info(f"IBSE Validation Failed (Attempt {retry_count + 1}). Retrying...")
        return "retry"
    
    return "end"

def update_retry_count(state: IBSEState):
    """
    Simple node to increment retry count before retrying.
    """
    return {"retry_count": state.get("retry_count", 0) + 1}

# --- Graph Definition ---
workflow = StateGraph(IBSEState)

# Add Nodes
workflow.add_node("generate_candidates", generate_candidates_node)
workflow.add_node("select_signature", select_signature_node)
workflow.add_node("validate", validate_node)
workflow.add_node("increment_retry", update_retry_count)

# Set Entry Point
workflow.set_entry_point("generate_candidates")

# Add Edges
workflow.add_edge("generate_candidates", "select_signature")
workflow.add_edge("select_signature", "validate")

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
workflow.add_edge("increment_retry", "select_signature")

# Compile
ibse_graph = workflow.compile()
