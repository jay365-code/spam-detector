from .state import IBSEState
from .utils import get_cp949_byte_len

class Validator:
    def validate(self, text_context: str, result: dict) -> dict:
        """
        Validates the LLM signature selection result.
        Returns the result with 'error' field if validation fails.
        """
        decision = result.get("decision")
        signature = result.get("signature")
        start_idx = result.get("start_idx")
        end_idx = result.get("end_idx_exclusive")
        
        # 0. Safety Checks
        if decision == "unextractable":
            return result
        
        if not signature:
            return {**result, "error": "Signature is empty but decision is use_20/40"}
        
        # 1. Inclusion Check
        if signature not in text_context:
            return {**result, "error": "Signature not found in original text context"}
        
        # 2. Byte Length Check
        byte_len = get_cp949_byte_len(signature)
        if byte_len == -1:
             return {**result, "error": "Signature contains invalid CP949 characters"}
        
        if decision == "use_20" and byte_len > 20:
             return {**result, "error": f"Decision is use_20 but byte_len is {byte_len}"}
        
        if decision == "use_40" and byte_len > 40:
             return {**result, "error": f"Decision is use_40 but byte_len is {byte_len}"}
             
        # Validation Passed
        return result

def validate_node(state: IBSEState) -> dict:
    original_text = state.get("original_text", "")
    final_result = state.get("final_result") # JSON output from Selector
    
    if not final_result:
        return {"error": "No final_result to validate"}
    
    validator = Validator()
    # Validate against ORIGINAL text to ensure whitespace preservation
    validated_result = validator.validate(original_text, final_result)
    
    state_update = {
        "final_result": validated_result
    }
    
    # Check if error was added
    if "error" in validated_result:
         state_update["error"] = validated_result["error"]
         
         # Logic for Repair Loop in Runner
         # If this is the first time failing, we might want to trigger retry.
         # But the node just updates state. The runner decides flow.
    else:
         # Validation success, clear error
         state_update["error"] = None
         
    return state_update
