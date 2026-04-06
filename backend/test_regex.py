import re

message1 = "(광고)[CJ대한통운]bit.ly/37dsGj0[29**05] 반송물품 1건확인 요청무료수신거부 08085541"
spaceless_message1 = re.sub(r'\s+', '', message1)
domain_pattern = r'(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]{2,}(?:/[^\s\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]*)?'
sp_domain_pattern = r'(?:[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]+\.)+[a-zA-Z0-9\uac00-\ud7a3\u3131-\u3163-]{2,}(?:/[^\[\]<>◆▶★♥→※○●◎◇□■△▲▽▼▷◁◀♤♠♡♣⊙◈▣◐◑▒▤▥▨▧▦▩♨☏☎☜☞¶†‡↕↗↙↖↘♭♩♪♬]*)?'

print("Msg1 sp:", re.findall(sp_domain_pattern, spaceless_message1))

