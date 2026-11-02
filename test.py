import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv("backend/.env")
api_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("API_KEY")
if not api_key:
    raise RuntimeError("AZURE_OPENAI_API_KEY is missing")

model = ChatOpenAI(
    model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
    api_key=api_key,
    base_url=os.getenv(
        "AZURE_OPENAI_CHAT_ENDPOINT",
        "https://vineesh-ai-uae-resource.services.ai.azure.com/openai/v1",
    ),
    temperature=0.5,
)

for chunk in model.stream("Hello! How are you?"):
    if chunk.content:
        print(chunk.content, end="", flush=True)

print("\nTest completed.")
