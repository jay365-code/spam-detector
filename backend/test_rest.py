import asyncio
import os
import json
import time
import httpx
from dotenv import load_dotenv

load_dotenv(r"c:\Users\leejo\Project\AI Agent\Spam Detector\backend\.env")

async def run():
    api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        api_keys = os.getenv("GEMINI_API_KEYS", "").split(",")
        api_key = api_keys[0].strip().strip('"').strip("'") if api_keys else None
        
    sys_prompt = """너는 IBSE(Intelligence Blocking Signature Extractor)의 판단 엔진이다.
목표는 **이미 스팸으로 판명된 메시지**에서, 향후 동일/유사 공격을 효율적으로 차단할 수 있는 '문자열 시그니처'를 추출하는 것이다.

**[입력 컨텍스트 (Input Context)]**
- 입력된 메시지는 앞단(LLM 기반 Content Agent)에서 이미 **SPAM**으로 분류되었다.
- 따라서 네가 다시 스팸 여부를 판단할 필요는 없다. 오직 **"이 스팸을 가장 효과적으로 차단할 고유 패턴이 있는가?"**에만 집중하라.

**[전략적 제약 사항 (Strategic Constraints)]**
- **시스템 자원 한계**: 시그니처 차단 리스트는 최대 10,000개로 제한되어 있다. 따라서 **확실하고, 재사용성이 높으며, 치명적인** 패턴만 선별적으로 등록해야 한다.
- **IBSE의 역할 정의**: 이 시스템은 ML이 놓친 것을 잡는 것이 아니라, 스팸을 **더 싸고 빠르게(단순 문자열 매칭) 차단하기 위한 보조 장치**다.
- **억지 추출 금지**: 확실한 시그니처가 없다면 굳이 추출하지 마라. 이미 ML이 차단했으므로, 애매한 시그니처를 만들어 리소스를 낭비할 필요가 없다. **'확실하지 않으면 `unextractable`'**이 원칙이다.

중요 제약:
- 시그니처는 반드시 후보 목록에서만 선택한다. 후보 밖의 문자열을 새로 만들거나 변형/정규화/요약하지 않는다.
- 후보는 match_text에서 잘라낸 연속 substring이며, CP949 바이트 길이가 제공된다.
- 20바이트 이하 후보로 충분히 특이하고 스팸 앵커가 있으면 use_20을 선택한다.
- 20바이트로는 일반적이거나 오탐 위험이 크면 40바이트 이하 후보 중 선택(use_40).
- 40바이트에서도 일반 문구 중심이거나 오탐 위험이 크면 unextractable을 선택한다.

**[판단 최우선 원칙: 특이점(Unique Anchor) 추출 로직]**
너는 메시지 내용을 해석하는 것이 아니라, 문장구조의 '특이도(Uniqueness)'와 '결합의 이질성'을 평가한다. 
평범한 단어(Low Entropy)는 버리고, 정상적인 문장에서는 절대 우연히 조합될 수 없는 기형적인 텍스트 덩어리(High Entropy)를 찾아라.

1. **최우선 (Must Extract) : 구조적 이질성과 고유 식별 블록 (Structural Anomaly & Unique Id-Block)**
    - 특정 단어의 의미나 종류(이름, 번호, 기호 등)는 중요하지 않다. 메시지의 일반적인 문장(템플릿) 흐름과 구조적으로 완전히 단절된 채, 숫자, 기호, 특이한 명사들이 인위적으로 뭉쳐진 20~40바이트의 덩어리를 찾는다. 
    - 예: "바밤바 둘 리 ( 010 2387 7373 )", "국&태봉# ☎010-6851", "V-VIP 입장 t.me/abcd"
    - 이 덩어리는 스팸 발송자가 자신을 식별받기 위해 삽입한 '고유 서명(Signature)'일 확률이 99%다. 주변 문맥과 이 고유 정보가 한 덩어리로 묶인 후보(use_20 또는 use_40)를 최우선으로 선택하라.
    - 판단 기준: "이 20~40바이트 문자열 구성을 일반인이나 다른 기업이 토씨 하나 안 틀리고 우연히 똑같이 사용할 확률이 0%에 가까운가?" -> Yes라면 완벽한 시그니처다.

2. **차선 (High Priority) : 난독화 및 필터 회피 패턴 (Obfuscation Patterns)**
    - 일반적인 단어 사이에 특수기호나 자모음 분리, 기이한 영어/숫자 조합이 끼어있는 형태 ('대.출', 'ㅋr톡', 'vt⑨8g'). 이 자체로 세상에 유일한(Unique) 문자열이 되므로 좋은 시그니처다.
    - **[우선순위 절대 규칙]** 만약 후보군 중에 이런 강력한 난독화(`■최'대`, `인Eㅓ냇`) 기법이 포함되어 있다면, 그 주변이나 끝부분에 '무료거부', '상담' 같은 추출 금지(평범한 문구) 조건이 섞여 있더라도 **무조건 난독화 앵커를 우선순위로 두고 타협 없이 시그니처로 추출하라. 딜레마에 빠지지 마라.**

3. **절대 금지 및 조기 포기(Fail-fast) : 파편화된 정보 및 범용/상용구 문구**
    - **파편화된 정보 금지:** "010-1234", "김팀장" 처럼 우연히 겹칠 수 있는 짧고 흔한 정보의 조각만 단독으로 떼어내지 마라.
    - **[핵심] 일상 대화형 결합 금지:** 전화번호 주변이 오직 "여기로 연락주세요", "담당자", "무료거부 080" 같은 평범한 템플릿으로만 이루어져 있다면 오탐 확률이 크므로 절대 추출하지 않는다.
    - **예외 허용 (식별자 결합):** 단, "독 ZT03 무료거부 080" 처럼 **일반 상용구 옆에 고유한 식별자/난독화 코드(ZT03 등)가 강하게 결합되어 있다면 훌륭한 시그니처**이므로 적극 추출하라.
    - **[조기 포기 규칙 (Fail-fast)]:** 만약 제공된 후보 5개가 전부 고유 식별자 없이 흔한 상용구(무료거부, 상담 등)나 평범한 문장으로만 이루어져 있어 안전한 추출이 불가능하다고 판단되면, **억지로 다른 부분을 떼어내려 고민하지 마라. 단 1초도 고민하지 말고 즉시 `{"decision": "unextractable"}`을 뱉고 출력을 종료해라. 억지로 추출하는 것은 시스템 장애(Timeout)의 원인이 된다.**


**[특수 규칙: URL이 포함된 경우 (Special Rule for URLs)]**
- **정상적인 URL**(`http`, `www`, `naver.com` 등 **깨끗한 형태**)이 포함된 경우:
    - 리소스 낭비를 막기 위해 **`unextractable`을 선택**한다. (URL Agent 위임)
- **난독화된/변형된 URL**(`vt⑨8g.COm`, `k-bank. xyz` 등)이 포함된 경우:
    - 이는 정상 URL이 아니므로, **시그니처로 추출해야 한다**. (최우선 순위 적용)
    - 예: `vt⑨8g.COm` -> 추출 허용.
    - 예: `www.google.com` -> 추출 금지 (`unextractable`).

반드시 JSON 단일 객체만 출력한다. 추가 텍스트 금지."""

    user_template = """message_id: {message_id}
match_text: {match_text}

candidates_20: {candidates_20_json}

candidates_40: {candidates_40_json}

출력(JSON):
{{
  "message_id": "{message_id}",
  "decision": "use_20" | "use_40" | "unextractable",
  "chosen_candidate_id": "...",
  "signature": "...",
  "byte_len_cp949": 0,
  "start_idx": 0,
  "end_idx_exclusive": 0,
  "risk": "low" | "medium" | "high",
  "reason": "한 줄 근거(특이성/앵커/오탐위험)"
}}"""

    text = '휴대폰매장입니다 케이스 도착했어요 매장방문해주세요~으)로부터 압류명령이 접수되었음을 안내드복지'
    
    # Mocking what candidate component outputs exactly
    c20 = [{'id':'c20_0','text':'휴대폰매장입니다케이','text_original':'휴대폰매장입니다 케이','byte_len_cp949':20,'start_idx':0,'end_idx_exclusive':10,'anchor_tags':[],'score':0.0}]
    c40 = [{'id':'c40_0','text':'휴대폰매장입니다케이스도착했어요매장방문해','text_original':'휴대폰매장입니다 케이스 도착했어요 매장방문해','byte_len_cp949':40,'start_idx':0,'end_idx_exclusive':19,'anchor_tags':[],'score':0.0}]

    user_msg = user_template.format(
        message_id='test_msg',
        match_text=text.replace(' ', ''),
        candidates_20_json=json.dumps(c20, ensure_ascii=False),
        candidates_40_json=json.dumps(c40, ensure_ascii=False)
    )

    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}'
    headers = {'Content-Type': 'application/json'}
    data = {
        'contents': [
             {'role': 'user', 'parts': [{'text': sys_prompt + '\n\n' + user_msg}]}
        ],
        'generationConfig': {
            'temperature': 0.0,
            'responseMimeType': 'application/json'
        }
    }

    print('Calling Gemini REST API...')
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(url, headers=headers, json=data)
            print(f'Success in {time.time()-start:.2f}s! \nResponse: {res.text}')
    except Exception as e:
        print(f'Timeout or Error after {time.time()-start:.2f}s: {e}')

asyncio.run(run())
