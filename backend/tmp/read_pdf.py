import sys

pdf_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\docs\스팸태깅 작업 절차_1일3회작업(2026.03.26).pdf"

try:
    import fitz
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    print(text)
    sys.exit(0)
except ImportError:
    pass

try:
    from PyPDF2 import PdfReader
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    print(text)
    sys.exit(0)
except ImportError:
    print("Could not import fitz or PyPDF2")
    sys.exit(1)
