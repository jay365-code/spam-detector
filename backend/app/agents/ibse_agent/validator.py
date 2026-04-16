from .state import IBSEState
from .utils import get_cp949_byte_len

class Validator:
    def validate(self, text_context: str, result: dict) -> dict:
        decision = result.get("decision")
        signature = result.get("signature")
        
        if decision == "unextractable":
            return result
        
        allowed_decisions = ["use_string", "use_sentence", "unextractable"]
        if decision not in allowed_decisions:
            return {**result, "error": f"Invalid decision: '{decision}'. Must be one of {allowed_decisions}."}
        
        if not signature:
            return {**result, "error": "Signature is empty but decision is not unextractable"}
        
        # 1. Exact Match Check (No Hallucination!)
        if signature not in text_context:
            return {**result, "error": "Strict extraction failed. The extracted signature does NOT exist exactly within the original message text."}
            
        # 2. URL Substring Check (Prevent Domain-only extraction)
        import re
        url_pattern = r'(?:(?:https?://)|(?:www\.))?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-zA-Z]{2,6}\b(?:[-a-zA-Z0-9@:%_\+.~#?&//=]*)'
        urls_in_text = list(re.finditer(url_pattern, text_context))
        
        sig_start = text_context.find(signature)
        if sig_start != -1:
            sig_end = sig_start + len(signature)
            for url_match in urls_in_text:
                u_start = url_match.start()
                u_end = url_match.end()
                
                # Check if the signature is ENTIRELY contained within the URL
                if sig_start >= u_start and sig_end <= u_end:
                    from urllib.parse import urlparse
                    url_str = signature if signature.startswith("http") else "http://" + signature
                    parsed = urlparse(url_str)
                    
                    # 패스(Path)나 쿼리 파라미터(Query) 없이 루트 도메인 껍데기만 남은 경우 차단
                    if (not parsed.path or parsed.path == '/') and not parsed.query:
                        return {**result, "error": f"루트 도메인 껍데기만 단독으로 추출하는 것은 금지됩니다. 주변 악성 문구를 포함하거나 포기(unextractable)하세요. 단, 고유 Path나 쿼리 파라미터가 있는 특수/단축 주소는 단독 추출이 허용됩니다. (추출된: {signature})"}
                    else:
                        # 고유 Path(`/xyz123`)나 Query(`?id=`)가 포함되어 있으므로 단독 추출 승인 (Pass)
                        pass
                        
        # 3. Blacklist Check
        blacklist = ["광고", "(광고)", "[광고]", "080-", "무료거부", "수신거부", "무료수신거부"]
        for b in blacklist:
            if b in signature:
                return {**result, "error": f"Signature contains blacklisted word: {b}"}
                
        # 4. Byte Length constraints
        byte_len = get_cp949_byte_len(signature)
             
        if byte_len < 9:
             return {**result, "error": f"Signature is too short ({byte_len} bytes). Must be at least 9 bytes."}
             
        if decision == "use_string" and (byte_len < 9 or byte_len > 20):
             return {**result, "error": f"Decision is use_string but length is {byte_len} bytes. Should be between 9 and 20."}
             
        if decision == "use_sentence":
             if byte_len < 39 or byte_len > 40:
                  return {**result, "error": f"Decision is use_sentence but length is {byte_len} bytes. Should be exactly 39 or 40 bytes. (If the original text is too short, you must use use_string or unextractable instead.)"}
             
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
