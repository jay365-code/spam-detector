from .state import IBSEState
from .utils import get_cp949_byte_len

class Validator:
    def validate(self, text_context: str, result: dict) -> dict:
        decision = result.get("decision")
        signature = result.get("signature")
        
        if decision == "unextractable":
            return result
        
        if not signature:
            return {**result, "error": "Signature is empty but decision is not unextractable"}
        
        # 1. Exact Match Check (No Hallucination!)
        if signature not in text_context:
            return {**result, "error": "Strict extraction failed. The extracted signature does NOT exist exactly within the original message text."}
            

            
        # 3. Blacklist Check
        blacklist = ["광고", "(광고)", "[광고]", "080-", "무료거부", "수신거부", "무료수신거부"]
        for b in blacklist:
            if b in signature:
                return {**result, "error": f"Signature contains blacklisted word: {b}"}
                
        # 4. Byte Length constraints
        byte_len = get_cp949_byte_len(signature)
        if byte_len == -1: # Fallback calculation if encoding fails
             byte_len = len(signature) * 2
             
        if byte_len < 9:
             return {**result, "error": f"Signature is too short ({byte_len} bytes). Must be at least 9 bytes."}
             
        if decision == "use_string" and (byte_len < 9 or byte_len > 20):
             return {**result, "error": f"Decision is use_string but length is {byte_len} bytes. Should be between 9 and 20."}
             
        if decision == "use_sentence":
             # 원본 메시지가 39바이트보다 짧은 특수 상황이 아닌 이상, 39~40을 엄격히 시킴
             full_msg_len = get_cp949_byte_len(text_context)
             if full_msg_len == -1: full_msg_len = len(text_context) * 2
             
             if full_msg_len >= 39:
                 if byte_len < 39 or byte_len > 40:
                      return {**result, "error": f"Decision is use_sentence but length is {byte_len} bytes. Should be exactly 39 or 40 bytes."}
             else:
                 if byte_len != full_msg_len:
                      return {**result, "error": f"Decision is use_sentence on a short message. Length {byte_len} must match full message length {full_msg_len}."}
             
        return result

def validate_node(state: IBSEState) -> dict:
    match_text = state.get("match_text", "")
    final_result = state.get("final_result")
    
    if not final_result:
        return {"error": "No final_result to validate"}
    
    validator = Validator()
    validated_result = validator.validate(match_text, final_result)
    
    state_update = {"final_result": validated_result}
    if "error" in validated_result:
         state_update["error"] = validated_result["error"]
    else:
         state_update["error"] = None
         
    return state_update
