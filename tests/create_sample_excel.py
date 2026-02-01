from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = '육안분석(시뮬결과35_150)'
ws.append(['메시지'])

data = [
    ["안녕하세요. 이번 주말 모임 참석하시나요?"], # HAM
    ["향.꼼.썽! 100% 당첨 보장!"], # SPAM (Obfuscation)
    ["최저금리 대출 상담. http://loan-scam.com"], # SPAM (URL)
    ["무료 픽 드립니다. 카톡 아이디 추가하세요."], # SPAM (Keyword)
    ["정상적인 업무 관련 메일입니다. 검토 부탁드립니다."] # HAM
]

for row in data:
    ws.append(row)

wb.save('sample_test.xlsx')
print("sample_test.xlsx created successfully.")
