import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.agents.url_agent.nodes import extract_node

# 1. Test bit.ly
state1 = {
    "sms_content": "(광고)[NH]쉿!!일일 1900만 급등주bit.ly/밴드정보방선착순 마감무료거부 0801560190",
    "decoded_text": None,
    "content_context": {}
}
res1 = extract_node(state1)
print("--- TEST 1: bit.ly ---")
print(res1)

# 2. Test TOY9898 점켬
state2 = {
    "sms_content": '(광고) "토이" 랜덤 2만-20만 이용 부탁드립니다. ▶ 접 속 : TOY9898 점켬 ◆ 코 드 : KKKK ID',
    "decoded_text": None,
    "content_context": {"obfuscated_urls": ["toy9898.com"]} # Mocking LLM output
}
res2 = extract_node(state2)
print("\n--- TEST 2: TOY9898 ---")
print(res2)

# 3. Test 3nwdavin84.com (Let's check if the fallback text is built correctly in analyze_node)
from app.agents.url_agent.nodes import analyze_node
import asyncio

state3 = {
    "sms_content": "선물:50000[원]불 사 조 출 현5 0 0 장 획 득 추 8 4 3nwdvin84.com",
    "scraped_data": {
        "status": "failed",
        "error": "ERR_NAME_NOT_RESOLVED",
        "url": "http://3nwdavin84.com",
        "fallback_log": ["http://3nwdavin84.com -> http://nwdavin84.com (숫자 난독화 제거)"]
    }
}
res3 = asyncio.run(analyze_node(state3))
print("\n--- TEST 3: analyze_node fallback log ---")
print(res3)
