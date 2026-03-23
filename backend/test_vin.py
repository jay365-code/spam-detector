import asyncio
from app.agents.content_agent.service import ContentAgentService

async def main():
    service = ContentAgentService()
    text = "선물:50000[원]불시조줄현500장적중주843nwdⓐvin⑧4.com"
    result = await service.process_message({"original_text": text, "message_id": "2"})
    print("Content Agent Result:", result)

asyncio.run(main())
