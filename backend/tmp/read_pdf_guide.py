import fitz
import sys

pdf_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\docs\스팸태깅 작업 절차_1일3회작업(2026.03.26).pdf"
out_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\backend\tmp\pdf_tagging_guide.txt"

try:
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print("Success")
except Exception as e:
    print(f"Error with PyMuPDF: {e}")
    try:
        import PyPDF2
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print("Success with PyPDF2")
    except Exception as e2:
        print(f"Error with PyPDF2: {e2}")
