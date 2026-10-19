import os
from pathlib import Path

from dotenv import load_dotenv

# 始终从项目根加载 .env（避免 WSL/工作目录不一致读不到）
_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env", override=False)

NEBULA_HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
NEBULA_PORT = int(os.getenv("NEBULA_PORT", "9669"))
NEBULA_USER = os.getenv("NEBULA_USER", "root")
NEBULA_PASSWORD = os.getenv("NEBULA_PASSWORD", "")
NEBULA_SPACE = os.getenv("NEBULA_SPACE", "auto_innovation_kg")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.deepseek.com/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

WRITE_PASSWORD = os.getenv("WRITE_PASSWORD", "")
