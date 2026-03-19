import asyncio
from dotenv import load_dotenv
load_dotenv(r"c:\Users\leejo\Project\AI Agent\Spam Detector\backend\.env")
from app.agents.ibse_agent.selector import LLMSelector
from app.agents.ibse_agent.state import IBSEState, Candidate

async def main():
    selector = LLMSelector()
    
    text = "휴대폰매장입니다 케이스 도착했어요 매장방문해주세요~으)로부터 압류명령이 접수되었음을 안내드복지"
    text_nospace = text.replace(" ", "")
    
    # Mocking what candidate component outputs exactly
    c20 = [Candidate(
        id="c20_0",
        text="휴대폰매장입니다케이",
        text_original="휴대폰매장입니다 케이",
        byte_len_cp949=20,
        start_idx=0,
        end_idx_exclusive=10,
        anchor_tags=[],
        score=0.0
    )]
    
    c40 = [Candidate(
        id="c40_0",
        text="휴대폰매장입니다케이스도착했어요매장방문해",
        text_original="휴대폰매장입니다 케이스 도착했어요 매장방문해",
        byte_len_cp949=40,
        start_idx=0,
        end_idx_exclusive=19,
        anchor_tags=[],
        score=0.0
    )]
    
    state: IBSEState = {
        "message_id": "test_msg",
        "original_text": text,
        "match_text": text_nospace,
        "candidates_20": c20,
        "candidates_40": c40,
        "selected_decision": None,
        "selected_candidate": None,
        "final_result": None,
        "retry_count": 0,
        "error": None
    }
    
    print("Calling actual LLMSelector...")
    try:
        res = await selector.select(state)
        print("Success!")
        import pprint
        pprint.pprint(res)
    except Exception as e:
        print(f"Failed: {type(e)} - {e}")

if __name__ == "__main__":
    asyncio.run(main())
