import asyncio
from app.agents.content_agent.service import ContentAgentService

async def main():
    service = ContentAgentService()
    text = "(광고)나이키  대체불가♥토지노 성공으로가는 하이패스 주소 ↓ nike26.  무료거부 0808701121"
    result = await service.process_message({"original_text": text, "message_id": "1"})
    print("Content Agent Result:", result)

asyncio.run(main())
