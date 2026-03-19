
import logging
from app.services.rule_service import RuleBasedFilter
import os
import sys

# Configure basic logging to stdout
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def test_garbled_file():
    file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\kisa_20260101_A_result_hamMsg_url_test - one.txt'
    
    print(f"--- Testing File: {os.path.basename(file_path)} ---")
    
    # 1. Inspect Raw Content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"Content Preview (first 100 chars): {content[:100]}")
            
            # Check for Replacement Character (U+FFFD)
            if '\ufffd' in content:
                print("Confirmed: File contains U+FFFD (Replacement Character). This means data was lost during a previous save/conversion.")
            else:
                print("Result: No U+FFFD found. File might be just Mojibake (wrong decoding but bytes preserved) or correct.")

    except Exception as e:
        print(f"Error reading file utf-8: {e}")
        return

    # 2. Test RuleBasedFilter Analysis
    print("\n--- Running RuleBasedFilter ---")
    rule_filter = RuleBasedFilter()
    
    # Check Foreign Language Logic
    foreign_check = rule_filter.has_foreign_language(content)
    print(f"Foreign Language Check Result: {foreign_check}")
    
    # Check Full Logic
    result = rule_filter.check(content)
    print("Full Rule Check Result:")
    print(result)

    # 3. Explain "Why Foreign?" if applicable
    if foreign_check['has_foreign']:
        print("\nAnalysis: The garbled text resembles non-Korean characters, so the system flags it as Foreign Language.")
        print("This is EXPECTED behavior for broken text. The root cause is the file content itself, not the logic.")

if __name__ == "__main__":
    # Add project root to sys.path to import app.services
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    test_garbled_file()
