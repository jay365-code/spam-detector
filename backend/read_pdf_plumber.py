import pdfplumber
import sys

pdf_path = r'c:\Users\leejo\Project\AI Agent\Spam Detector\docs\스팸태깅 작업 절차_1일3회작업(25.12.01-26.03.31).pdf'
try:
    with pdfplumber.open(pdf_path) as pdf:
        print("--- PAGE 8 (Index 7) ---")
        print(pdf.pages[7].extract_text() or "No text")
        print("--- PAGE 9 (Index 8) ---")
        print(pdf.pages[8].extract_text() or "No text")
        print("--- PAGE 10 (Index 9) ---")
        print(pdf.pages[9].extract_text() or "No text")
except Exception as e:
    print("Error:", e)
