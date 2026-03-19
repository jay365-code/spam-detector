import os

# Read selector.py
selector_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\backend\app\agents\ibse_agent\selector.py'
with open(selector_path, 'r', encoding='utf-8') as f:
    selector_code = f.read()

# Post-processing injection for selector.py
truncation_code = """
    # Update byte_len natively and Truncate safely for CP949
    if "signature" in result and result["signature"] and result.get("decision") in ["use_string", "use_sentence"]:
        max_bytes = 20 if result["decision"] == "use_string" else 40
        sig_text = result["signature"]
        
        # Safely truncate CP949
        encoded = sig_text.encode("cp949", errors="replace")
        if len(encoded) > max_bytes:
            truncated = encoded[:max_bytes]
            while len(truncated) > 0:
                try:
                    sig_text = truncated.decode("cp949", errors="strict")
                    break
                except UnicodeDecodeError:
                    truncated = truncated[:-1]
            result["signature"] = sig_text
            
        try:
            result["byte_len_cp949"] = len(result["signature"].encode("cp949"))
        except:
             result["byte_len_cp949"] = len(result["signature"]) * 2

    return {
        "final_result": result,
        "extracted_signature": result.get("signature"),
        "extraction_type": result.get("decision"),
        "error": result.get("error")
    }
"""

selector_code = selector_code.replace('''    # Update byte_len natively
    if "signature" in result and result["signature"]:
        try:
            result["byte_len_cp949"] = len(result["signature"].encode("cp949"))
        except:
             result["byte_len_cp949"] = len(result["signature"]) * 2

    return {
        "final_result": result,
        "extracted_signature": result.get("signature"),
        "extraction_type": result.get("decision"),
        "error": result.get("error")
    }''', truncation_code.strip())

with open(selector_path, 'w', encoding='utf-8') as f:
    f.write(selector_code)

# Update validator.py
validator_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\backend\app\agents\ibse_agent\validator.py'
with open(validator_path, 'r', encoding='utf-8') as f:
    validator_code = f.read()

validator_code = validator_code.replace('''        if decision == "use_string" and byte_len > 25:
             # Allowed up to 25 to give tiny flexibility, but flag error if too long
             return {**result, "error": f"Decision is use_string but length is {byte_len} bytes. Should be <= 20."}
             
        if decision == "use_sentence" and byte_len > 45:
             return {**result, "error": f"Decision is use_sentence but length is {byte_len} bytes. Should be <= 40."}''', 
'''        if decision == "use_string" and byte_len > 20:
             return {**result, "error": f"Decision is use_string but length is {byte_len} bytes. Should be <= 20."}
             
        if decision == "use_sentence" and byte_len > 40:
             return {**result, "error": f"Decision is use_sentence but length is {byte_len} bytes. Should be <= 40."}''')

with open(validator_path, 'w', encoding='utf-8') as f:
    f.write(validator_code)
