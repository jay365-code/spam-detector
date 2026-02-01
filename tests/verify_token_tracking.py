import os
import sys

# Add backend directory to sys.path
backend_path = os.path.abspath("backend")
sys.path.append(backend_path)

from backend.app.services.filter_rag import RagBasedFilter
from backend.app.utils.excel_handler import ExcelHandler

# Mocking the processing function to use RagBasedFilter
rag_filter = RagBasedFilter()

def processing_function(message):
    # Mocking Stage 1 Result
    stage1_result = {"detected_pattern": "None"}
    # Force RAG OFF to avoid DB lock during simple token tracking test
    # We only want to test that tokens are recorded when check() returns
    # But check() logic accesses DB.
    # Let's try to set RAG_ON=0 env var for this process
    os.environ["RAG_ON"] = "0" 
    return rag_filter.check(message, stage1_result)

def main():
    excel_handler = ExcelHandler()
    input_file = "sample_test.xlsx"
    output_file = "sample_test_result.xlsx"
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Please create it first.")
        return

    print(f"Processing {input_file}...")
    try:
        excel_handler.process_file(input_file, output_file, processing_function)
        print(f"Success! Result saved to {output_file}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    main()
