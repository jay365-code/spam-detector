from docx import Document
import sys

doc_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\docs\스팸 및 햄 차단 기준(20230724)_대리운전 관련 변경 반영.docx"
out_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\backend\tmp\legacy_guide.txt"

try:
    doc = Document(doc_path)
    text = []
    for para in doc.paragraphs:
        if para.text.strip():
            text.append(para.text.strip())
            
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text))
    print("Success")
except Exception as e:
    print(f"Error: {e}")
