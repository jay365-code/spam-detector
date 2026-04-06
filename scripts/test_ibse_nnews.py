import asyncio
import json
from app.agents.ibse_agent.agent import workflow as ibse_workflow
from app.agents.ibse_agent.state import IBSEState

async def run():
    text = "(광고) 최상위 VIP 리딩방 폭등주 적중!! 무료체험방 입장전 아래 경제 기사 확인바랍니다. https://n.news.naver.com/mnews/article/001/00145678 거부 0808889999"
    state = IBSEState(match_text=text)
    res = await ibse_workflow.compile().ainvoke(state)
    print(json.dumps(res, ensure_ascii=False, indent=2))

asyncio.run(run())
