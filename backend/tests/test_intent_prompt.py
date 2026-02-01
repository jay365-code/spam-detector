
import os
import sys
import asyncio
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../"))
load_dotenv(override=True)

from app.core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# Mock Agent for Prompt Testing
class MockAgent:
    def __init__(self):
        self.model_name = os.getenv("LLM_MODEL", "gpt-5-mini")
        self.api_key = os.getenv("OPENAI_API_KEY")
        provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()

        if provider == "GEMINI":
            from langchain_google_genai import ChatGoogleGenerativeAI
            self.llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=os.getenv("GEMINI_API_KEY"),
                temperature=0.0
            )
        else:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                temperature=0.0 
            )

    async def _generate_intent_summary(self, message: str) -> str:
        prompt = f"""
        [GOAL]
        Understand the input message and summarize its "Core Intent" in 1-2 sentences.
        Remove all variable values (amounts, phone numbers, URLs, specifics) and focus on the *Pattern* and *Action*.
        
        [INPUT]
        {message}
        
        [OUTPUT GUIDELINES]
        - Format: "Principal Intent / Tactics / Action Request"
        - Do NOT include any PII (Person Identifiable Information) or specific numbers.
        - Example: 
            Input: "Deposit 300 today, contact 010-1234-5678" 
            Output: "Illegal Loan Advertisement / Immediate Deposit Promise / Request for contact via personal number"
        """
        
        response = await self.llm.ainvoke(prompt)
        return response.content

async def main():
    agent = MockAgent()
    
    test_cases = [
        "김미영 팀장입니다. 고객님께서는 3000만원까지 대출 가능하십니다. 010-1111-2222로 연락주세요.",
        "ㅋrㅈi노 가입만 해도 3만 포인트 지급! 100% 환전 가능 www.bet-777.com",
        "안녕하세요, 택배 배송 주소가 불명확하여 반송되었습니다. 아래 링크로 확인 부탁드립니다.",
        "[Web발신] (광고) 주식 리딩방 무료 초대. 300% 수익 보장. 링크 클릭: bit.ly/12345"
    ]
    
    print("\n=== Intent Summary Generation Test ===\n")
    
    for i, msg in enumerate(test_cases):
        print(f"[{i+1}] Original: {msg}")
        summary = await agent._generate_intent_summary(msg)
        print(f"    Summary: {summary}\n")

if __name__ == "__main__":
    asyncio.run(main())
