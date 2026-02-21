from langchain_ollama import ChatOllama
from app.config.settings import MODEL

llm = ChatOllama(
    model=MODEL,
    temperature=0.0
)