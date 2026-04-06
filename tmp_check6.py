import unicodedata

text = "[ ­­­­­­­­­­쿠­­­­­­­­­­팡 파트너사 소식 ] 쿠팡 파트너사 체험단 당첨자 안내 http://pf.kakao.com/_xgwUVX/chat 참여진행은 위 링크에서 가능 하십니다. -“상품선택” 이라고 채팅회신시 체험신청이 완료 됩니다 ※ 혜택안내 - 체험 완료 후 체험 수당 매일 지급! - 제휴사 제공 물품 당일 배송 http://pf.kakao.com/_xgwUVX/chat ※ 접수시 체험수당(현금)과 제품 모두 파트너사에서 지급발송 합니다 ※ 무료안내 - 등록후 체험단 완료시마다 체험 수당 즉시 정산됩니다. - 제휴사 선택물품 발송 (무료지급) ※ 등록신청 시간 오전09:00 ~ 오후 20:"

invisible_chars = []
for i, char in enumerate(text):
    category = unicodedata.category(char)
    code = ord(char)
    # Cf: Format, Mn: Non-spacing Mark, Co: Private Use, ZWSP: 200B
    if category.startswith('C') or code in [0x00AD, 0x200B, 0x200C, 0x200D, 0xFEFF]:
        invisible_chars.append((i, char, hex(code), unicodedata.name(char, 'UNKNOWN')))

print(f"Total string length: {len(text)}")
if invisible_chars:
    print(f"Found {len(invisible_chars)} invisible/special characters!")
    for idx, c, h, name in invisible_chars[:30]:
        print(f"Index {idx:03d}: {h} ({name})")
else:
    print("No invisible characters found.")
