
import os

file_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\spams\kisa_20260101_A_result_hamMsg_url_test - one.txt'

try:
    with open(file_path, 'rb') as f:
        raw_data = f.read(64) # Read first 64 bytes
    
    print(f"File Path: {file_path}")
    print(f"Hex Dump: {raw_data.hex(' ')}")
    print(f"Raw Bytes: {raw_data}")
    
    # Analyze known patterns
    if b'\xef\xbb\xbf' in raw_data:
        print("BOM detected: UTF-8-SIG")
    
    # Check for UTF-8 Replacement Character (EF BF BD)
    if b'\xef\xbf\xbd' in raw_data:
        print("WARNING: UTF-8 Replacement Character (U+FFFD) detected! The file might have been saved with broken encoding.")
        
except Exception as e:
    print(f"Error reading file: {e}")
