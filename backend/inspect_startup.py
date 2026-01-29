
import time
import logging
import sys
import os

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def measure_time(description, func):
    start_time = time.time()
    logger.info(f"⏳ [START] {description}...")
    try:
        func()
    except Exception as e:
        logger.error(f"❌ [ERROR] {description} failed: {e}")
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"✅ [DONE]  {description} took {duration:.2f} seconds")
    return duration

def test_imports():
    logger.info("🚀 Starting Startup Diagnosis...")
    
    # 1. Environment Variables
    def load_env():
        from dotenv import load_dotenv
        load_dotenv(override=True)
    measure_time("Loading .env", load_env)
    
    # 2. RuleBasedFilter
    def init_rule_filter():
        try:
            # Found in backend/app/services/rule_service.py
            from app.services.rule_service import RuleBasedFilter
            _ = RuleBasedFilter()
        except ImportError:
            logger.warning("Could not import RuleBasedFilter. Skipping.")
    measure_time("Importing & Initializing RuleBasedFilter", init_rule_filter)

    # 3. ContentAnalysisAgent
    def init_content_agent():
        from app.agents.content_agent.agent import ContentAnalysisAgent
        _ = ContentAnalysisAgent()
    measure_time("Importing & Initializing ContentAnalysisAgent", init_content_agent)

    # 4. UrlAnalysisAgent
    def init_url_agent():
        from app.agents.url_agent.agent import UrlAnalysisAgent
        _ = UrlAnalysisAgent()
    measure_time("Importing & Initializing UrlAnalysisAgent", init_url_agent)
    
    # 5. IBSEAgentService
    def init_ibse_service():
        from app.agents.ibse_agent.service import IBSEAgentService
        _ = IBSEAgentService()
    measure_time("Importing & Initializing IBSEAgentService", init_ibse_service)

    # 6. SpamRagService
    def init_spam_rag():
        from app.services.spam_rag_service import get_spam_rag_service
        _ = get_spam_rag_service()
    measure_time("Importing & Initializing SpamRagService", init_spam_rag)

    logger.info("🏁 Diagnosis Completed.")

if __name__ == "__main__":
    # Add backend directory to sys.path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    test_imports()
