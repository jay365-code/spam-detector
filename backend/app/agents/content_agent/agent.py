import os
from dotenv import load_dotenv

load_dotenv(override=True) # Load .env file (override system variables)

import json
import logging

logger = logging.getLogger(__name__)
from dotenv import load_dotenv

load_dotenv(override=True) # Load .env file (override system variables)

from openai import OpenAI
from openai import OpenAI
import json
import logging

logger = logging.getLogger(__name__)

class ContentAnalysisAgent: # Renamed from RagBasedFilter
    def __init__(self):
        # Initialize LLM (Get model from env, default to gpt-5-mini)
        self.model_name = os.getenv("LLM_MODEL", "gpt-5-mini")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.vector_db = None

    def _get_vector_db(self):
        if self.vector_db is None:
            # Local imports to optimize startup
            from langchain_community.vectorstores import Chroma
            from langchain_openai import OpenAIEmbeddings
            
            print("[ContentAnalysisAgent] Initializing ChromaDB...")
            self.vector_db = Chroma(
                collection_name="spam_guide",
                embedding_function=OpenAIEmbeddings(model="text-embedding-ada-002"),
                persist_directory="../../data/chroma_db"
            )
        return self.vector_db

    def search_guide(self, message: str, k: int = 3):
        db = self._get_vector_db()
        return db.similarity_search(message, k=k)

    def _retrieve_context(self, message: str) -> str:
        """
        Retrieves context from Vector DB or loads full spam guide.
        """
        rag_on = os.getenv("RAG_ON", "1")
        
        if rag_on == "1":
            print(f"    [RAG] Mode ON: Searching Vector DB...")
            similar_docs = self.search_guide(message)
            context_text = "\n".join([doc.page_content for doc in similar_docs])
        else:
            print(f"    [RAG] Mode OFF: Using Full Spam Guide Text...")
            try:
                guide_path = os.path.join(os.path.dirname(__file__), "../../../data/spam_guide.md") # Path adjusted
                with open(guide_path, "r", encoding="utf-8") as f:
                    context_text = f.read()
            except Exception as e:
                # Try absolute path fallback matching the pattern in original
                try: 
                     # Attempt to find data dir dynamically
                     base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                     guide_path = os.path.join(base_dir, "data/spam_guide.md")
                     with open(guide_path, "r", encoding="utf-8") as f:
                        context_text = f.read()
                except Exception as e2:
                    print(f"    [Error] Failed to load spam_guide.md: {e2}")
                    context_text = "Error loading context."
        return context_text

    def _query_llm(self, prompt: str) -> str:
        """
        Executes the LLM call based on the provider.
        """
        content = ""
        provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
        
        try:
            if provider == "GEMINI":
                import google.generativeai as genai
                gemini_key = os.getenv("GEMINI_API_KEY")
                if not gemini_key:
                    raise ValueError("GEMINI_API_KEY is missing")
                    
                genai.configure(api_key=gemini_key)
                model_name = self.model_name if "gemini" in self.model_name else "gemini-1.5-flash"
                model = genai.GenerativeModel(model_name)
                # Sync call
                response = model.generate_content(prompt)
                content = response.text
                
            elif provider == "CLAUDE":
                import anthropic
                claude_key = os.getenv("CLAUDE_API_KEY")
                if not claude_key:
                    raise ValueError("CLAUDE_API_KEY is missing")
                    
                client = anthropic.Anthropic(api_key=claude_key)
                model_name = self.model_name if "claude" in self.model_name else "claude-3-haiku-20240307"
                
                response = client.messages.create(
                    model=model_name,
                    max_tokens=1024,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.content[0].text

            else: # Default to OPENAI
                local_client = OpenAI(api_key=self.api_key)
                response = local_client.responses.create(
                    model=self.model_name,
                    input=prompt
                )
                content = response.output_text.strip()
                
        except Exception as e:
            print(f"{provider} API Error: {e}")
            raise e
        
        return content

    def _build_prompt(self, message: str, detected_pattern: str, context_text: str) -> str:
        return f"""
            Analyze the following text message to determine if it is SPAM or HAM.
            
            Message: "{message}"
            
            Context from Stage 1 (Rule Filter):
            - Detected Pattern: {detected_pattern}
            
            Context from Spam Guide (RAG):
            {context_text}
            
            Task:
            1. 각 메시지를 아래의 [판단 우선순위 계층]에 따라 엄격히 분석하십시오.
            2. 결과 도출 전 'analysis_step' 필드에 다음 과정을 반드시 기록하십시오:
               - [Step 1: Level 1 확인] 가이드의 [HAM분류] 혹은 [SPAM분류]에 즉각 해당하나?
               - [Step 2: 사업자 식별] **(가장 중요)** 사업자명, 지점명, 연락처가 명확하여 Level 3 규칙("사업자 정보 명확 시 HAM")을 적용할 수 있는가?
               - [Step 3: 정보의 구체성] 단순 유도(SPAM 우세)인가, 구체적 정보 제공(HAM 우세)인가?
               - [Step 4: 최종 판정] 위 단계들을 종합하여 결론 도출.
            3. 판단 원칙:
               - 메시지 내용에 스팸 패턴(현금지원, 특가 등)이 있더라도, **사업자 정보(지점명 등)가 명확하다면 Level 3에 의거하여 HAM으로 판정합니다.**
               - **반대로, 현금/경품 지급, 투자 유도, 무료 상담 등의 내용이 포함되어 있으나 사업자 정보(업체명, 사업자번호 등)가 명확하지 않다면 반드시 SPAM(확률 0.9 이상)으로 판정합니다.**
               - '20자 이내' 관련 규정이 있다면 이를 HAM 판정의 근거로 활용하십시오.
            
            Output Format:
            {{
                "id": 1,
                "analysis_step": "[Step 1]... [Step 2]... [Step 3]... [Step 4]...",
                "is_spam": true,
                "classification_code": "SPAM-1",
                "spam_probability": 0.95,
                "reason": "현금 지급을 미끼로 가입을 유도하며 사업자 정보가 불분명함"
            }}
            """

    def _parse_response(self, content: str, provider: str) -> dict:
        # Simple JSON cleanup
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "")
        elif content.startswith("```"):
            content = content.replace("```", "")
        
        # Debug Log
        logger.info(f"[ContentAnalysisAgent] Raw LLM Response: {content.strip()}")

        import json
        try:
            result_json = json.loads(content)
        except json.JSONDecodeError:
             logger.error("JSON Decode Error")
             return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": "Error (JSON Parse Fail)"}
        
        spam_prob = float(result_json.get("spam_probability", 0.0))
        classification_code = str(result_json.get("classification_code", ""))
        reason = result_json.get("reason", f"{provider} Analysis")
        
        # Extract Token Usage (Simplified for brevity, similar to original)
        input_tokens = 0
        output_tokens = 0

        if spam_prob < 0.4:
            is_spam = False
            classification_code = "0"
        
        elif 0.4 <= spam_prob < 0.6:
            is_spam = None # Undecided, will be handled by HITL
            classification_code = "30" # HITL Required
            reason = f"[HITL] Probability ({spam_prob:.2f}) is ambiguous. Requesting user feedback."
            
        else: # >= 0.6
            is_spam = True

        return {
            "is_spam": is_spam,
            "spam_probability": spam_prob,
            "classification_code": classification_code,
            "reason": reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    def check(self, message: str, stage1_result: dict) -> dict:
        """
        Stage 2: RAG + LLM (Sync Version)
        """
        try:
            # 1. RAG Retrieval
            context_text = self._retrieve_context(message)
            
            # 2. LLM Inference
            detected_pattern = stage1_result.get("detected_pattern", "None")
            prompt = self._build_prompt(message, detected_pattern, context_text)
            
            content = self._query_llm(prompt)
            
            return self._parse_response(content, os.getenv("LLM_PROVIDER", "OPENAI"))
            
        except Exception as e:
            print(f"LLM Error: {e}")
            return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": "Error (LLM Fail)"}

    from typing import Callable, Awaitable, Optional

    async def acheck(self, message: str, stage1_result: dict, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> dict:
        """
        Stage 2: RAG + LLM (Async Version with Callbacks)
        """
        import asyncio
        loop = asyncio.get_running_loop()
        
        try:
            # 1. RAG Retrieval (Run in thread to avoid blocking)
            if status_callback:
                await status_callback("🔍 문맥 검색 중... (RAG)")
            
            context_text = await loop.run_in_executor(None, lambda: self._retrieve_context(message))
            
            # 2. LLM Inference
            if status_callback:
                await status_callback("🧠 AI 정밀 분석 중...")
                
            detected_pattern = stage1_result.get("detected_pattern", "None")
            prompt = self._build_prompt(message, detected_pattern, context_text)
            
            # Run blocking LLM call in executor
            content = await loop.run_in_executor(None, lambda: self._query_llm(prompt))
            
            result = self._parse_response(content, os.getenv("LLM_PROVIDER", "OPENAI"))
            
            if status_callback:
                verdict = "SPAM" if result['is_spam'] else "HAM"
                if result['is_spam'] is None: verdict = "HITL"
                await status_callback(f"✅ 분석 완료 (판정: {verdict})")
                
            return result
            
        except Exception as e:
            logger.error(f"Async LLM Error: {e}")
            if status_callback:
                 await status_callback(f"⚠️ 오류 발생: {str(e)}")
            return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": f"Error: {e}"}

    async def check_batch(self, messages: list[str], stage1_results: list[dict]) -> list[dict]:
        """
        Stage 2 (Batch) implementation
        Process multiple messages appropriately.
        """
        results = []
        
        # Simple iterative processing for now. 
        # Ideally, this could uses LLM batch APIs or concurrent execution,
        # but for consistent results with the single check logic, iteration is safest.
        for i, message in enumerate(messages):
            s1_result = stage1_results[i] if i < len(stage1_results) else {}
            try:
                # Reuse the existing check logic
                # Note: check() is synchronous in this class currently (uses standard calls).
                # If we want true async, we should refactor check() to be async or run_in_executor.
                # Since get_chat_model returns correct client, we stick to sequential for reliability first.
                result = self.check(message, s1_result)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch Item Error: {e}")
                results.append({
                    "is_spam": False, 
                    "reason": f"Error in batch processing: {str(e)}",
                    "classification_code": "ERROR"
                })
        
        return results

    def _get_chat_model(self):
        """
        Returns a LangChain Chat Model based on valid environment variables.
        """
        provider = os.getenv("LLM_PROVIDER", "OPENAI").upper()
        
        # Local Imports for Lazy Loading
        from langchain_openai import ChatOpenAI
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_anthropic import ChatAnthropic

        if provider == "GEMINI":
            api_key = os.getenv("GEMINI_API_KEY")
            return ChatGoogleGenerativeAI(
                model=self.model_name if "gemini" in self.model_name else "gemini-1.5-flash",
                google_api_key=api_key,
                temperature=0.3
            )
        elif provider == "CLAUDE":
            api_key = os.getenv("CLAUDE_API_KEY")
            return ChatAnthropic(
                model=self.model_name if "claude" in self.model_name else "claude-3-haiku-20240307",
                anthropic_api_key=api_key,
                temperature=0.3
            )
        else: # OPENAI
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                temperature=0.3
            )



    async def generate_final_summary(self, message: str, content_result: dict, url_result: dict = None) -> str:
        """
        Generates a final executive summary based on both Content and URL analysis results.
        """
        prompt = f"""
        You are a Spam Prevention Expert. Synthesize the analysis results below into a 3-line final verdict for the user.

        [User Message]
        {message}

        [Content Analysis Result]
        - Verdict: {'SPAM' if content_result.get('is_spam') else 'HAM'}
        - Reason: {content_result.get('reason')}

        [URL Analysis Result]
        {'- N/A (URL not found or not analyzed)' if not url_result else f"- Verdict: {'SPAM' if url_result.get('is_spam') else 'SAFE'}"}
        {'- Reason: ' + url_result.get('reason') if url_result else ''}
        {'- Details: ' + str(url_result.get('details')) if url_result else ''}

        [Task]
        Write a friendly but firm final summary in Korean.
        1. **Final Conclusion**: Start with a clear emoji (🚫 for Spam, ✅ for Safe, ⚠️ for Caution).
        2. **Synthesis**: Explain *why* based on the combination of text and URL evidence. (e.g., "Text seemed safe, but the URL leads to a known phishing site.")
        3. **Action**: Tell the user exactly what to do (e.g., "Do not click," "Block this number," or "Safe to ignore").

        Provide a comprehensive and helpful summary without strict length limits.
        """

        try:
            llm = self._get_chat_model()
            # Since this is a single call (not stream), we use .invoke or generic call
            from langchain_core.messages import HumanMessage
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            
            # Extract content robustly
            if hasattr(response, 'content'):
                content = response.content
                if isinstance(content, list) and len(content) > 0:
                     # Handle list of blocks (e.g. Anthropic)
                     if isinstance(content[0], dict) and 'text' in content[0]:
                         return content[0]['text']
                     return str(content) # Fallback if structure unknown
                return content # Valid string
                
            elif isinstance(response, list) and len(response) > 0:
                 if isinstance(response[0], dict) and 'text' in response[0]:
                     return response[0]['text']
                 elif hasattr(response[0], 'content'):
                     return response[0].content
            
            return str(response)
            
            return str(response)

        except Exception as e:
            logger.error(f"Summary Generation Error: {e}")
            return "종합 결과 요약 생성 중 오류가 발생했습니다."
