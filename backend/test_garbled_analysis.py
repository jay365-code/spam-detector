
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
    
    # Check Full Logic
    result = rule_filter.check(content)
    print("Full Rule Check Result:")
    print(result)

    # 3. Explain the result
    if result.get('is_spam') is None:
        print("\nAnalysis: Message passed to Content Agent (LLM) for further analysis.")
    elif result.get('is_spam') is False:
        print(f"\nAnalysis: Message classified as HAM by Rule Filter. Code: {result.get('classification_code')}")
    else:
        print(f"\nAnalysis: Message classified as SPAM by Rule Filter. Code: {result.get('classification_code')}")

if __name__ == "__main__":
    # Add project root to sys.path to import app.services
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    test_garbled_file()
