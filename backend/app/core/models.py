"""
Spam Detector - LLM 모델 리스트 정의
====================================
지원 가능한 모델 공급자별 모델 목록을 중앙화하여 관리합니다.
"""

# 모델 공급자 리스트
LLM_PROVIDERS = ["GEMINI", "OPENAI", "CLAUDE"]

# 공급자별 모델 상세 리스트
# name: UI에 표시될 이름
# id: .env의 LLM_MODEL에 설정될 실제 값
LLM_MODELS = {
    "GEMINI": [
        {"name": "Gemini 3.0 Flash Preview (Recommended)", "id": "gemini-3-flash-preview"},
        {"name": "Gemini 3.1 Flash-Lite (Preview)", "id": "gemini-3.1-flash-lite-preview"},
    ],
    "OPENAI": [
        {"name": "GPT-5-mini", "id": "gpt-5-mini"},
        {"name": "GPT-5-nano", "id": "gpt-5-nano"},
    ],
    "CLAUDE": [
        {"name": "Claude Haiku 4.5", "id": "claude-haiku-4-5"},
    ]
}

# 기본 설정값 리스트 (UI 폼 구성용)
CONFIG_METADATA = [
    {"key": "LLM_PROVIDER", "label": "LLM 공급자", "description": "사용할 AI 엔진 브랜드", "type": "select", "options": LLM_PROVIDERS},
    {"key": "LLM_MODEL", "label": "분석 모델", "description": "사용할 실제 AI 모델 버전", "type": "model_select"},
    {"key": "LLM_SUB_MODEL", "label": "예비 분석 모델(타임아웃 시)", "description": "응답 지연 시 전환할 가장 빠른 임시 모델", "type": "select", "options": ["gemini-3.1-flash-lite-preview", "gemini-2.5-flash"]},
    {"key": "LLM_BATCH_SIZE", "label": "LLM 배치 사이즈", "description": "한 번에 처리할 메시지 수", "type": "number", "min": 1, "max": 100},
    {"key": "SPAM_RAG_ENABLED", "label": "유사 사례 참고(RAG)", "description": "과거 스팸 사례 정보를 함께 분석에 활용", "type": "boolean"},
    {"key": "RAG_DISTANCE_THRESHOLD", "label": "RAG 유사도 임계치", "description": "얼마나 비슷한 사례만 가져올지 결정", "type": "float", "step": 0.05, "min": 0, "max": 1.0},
    {"key": "MAX_BROWSER_CONCURRENCY", "label": "URL 동시 분석 수", "description": "브라우저 동시 실행 최대 개수", "type": "number", "min": 1, "max": 50},
    {"key": "ALPHANUMERIC_OBFUSCATION_RATIO_THRESHOLD", "label": "난독화 의심 비율", "description": "스팸 필터링 엄격도 조절", "type": "float", "step": 0.05, "min": 0, "max": 1.0},
    {"key": "LOG_LEVEL_CONSOLE", "label": "콘솔 로그 레벨", "description": "화면에 표시할 로그 상세 수위", "type": "select", "options": ["DEBUG", "INFO", "WARNING", "ERROR"]},
    {"key": "MIN_MESSAGE_LENGTH", "label": "최소 분석 길이", "description": "이 길이보다 짧은 메시지는 분석에서 제외(SKIP)", "type": "number", "min": 0, "max": 100},
]
