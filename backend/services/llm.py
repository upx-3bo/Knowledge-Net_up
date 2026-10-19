"""OpenAI-compatible chat client (DeepSeek / etc.)."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from backend.config import LLM_API_KEY, LLM_API_URL, LLM_MODEL


class LLMNotConfigured(RuntimeError):
    pass


# 瞬时性错误码：服务过载 / 限流时短暂等待后重试
_TRANSIENT = (429, 500, 502, 503, 504)


def _post_chat(url: str, headers: dict, payload: dict, timeout: float, max_retries: int = 2):
    """POST 到 OpenAI 兼容接口，遇瞬时错误（429/5xx/网络超时）退避重试。"""
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout, verify=False) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in _TRANSIENT and attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except httpx.RequestError as exc:
            last_err = exc
            if attempt >= max_retries:
                raise
            time.sleep(2 * (attempt + 1))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in _TRANSIENT and attempt < max_retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise last_err


def llm_ready() -> bool:
    key = (LLM_API_KEY or "").strip()
    return bool(key) and key not in {"your_deepseek_api_key_here", "changeme"}


def chat_json(prompt: str, *, timeout: float = 300.0) -> dict[str, Any]:
    if not llm_ready():
        raise LLMNotConfigured("LLM_API_KEY 未配置：请在项目根目录 .env 中填写后重启 API")

    url = f"{LLM_API_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    resp = _post_chat(url, headers, payload, timeout)
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM 返回非 JSON: {content[:400]}") from exc

def chat_text(prompt: str, *, timeout: float = 180.0) -> str:
    if not llm_ready():
        raise LLMNotConfigured("LLM_API_KEY 未配置：请在项目根目录 .env 中填写后重启 API")

    url = f"{LLM_API_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    resp = _post_chat(url, headers, payload, timeout)
    data = resp.json()
    return str(data["choices"][0]["message"]["content"] or "").strip()
