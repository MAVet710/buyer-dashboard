import os
from openai import OpenAI



def get_llm_client() -> OpenAI:
    base_url = os.getenv("OLLAMA_OPENAI_BASE_URL", "http://localhost:11434/v1")
    api_key = os.getenv("OLLAMA_API_KEY", "ollama")
    return OpenAI(base_url=base_url, api_key=api_key)


def get_chat_model() -> str:
    return os.getenv("OLLAMA_CHAT_MODEL", "llama3.1")
