import os
import json
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("SignatureRefiner-LLM")
logger.setLevel(logging.INFO)

class LLMAnalyzer:
    def __init__(self, api_key: str = None):
        self._custom_api_key = api_key
        self.current_key = None
        self._init_llm()
        self.guide_content = self._load_guide()

    def _init_llm(self, failed_key: str = None):
        key = self._custom_api_key
        
        if not key:
            try:
                from app.core.llm_manager import key_manager
                # 만약 failed_key가 전달되었다면 로테이션 먼저 수행
                if failed_key:
                    is_rotated = key_manager.rotate_key("GEMINI", failed_key=failed_key)
                    if not is_rotated:
                        logger.error("[SignatureRefiner-LLM] 모든 GEMINI 키 고갈!")
                key = key_manager.get_key("GEMINI")
            except ImportError:
                key = os.getenv("GOOGLE_API_KEY")

        if not key:
             from dotenv import load_dotenv
             env_path = os.path.join(os.path.dirname(__file__), "../../../../.env")
             load_dotenv(env_path)
             key = os.getenv("GOOGLE_API_KEY")

        if not key:
             raise ValueError("GOOGLE_API_KEY environment variable is not set. Please check your .env file or LLM Settings.")
        
        self.current_key = key
        # 사용자가 .env에 지정한 모델명 사용, 없으면 최후의 수단으로 1.5 사용
        raw_model_name = os.getenv("LLM_MODEL", "gemini-1.5-flash")
        model_name = raw_model_name.strip("'").strip('"')
        
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=key,
            temperature=0.0,
            max_retries=0  # 내부 재시도를 끄고 자체 로테이션 로직 사용
        )

    def _load_guide(self) -> str:
        # Load the signature_spam_guide.md
        guide_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "../../../data/signature_spam_guide.md"
        ))
        try:
            with open(guide_path, "r", encoding="utf-8") as f:
                 return f.read()
        except Exception:
            return "Rule: Extract unique spam signature. Must be 9~20 or 39~40 bytes."

    def get_system_prompt(self) -> str:
        return (
            "너는 스팸 시그니처 자동 정제기(Signature Refiner)이다.\n"
            "여러 유사(파편화된) 메시지에서 **반드시 100% 공통으로 포함되는 교집합 구역**만을 찾아 단 1개의 완벽한 대표 시그니처를 만들어야 한다.\n\n"
            f"=== [스팸 시그니처 추출 가이드] ===\n{self.guide_content}\n\n"
            "=== [추가 절대/핵심 규칙] ===\n"
            "0. **[기존 보유 시그니처 우선 채택]** 주어진 메시지들의 `기존 추출된 시그니처` 후보군들을 가장 먼저 평가하라. 그 중 하나가 가이드라인에 완벽히 부합하면서 전체 문서를 포괄할 수 있는 뛰어난 대표성과 유니크함을 가졌다면, 무리해서 완전히 새로운 시그니처를 밑바닥부터 추출하지 말고 그 우수한 '기존 시그니처' 중 하나를 대표로 채택하라!\n"
            "1. 뽑혀진 대표 시그니처는 제공된 모든 메시지의 원문(공백제거 형태 포함)에 100% 매치되어야 한다. (가변되는 변수는 절대 포함불가)\n"
            "2. **[유니크함 훼손 금지]** 공통점을 찾기 위해 과도하게 메시지를 깎아내서, '안녕하세요', '감사합니다' 와 같은 평범한 일상 단어가 대표 시그니처로 도출될 상황이라면 **절대로 억지로 추출하지 마라!**\n"
            "3. 유니크함을 잃을 바에야 차라리 추출을 포기하고 `\"decision\": \"unextractable\"`을 출력해라. 시스템이 이를 감지하여 [기존 시그니처 유지] 모드로 Fallback 할 것이다.\n"
            "4. 반드시 스팸만의 강렬하고 고유한(Unique) 텍스트/도메인만이 시그니처의 자격이 있다.\n"
            "5. 답변은 반드시 아래 형식의 JSON Object로만 응답하라.\n"
        )

    async def analyze_cluster(self, cluster_items: list) -> dict:
        """
        cluster_items: list of dicts [{'log_id': '..', 'message': '..', 'current_signature': '..'}]
        """
        messages_text = ""
        for i, item in enumerate(cluster_items):
             messages_text += f"--- [Message {i+1}] ---\n{item['message']}\n"
             messages_text += f"> 기존 추출된 시그니처: {item['current_signature']}\n\n"

        human_prompt = (
             "아래는 텍스트 유사도가 85% 이상인 동종 스팸 템플릿 그룹이다.\n"
             "각각 서로 다른 시그니처가 뽑혀서 파편화되어 있다. 모든 메시지에 공통으로 적용될 '하나의 대표 시그니처'를 도출하라.\n\n"
             f"{messages_text}\n\n"
             "가이드라인 조건과 '유니크함 훼손 금지' 원칙을 지킬 수 있다면 아래 JSON 형태로 답하라:\n"
             "{\n"
             '  "decision": "extracted",\n'
             '  "signature": "추출한 대표 시그니처",\n'
             '  "reason": "왜 이 문자열을 공통으로 채택했는지 설명"\n'
             "}\n\n"
             "만약 공통 영역에서 유니크함을 찾을 수 없어 평범한 문구가 나온다면 추출을 포기하고 아래처럼 답하라:\n"
             "{\n"
             '  "decision": "unextractable",\n'
             '  "signature": "",\n'
             '  "reason": "공통 영역 추출 시 유니크함이 훼손되므로 기존 값을 유지하기 위해 포기함"\n'
             "}"
        )
        
        messages = [
             SystemMessage(content=self.get_system_prompt()),
             HumanMessage(content=human_prompt)
        ]
        
        try:
            from app.core.llm_manager import key_manager
            keys_pool_size = max(1, len(key_manager._keys_pool.get("GEMINI", [])))
        except:
            keys_pool_size = 1

        last_err = None
        for attempt in range(keys_pool_size):
            try:
                 logger.debug(f">> LLM 분석 요청 전송 중... (Attempt {attempt+1}/{keys_pool_size})")
                 try:
                     res = await self.llm.ainvoke(messages)
                 except Exception as inner_e:
                     inner_err = str(inner_e).lower()
                     # 429 에러는 기존처럼 바깥 루프에서 키를 로테이션하게 위로 패스합니다.
                     if any(kw in inner_err for kw in ["quota", "429", "resource exhausted", "too many requests"]):
                         raise inner_e
                     
                     # 404 (NOT_FOUND)나 다른 접근 에러일 경우 운영자님 지시대로 안전히 2.5-flash로 폴백
                     logger.warning(f"[Fallback] 모델 예측 실패({inner_e}). 'gemini-2.5-flash' 모델로 즉시 우회 재시도합니다.")
                     fallback_llm = ChatGoogleGenerativeAI(
                         model="gemini-2.5-flash",
                         google_api_key=self.current_key,
                         temperature=0.0,
                         max_retries=0
                     )
                     res = await fallback_llm.ainvoke(messages)
                     
                 raw_content = res.content or ""
                 if isinstance(raw_content, list) and raw_content:
                     first = raw_content[0]
                     if isinstance(first, dict) and first.get("type") == "text":
                         raw_content = first.get("text", "")
                     elif isinstance(first, str):
                         raw_content = first
                     else:
                         raw_content = str(raw_content)
                 elif not isinstance(raw_content, str):
                     raw_content = str(raw_content)
                     
                 content = raw_content.strip()
                 content = content.replace("```json", "").replace("```", "").strip()
                 parsed = json.loads(content)
                 
                 # 스팸 시그니처 가이드라인 강제 보완 (모든 공백 제거)
                 if parsed.get("signature"):
                     parsed["signature"] = parsed["signature"].replace(" ", "")
                     
                 logger.debug(f"<< LLM 응답 해석 완료: {parsed.get('decision')} | {parsed.get('signature')}")
                 try:
                     from app.core.llm_manager import key_manager
                     key_manager.report_success("GEMINI")
                 except:
                     pass
                 
                 return parsed
                 
            except Exception as e:
                 error_msg = str(e).lower()
                 last_err = e
                 is_quota_error = any(kw in error_msg for kw in ["quota", "429", "resource exhausted", "too many requests"])
                 
                 if is_quota_error and attempt < keys_pool_size - 1:
                     logger.warning(f"!! LLM API 한도 초과 오류(429) 감지. 키 로테이션 시도 중...")
                     self._init_llm(failed_key=self.current_key)
                     continue
                 else:
                     logger.error(f"!! LLM 분석 에러 발생 (최종): {e}")
                     break
        
        return {
             "decision": "error",
             "signature": "",
             "reason": f"LLM error: {str(last_err)}"
        }
