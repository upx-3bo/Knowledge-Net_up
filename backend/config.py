import os
from dotenv import load_dotenv

load_dotenv()

NEBULA_HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
NEBULA_PORT = int(os.getenv("NEBULA_PORT", "9669"))
NEBULA_USER = os.getenv("NEBULA_USER", "root")
NEBULA_PASSWORD = os.getenv("NEBULA_PASSWORD", "nebula")
NEBULA_SPACE = "auto_knowledge"

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
