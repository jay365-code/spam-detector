import pdfplumber
import pandas as pd
import sys

def main():
    pdf_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\docs\스팸태깅 작업 절차_1일3회작업(2026.03.26).pdf"
    excel_path = r"c:\Users\leejo\Project\AI Agent\Spam Detector\spams\MMSC스팸추출_20260327_A.xlsx"
    out_pdf = r"c:\Users\leejo\Project\AI Agent\Spam Detector\tmp\pdf_analysis.txt"
    out_excel = r"c:\Users\leejo\Project\AI Agent\Spam Detector\tmp\excel_analysis.txt"

    print("Extracting PDF...")
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    
    with open(out_pdf, "w", encoding="utf-8") as f:
        f.write(text)

    print("Extracting Excel...")
    xlsx = pd.ExcelFile(excel_path)
    with open(out_excel, "w", encoding="utf-8") as f:
        f.write("Sheet names:\n")
        f.write(str(xlsx.sheet_names) + "\n\n")
        
        for sheet in xlsx.sheet_names:
            if "TRAP" in sheet:
                f.write(f"--- Sheet: {sheet} ---\n")
                df = xlsx.parse(sheet).head(5)
                f.write(f"Columns: {list(df.columns)}\n")
                f.write(df.to_string() + "\n\n")

if __name__ == "__main__":
    main()
