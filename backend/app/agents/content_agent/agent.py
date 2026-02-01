import os
from dotenv import load_dotenv

load_dotenv(override=True) # Load .env file (override system variables)

import json
import logging
from app.core.logging_config import get_logger

logger = get_logger(__name__)
# from openai import OpenAI  <-- Removed global import

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
            
            logger.debug("ChromaDB 초기화 중...")
            self.vector_db = Chroma(
                collection_name="spam_guide",
                embedding_function=OpenAIEmbeddings(model="text-embedding-ada-002"),
                persist_directory="../../../data/chroma_db"
            )
        return self.vector_db

    def search_guide(self, message: str, k: int = 3):
        """Guide 검색 (실패 시 빈 리스트 반환)"""
        try:
            db = self._get_vector_db()
            results = db.similarity_search(message, k=k)
            logger.info(f"RAG 검색 결과: {len(results)}건")
            for i, doc in enumerate(results):
                logger.debug(f"  [{i+1}] {doc.page_content[:80]}...")
            return results
        except Exception as e:
            logger.warning(f"RAG Guide Search Error: {e}")
            return []
    
    def _search_spam_rag(self, intent_summary: str, k: int = 2) -> list:
        """스팸 참조 예시 검색 (Spam RAG) - Intent Summary 기반"""
        # 환경변수로 검색 비활성화 가능 (비용 절감)
        rag_enabled = os.getenv("SPAM_RAG_ENABLED", "1")
        if rag_enabled != "1":
            print(f"    [Spam RAG] Disabled (SPAM_RAG_ENABLED={rag_enabled})")
            return []
        
        try:
            from app.services.spam_rag_service import get_spam_rag_service
            rag_service = get_spam_rag_service()
            # Intent Summary로 검색
            results = rag_service.search_similar(intent_summary, k=k)
            return results.get("hits", []) # Contract: returns dict with 'hits'
        except Exception as e:
            logger.warning(f"RAG Search Error: {e}")
            return []

    def _retrieve_context(self, message: str, intent_summary: str = None) -> dict:
        """
        Retrieves context from Vector DB or loads full spam guide.
        Also retrieves similar FN examples using Intent Summary.
        
        Returns:
            dict with 'guide_context' and 'rag_examples'
        """
        # [Deprecated] RAG 기능 비활성화 (항상 Full Context 사용)
        # rag_on = os.getenv("RAG_ON", "1")
        # guide_context = ""
        # 
        # if rag_on == "1":
        #     logger.debug("RAG Mode ON: Searching Vector DB...")
        #     similar_docs = self.search_guide(message)
        #     if similar_docs:
        #         guide_context = "\n".join([doc.page_content for doc in similar_docs])
        #     else:
        #         # RAG 검색 실패 시 Fallback: 전체 가이드 로드
        #         logger.info("RAG Fallback: Loading full guide (search returned empty)")
        #         guide_context = self._load_full_guide()
        # else:
        
        logger.debug("Using Full Spam Guide Text (RAG Disabled)")
        guide_context = self._load_full_guide()
        
        # RAG 예시 검색 (유사 스팸 사례) - Intent Summary 필수
        rag_examples = []
        if intent_summary:
            rag_examples = self._search_spam_rag(intent_summary, k=2)
            if rag_examples:
                logger.info(f"Spam RAG: {len(rag_examples)}건 검색됨")
            else:
                logger.debug("Spam RAG: 유사 사례 없음")
        else:
             logger.warning("Spam RAG: Intent Summary missing, skipping search.")
        
        return {
            "guide_context": guide_context,
            "rag_examples": rag_examples
        }
    
    def _load_full_guide(self) -> str:
        """전체 spam_guide.md 로드 (Fallback용)"""
        try:
            guide_path = os.path.join(os.path.dirname(__file__), "../../../data/spam_guide.md")
            with open(guide_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            try: 
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                guide_path = os.path.join(base_dir, "data/spam_guide.md")
                with open(guide_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e2:
                logger.error(f"    [Error] Failed to load spam_guide.md: {e2}")
                return "스팸 판단 기준: 도박, 성인, 사기, 불법 대출 의도가 명확하면 SPAM, 그렇지 않으면 HAM."

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
                # Sync call with temperature=0.2 for classification tasks
                generation_config = genai.GenerationConfig(temperature=0.2)
                response = model.generate_content(prompt, generation_config=generation_config)
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
                    temperature=0.2,  # 분류 작업에 적합한 낮은 temperature
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.content[0].text

            else: # Default to OPENAI
                local_client = OpenAI(api_key=self.api_key)
                response = local_client.responses.create(
                    model=self.model_name,
                    input=prompt,
                    temperature=0.2  # 분류 작업에 적합한 낮은 temperature
                )
                content = response.output_text.strip()
                
        except Exception as e:
            logger.exception(f"{provider} API Error")
            raise e
        
        return content

    def _build_prompt(self, message: str, detected_pattern: str, context_data: dict) -> str:
        guide_context = context_data.get("guide_context", "")
        rag_examples = context_data.get("rag_examples", [])
        
        # RAG 예시 섹션 구성
        # ChromaDB L2 distance: 0에 가까울수록 유사
        # [Intent-based RAG] 문장 유사도가 아닌 '의도 유사도'를 보기 위해 임계값을 0.35로 완화
        # 0.15 (문장 일치) -> 0.35 (의도 일치: 단어 달라도 맥락 유사하면 허용)
        distance_threshold = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.35"))
        
        rag_section = ""
        valid_examples = []
        
        if rag_examples:
            logger.info(f"    [RAG Examples] Filtering with threshold: {distance_threshold}")
            for ex in rag_examples:
                # [Fix] Map 'distance' from RAG service to 'score'
                score = ex.get('score', ex.get('distance', 999))
                
                # 유사도 점수가 임계값 이하인 경우만 포함
                if score <= distance_threshold:
                    valid_examples.append({**ex, 'score': score}) 
                else:
                    logger.debug(f"    [RAG Examples]   - score: {score:.3f}, excluded (threshold: {distance_threshold})")
            
            if valid_examples:
                rag_section = "\n[Reference Context - Similar Intent Examples]\n"
                rag_section += "아래는 유사한 의도(Intent)를 가진 과거 메시지 판정 결과입니다. 참고 자료로만 활용하세요.\n"
                for i, ex in enumerate(valid_examples, 1):
                    msg_preview = ex.get('message', '')[:100]
                    category = ex.get('category', 'N/A')
                    reason = ex.get('reason', 'N/A')
                    
                    rag_section += f"\n예시 {i} (유사도: {ex.get('score', 0):.3f}):\n"
                    rag_section += f"  메시지: \"{msg_preview}{'...' if len(ex.get('message', '')) > 100 else ''}\"\n"
                    rag_section += f"  판정: {ex.get('label', 'SPAM')} (code: {ex.get('code', '')})\n"
                    rag_section += f"  카테고리: {category}\n"
                    rag_section += f"  근거: {reason}\n"
                
                logger.info(f"    [RAG Examples] {len(valid_examples)} examples included in prompt (threshold: {distance_threshold})")
                
                # [User Request] Log the exact context injected into prompt
                logger.debug(f"    [RAG Examples Injected Content]:\n{rag_section}")
        
        return f"""
너는 스팸 분류 전문가다. 판단 기준은 아래 Spam Guide에만 존재한다.

--------------------------------------------------
[Message]
\"\"\"{message}\"\"\"

[Spam Guide]
{guide_context}
{rag_section}

--------------------------------------------------

[CRITICAL] 너는 텍스트만 분석한다. URL 존재는 SPAM 근거가 아니다 (URL은 별도 Agent가 분석).

[PROCEDURE]
Step 1. HARD GATE 확인 → harm_anchor = false 이면 무조건 HAM (label="HAM")
Step 2. harm_anchor 판정 → Guide 2.2 기준 (URL 무시, 텍스트만, 도박/성인/사기/어뷰즈 의도가 명확해야 true)
Step 3. 의도 명확도 판정 → spam_probability로 표현 (0.85 이상이면 의도가 매우 명확)
Step 4. SPAM 확정 조건:
   - 의도가 매우 명확 (spam_probability >= 0.85): harm_anchor=true면 SPAM (route_or_cta 무시)
   - 의도가 애매 (spam_probability < 0.85): harm_anchor=true AND route_or_cta=true 일 때만 SPAM

[OUTPUT — JSON ONLY]
{{
"label": "HAM|SPAM",
"ham_code": "HAM-1|HAM-2|HAM-3|null",
"spam_code": "0|1|2|3|null",
"spam_probability": 0.0,
"reason": "한국어로 판단 근거 작성 (과거 유사 사례가 있다면 반드시 언급)",
"signals": {{ "harm_anchor": false, "route_or_cta": false }}
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
        
        # Reverted to 'spam_probability' as per user request for readability.
        spam_prob = float(result_json.get("spam_probability", 0.0))
        
        # Additional Safety: If label is SPAM but probability is low (e.g. 0.0 default), trust label?
        label = result_json.get("label", "HAM").upper()
        if label == "SPAM" and spam_prob < 0.6:
             pass
        classification_code = str(result_json.get("classification_code", ""))
        
        # New Parsing Logic: Map spam_code/ham_code to classification_code if missing
        if not classification_code:
            spam_code = result_json.get("spam_code")
            ham_code = result_json.get("ham_code")
            
            if spam_code and str(spam_code).lower() != "null":
                classification_code = str(spam_code)
            elif ham_code and str(ham_code).lower() != "null":
                classification_code = str(ham_code)
        
        # New Schema Logic: Prefer singular 'reason', fallback to joining 'reasons' if list exists
        reason = result_json.get("reason")
        if not reason:
            reasons = result_json.get("reasons", [])
            if isinstance(reasons, list) and reasons:
                reason = " | ".join(reasons)
            else:
                reason = f"{provider} Analysis"
        
        # Extract Token Usage (Simplified for brevity, similar to original)
        input_tokens = 0
        output_tokens = 0
        
        # Extract signals for HARD GATE enforcement
        signals = result_json.get("signals", {})
        harm_anchor = signals.get("harm_anchor", False)
        route_or_cta = signals.get("route_or_cta", False)

        # ========== HARD GATE ENFORCEMENT ==========
        # Rule 1: harm_anchor = false → 무조건 HAM
        # Rule 2: 의도 명확(prob >= 0.85) + harm_anchor=true → SPAM (route_or_cta 무시)
        # Rule 3: 의도 애매(prob < 0.85) + harm_anchor=true → route_or_cta 확인 필요
        
        if not harm_anchor:
            # HARD GATE: harm_anchor가 false면 무조건 HAM
            is_spam = False
            if classification_code in ["0", "1", "2", "3", "10"]:
                classification_code = None
            label = result_json.get("label", "HAM").upper()
            if label == "SPAM":
                reason = f"[HARD GATE Override] harm_anchor=false → HAM 강제. 원래 reason: {reason}"
        elif harm_anchor and spam_prob >= 0.85:
            # 의도가 매우 명확 (prob >= 0.85): route_or_cta 확인 불필요 → SPAM 확정
            is_spam = True
            # route_or_cta가 false여도 SPAM 처리
        elif harm_anchor and not route_or_cta:
            # 의도가 애매 (prob < 0.85) + route_or_cta=false → HAM
            if spam_prob >= 0.6:
                # 의도는 있지만 확신은 부족, route_or_cta 없음 → HAM 처리하되 경고
                is_spam = False
                if classification_code in ["0", "1", "2", "3", "10"]:
                    classification_code = None
                reason = f"[HARD GATE] harm_anchor=true, prob={spam_prob:.2f} but route_or_cta=false → HAM. 원래 reason: {reason}"
            else:
                is_spam = False
                if classification_code in ["0", "1", "2", "3", "10"]:
                    classification_code = None
                reason = f"[HARD GATE] harm_anchor=true but route_or_cta=false → HAM. 원래 reason: {reason}"
        else:
            # harm_anchor=true AND route_or_cta=true → 확률 기반 판단
            if spam_prob < 0.4:
                is_spam = False
                if classification_code in ["0", "1", "2", "3", "10"]:
                    classification_code = None
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
            "signals": signals,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    def _build_prompt(self, message: str, detected_pattern: str, context_data: dict) -> tuple[str, list]:
        guide_context = context_data.get("guide_context", "")
        rag_examples = context_data.get("rag_examples", [])
        
        # RAG 예시 섹션 구성
        # ChromaDB L2 distance: 0에 가까울수록 유사
        # [Intent-based RAG] 문장 유사도가 아닌 '의도 유사도'를 보기 위해 임계값을 0.35로 완화
        # 0.15 (문장 일치) -> 0.35 (의도 일치: 단어 달라도 맥락 유사하면 허용)
        distance_threshold = float(os.getenv("RAG_DISTANCE_THRESHOLD", "0.35"))
        
        rag_section = ""
        valid_examples = []
        
        if rag_examples:
            logger.info(f"    [RAG Examples] Filtering with threshold: {distance_threshold}")
            for ex in rag_examples:
                # [Fix] Map 'distance' from RAG service to 'score'
                score = ex.get('score', ex.get('distance', 999))
                
                # 유사도 점수가 임계값 이하인 경우만 포함
                if score <= distance_threshold:
                    valid_examples.append({**ex, 'score': score}) 
                else:
                    logger.debug(f"    [RAG Examples]   - score: {score:.3f}, excluded (threshold: {distance_threshold})")
            
            if valid_examples:
                rag_section = "\n[Reference Context - Similar Intent Examples]\n"
                rag_section += "아래는 유사한 의도(Intent)를 가진 과거 메시지 판정 결과입니다. 참고 자료로만 활용하세요.\n"
                for i, ex in enumerate(valid_examples, 1):
                    msg_preview = ex.get('message', '')[:100]
                    category = ex.get('category', 'N/A')
                    reason = ex.get('reason', 'N/A')
                    
                    rag_section += f"\n예시 {i} (유사도: {ex.get('score', 0):.3f}):\n"
                    rag_section += f"  메시지: \"{msg_preview}{'...' if len(ex.get('message', '')) > 100 else ''}\"\n"
                    rag_section += f"  판정: {ex.get('label', 'SPAM')} (code: {ex.get('code', '')})\n"
                    rag_section += f"  카테고리: {category}\n"
                    rag_section += f"  근거: {reason}\n"
                
                logger.info(f"    [RAG Examples] {len(valid_examples)} examples included in prompt (threshold: {distance_threshold})")
                
                # [User Request] Log the exact context injected into prompt
                logger.debug(f"    [RAG Examples Injected Content]:\n{rag_section}")
        
        prompt_text = f"""
너는 스팸 분류 전문가다. 판단 기준은 아래 Spam Guide에만 존재한다.

--------------------------------------------------
[Message]
\"\"\"{message}\"\"\"

[Spam Guide]
{guide_context}
{rag_section}

--------------------------------------------------

[CRITICAL] 너는 텍스트만 분석한다. URL 존재는 SPAM 근거가 아니다 (URL은 별도 Agent가 분석).

[PROCEDURE]
Step 1. HARD GATE 확인 → harm_anchor = false 이면 무조건 HAM (label="HAM")
Step 2. harm_anchor 판정 → Guide 2.2 기준 (URL 무시, 텍스트만, 도박/성인/사기/어뷰즈 의도가 명확해야 true)
Step 3. 의도 명확도 판정 → spam_probability로 표현 (0.85 이상이면 의도가 매우 명확)
Step 4. SPAM 확정 조건:
   - 의도가 매우 명확 (spam_probability >= 0.85): harm_anchor=true면 SPAM (route_or_cta 무시)
   - 의도가 애매 (spam_probability < 0.85): harm_anchor=true AND route_or_cta=true 일 때만 SPAM

[OUTPUT — JSON ONLY]
{{
"label": "HAM|SPAM",
"ham_code": "HAM-1|HAM-2|HAM-3|null",
"spam_code": "0|1|2|3|null",
"spam_probability": 0.0,
"reason": "한국어로 판단 근거 작성 (과거 유사 사례가 있다면 반드시 언급)",
"signals": {{ "harm_anchor": false, "route_or_cta": false }}
}}
"""
        return prompt_text, valid_examples

    def check(self, message: str, stage1_result: dict) -> dict:
        """
        Stage 2: RAG + LLM (Sync Version)
        """
        # 메시지 원문 로그
        logger.debug(f"분석 시작 | msg={message[:80]}{'...' if len(message) > 80 else ''}")
        
        try:
            # 1. Intent Summary Generation
            intent_summary = self.generate_intent_summary(message)
            logger.info(f"Intent Summary: {intent_summary[:120]}...")

            # 2. RAG Retrieval (guide + FN examples)
            context_data = self._retrieve_context(message, intent_summary)
            
            # [Telemetry] Calculate Distance Metrics (Top 1/2 + Gap)
            rag_examples = context_data.get('rag_examples', [])
            d1, d2, gap = 9.9, 9.9, 0.0
            if len(rag_examples) >= 1:
                d1 = rag_examples[0].get('score', rag_examples[0].get('distance', 9.9))
                if len(rag_examples) >= 2:
                    d2 = rag_examples[1].get('score', rag_examples[1].get('distance', 9.9))
                    gap = d2 - d1
            logger.info(f"RAG Metrics | Top1={d1:.4f} | Top2={d2:.4f} | Gap={gap:.4f}")

            # 2. LLM Inference
            detected_pattern = stage1_result.get("detected_pattern", "None")
            prompt, valid_examples = self._build_prompt(message, detected_pattern, context_data)
            
            # [Telemetry] RAG Injection Stats
            rag_retrieved = len(rag_examples)
            rag_injected = len(valid_examples)
            has_guide = bool(context_data.get('guide_context'))
            
            # Label Distribution & IDs
            spam_hits = sum(1 for ex in valid_examples if ex.get('label') == 'SPAM')
            ham_hits = sum(1 for ex in valid_examples if ex.get('label') == 'HAM')
            injected_ids = [ex.get('id', 'unk') for ex in valid_examples]
            
            logger.info(f"프롬프트 생성 완료 | RAG Guide={'O' if has_guide else 'X'} | rag_retrieved={rag_retrieved}, rag_injected={rag_injected}")
            logger.info(f"RAG Details | injected_labels=SPAM:{spam_hits}/HAM:{ham_hits} | injected_ids={injected_ids}")
            
            content = self._query_llm(prompt)
            
            # LLM 응답 로그
            logger.debug(f"LLM 응답: {content[:300]}{'...' if len(content) > 300 else ''}")
            
            result = self._parse_response(content, os.getenv("LLM_PROVIDER", "OPENAI"))
            
            # 판정 결과 로그 (표준화된 형식)
            is_spam = result.get('is_spam')
            verdict = "SPAM" if is_spam else ("HITL" if is_spam is None else "HAM")
            logger.info(f"판정완료 | {verdict} | code={result.get('classification_code')} | prob={result.get('spam_probability')}")
            logger.info(f"  - Reason: {result.get('reason')}")
            
            return result
            
        except Exception as e:
            logger.exception("LLM 분석 중 오류 발생")
            return {"is_spam": False, "spam_probability": 0.0, "classification_code": None, "reason": "Error (LLM Fail)"}

    from typing import Callable, Awaitable, Optional

    async def acheck(self, message: str, stage1_result: dict, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> dict:
        """
        Stage 2: RAG + LLM (Async Version with Callbacks)
        """
        import asyncio
        loop = asyncio.get_running_loop()
        
        # 메시지 원문 로그 (DEBUG로 변경)
        logger.debug(f"분석 시작 (async) | msg={message[:80]}{'...' if len(message) > 80 else ''}")
        
        try:
            # 1. RAG Retrieval (guide + FN examples, Run in thread to avoid blocking)
            if status_callback:
                await status_callback("🧠 의도 파악 중...")
            
            # 0. Generate Intent Summary (Blocking LLM call in executor)
            intent_summary = await loop.run_in_executor(None, lambda: self.generate_intent_summary(message))
            logger.info(f"Intent Summary: {intent_summary[:120]}...")

            # 1. RAG Retrieval (guide + FN examples, Run in thread to avoid blocking)
            if status_callback:
                await status_callback("🔍 문맥 검색 중... (RAG + FN Examples)")
            
            context_data = await loop.run_in_executor(None, lambda: self._retrieve_context(message, intent_summary))
            
            # [Telemetry] Calculate Distance Metrics (Top 1/2 + Gap)
            rag_examples = context_data.get('rag_examples', [])
            d1, d2, gap = 9.9, 9.9, 0.0
            if len(rag_examples) >= 1:
                d1 = rag_examples[0].get('score', rag_examples[0].get('distance', 9.9))
                if len(rag_examples) >= 2:
                    d2 = rag_examples[1].get('score', rag_examples[1].get('distance', 9.9))
                    gap = d2 - d1
            logger.info(f"RAG Metrics | Top1={d1:.4f} | Top2={d2:.4f} | Gap={gap:.4f}")
            
            # 2. LLM Inference
            if status_callback:
                await status_callback("🧠 AI 정밀 분석 중...")
            
            logger.debug("Building prompt...")
            detected_pattern = stage1_result.get("detected_pattern", "None")
            prompt, valid_examples = self._build_prompt(message, detected_pattern, context_data)
            
            # [Telemetry] RAG Injection Stats
            rag_retrieved = len(rag_examples)
            rag_injected = len(valid_examples)
            has_guide = bool(context_data.get('guide_context'))

            # Label Distribution & IDs
            spam_hits = sum(1 for ex in valid_examples if ex.get('label') == 'SPAM')
            ham_hits = sum(1 for ex in valid_examples if ex.get('label') == 'HAM')
            injected_ids = [ex.get('id', 'unk') for ex in valid_examples]

            logger.info(f"프롬프트 생성 완료 | RAG Guide={'O' if has_guide else 'X'} | rag_retrieved={rag_retrieved}, rag_injected={rag_injected}")
            logger.info(f"RAG Details | injected_labels=SPAM:{spam_hits}/HAM:{ham_hits} | injected_ids={injected_ids}")
            
            logger.debug(f"Prompt built, length: {len(prompt)} chars")
            
            logger.debug("Calling LLM...")
            # Run blocking LLM call in executor
            content = await loop.run_in_executor(None, lambda: self._query_llm(prompt))
            
            # LLM 응답 로그
            logger.debug(f"LLM 응답: {content[:300]}{'...' if len(content) > 300 else ''}")
            
            result = self._parse_response(content, os.getenv("LLM_PROVIDER", "OPENAI"))
            
            # 판정 결과 로그 (표준화된 형식)
            is_spam = result.get('is_spam')
            verdict = "SPAM" if is_spam else ("HITL" if is_spam is None else "HAM")
            logger.info(f"판정완료 | {verdict} | code={result.get('classification_code')} | prob={result.get('spam_probability')}")
            logger.info(f"  - Reason: {result.get('reason')}")
            
            if status_callback:
                await status_callback(f"✅ 분석 완료 (판정: {verdict})")
                
            return result
            
        except Exception as e:
            logger.exception("Async LLM 분석 중 오류 발생")
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
                temperature=0.2  # 분류 작업에 적합한 낮은 temperature
            )
        elif provider == "CLAUDE":
            api_key = os.getenv("CLAUDE_API_KEY")
            return ChatAnthropic(
                model=self.model_name if "claude" in self.model_name else "claude-3-haiku-20240307",
                anthropic_api_key=api_key,
                temperature=0.2  # 분류 작업에 적합한 낮은 temperature
            )
        else: # OPENAI
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                temperature=0.2  # 분류 작업에 적합한 낮은 temperature
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
            final_content = ""
            if hasattr(response, 'content'):
                content = response.content
                if isinstance(content, list) and len(content) > 0:
                     # Handle list of blocks (e.g. Anthropic)
                     if isinstance(content[0], dict) and 'text' in content[0]:
                         final_content = content[0]['text']
                     else:
                         final_content = str(content) # Fallback if structure unknown
                else:
                    final_content = str(content) # Valid string
                
            elif isinstance(response, list) and len(response) > 0:
                 if isinstance(response[0], dict) and 'text' in response[0]:
                     final_content = response[0]['text']
                 elif hasattr(response[0], 'content'):
                     final_content = response[0].content
            else:
                 final_content = str(response)
            
            logger.info(f"Final Summary: {final_content}")
            return final_content

        except Exception as e:
            logger.error(f"Summary Generation Error: {e}")
            return "종합 결과 요약 생성 중 오류가 발생했습니다."

    def generate_intent_summary(self, message: str) -> str:
        """
        Public method to generate 'Judgement Semantic Unit' (Intent Summary).
        Used by main.py for saving RAG examples and internally for analysis.
        (Synchronous version for compatibility)
        """
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
        
        try:
            llm = self._get_chat_model()
            from langchain_core.messages import HumanMessage
            # Use invoke instead of ainvoke for synchronous execution
            response = llm.invoke([HumanMessage(content=prompt)])
            
            if hasattr(response, 'content'):
                content = response.content
                if isinstance(content, list) and len(content) > 0:
                     if isinstance(content[0], dict) and 'text' in content[0]:
                         return content[0]['text']
                     return str(content)
                return str(content)
            return str(response)

        except Exception as e:
            logger.error(f"Intent Summary Generation Error: {e}")
            return "Error generating intent summary"
