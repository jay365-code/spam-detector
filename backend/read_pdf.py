import sys
from pypdf import PdfReader

try:
    reader = PdfReader(r'c:\Users\leejo\Project\AI Agent\Spam Detector\docs\스팸태깅 작업 절차_1일3회작업(25.12.01-26.03.31).pdf')
    print('--- PAGE 3 (Index 2) ---')
    print(reader.pages[2].extract_text())
    print('--- PAGE 4 (Index 3) ---')
    print(reader.pages[3].extract_text())
    print('--- PAGE 5 (Index 4) ---')
    print(reader.pages[4].extract_text())
except Exception as e:
    print("Error:", e)
