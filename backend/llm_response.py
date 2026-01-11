import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일 로드 (시스템 변수 무시하고 덮어쓰기)
load_dotenv(override=True)

# OPENAI_API_KEY 읽기
api_key = os.getenv("OPENAI_API_KEY")
print(api_key)

client = OpenAI(api_key=api_key)

response = client.responses.create(
    model="gpt-5-mini",
    input="Write a one-sentence bedtime story about a unicorn."
)

print(response.output_text)

