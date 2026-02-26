import json
import re

def find_corrupted():
    with open("backend/all_rag_examples.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    examples = data.get('data', [])
    for ex in examples:
        msg = ex.get('message', '')
        intent = ex.get('intent_summary', '')
        reason = ex.get('reason', '')
        
        # Check if message is strangely short, empty, or lacks Hangul where it should have
        if len(msg) < 10 and ex.get('label') == 'SPAM':
            print(f"Suspicious by length: ID={ex['id']}, msg='{msg}', reason='{reason}'")
            
        # Or if it contains weird characters that are not ascii, not hangul, not common punctuation
        # Korean chars: \uAC00-\uD7A3, Jamo: \u1100-\u11FF, \u3130-\u318F
        def is_garbled(s):
            if not s: return False
            for char in s:
                code = ord(char)
                if code > 127 and not (0xAC00 <= code <= 0xD7A3) and not (0x3130 <= code <= 0x318F):
                    # Found a character that is outside ascii and outside standard Hangul blocks
                    if not re.match(r'[가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s.,!?\'"]', char):
                        return True
            return False

        if is_garbled(msg) or is_garbled(intent) or is_garbled(reason):
            print(f"Suspicious by chars: ID={ex['id']}, msg='{msg[:20]}...', reason='{reason[:20]}...'")

if __name__ == "__main__":
    find_corrupted()
