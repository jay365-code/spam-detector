import sys

filepath = r'c:\Users\leejo\Project\AI Agent\Spam Detector\backend\app\utils\excel_handler.py'
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('Font(bold=True, size=10)', 'Font(name="맑은 고딕", bold=True, size=11.0)')
text = text.replace('Font(size=10, bold=True)', 'Font(name="맑은 고딕", bold=True, size=11.0)')
text = text.replace('Font(size=10)', 'Font(name="맑은 고딕", size=11.0)')

# For 육안분석 we need size 10.5 specifically!
# Let's see if there is any place specifically for 육안분석
# Let's restore 10.5 for _create_analysis_sheet
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)
