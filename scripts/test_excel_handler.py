import asyncio
import os
import sys

# Add project root to sys.path so we can import app modules
# The root is where backend is located
project_root = r"c:\Users\leejo\Project\AI Agent\Spam Detector"
sys.path.insert(0, project_root)

from backend.app.utils.excel_handler import ExcelHandler

async def mock_processing_function(messages, start_index=0, total_count=0, pre_parsed_urls=None, is_trap=False):
    # Just return empty dummy results
    results = []
    for _ in messages:
        results.append({
            "is_spam": False,
            "semantic_class": "Ham",
            "reason": "Test"
        })
    return results

def test():
    file_path = os.path.join(project_root, r"spams\kisa_20260101_A_result_hamMsg_url_test.txt")
    output_dir = os.path.join(project_root, "backend", "tmp")
    
    handler = ExcelHandler()
    res = handler.process_kisa_txt(
        file_path, 
        output_dir, 
        mock_processing_function,
        None,
        1,
        "kisa_20260101_A_result_hamMsg_url_test.txt",
        None,
        None,
        False
    )
    print("Test passed. Created File:", res["filename"])

if __name__ == "__main__":
    test()
