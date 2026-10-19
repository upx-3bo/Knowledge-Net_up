"""Simplest write-gate auth: a shared write password issues a stateless HMAC token.

- Browse (GET) is open to everyone.
- Write operations require a valid write token.
- The token is stateless: signed with a secret derived from the password, so no
  session store is needed. It expires after WRITE_TOKEN_TTL.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from fastapi import Header, HTTPException

from backend.config import WRITE_PASSWORD

TOKEN_TTL = int(os.getenv("WRITE_TOKEN_TTL", "43200"))  # seconds (12h)


def _secret() -> bytes:
    return hashlib.sha256(f"akn-write::{WRITE_PASSWORD}".encode("utf-8")).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(password: str) -> str:
    """Return a signed write token if the password matches, else None."""
    if not WRITE_PASSWORD or not hmac.compare_digest(password or "", WRITE_PASSWORD):
        return ""
    payload = f"{int(time.time())}|{os.urandom(6).hex()}".encode("utf-8")
    sig = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(sig)}"


def verify_token(token: str) -> bool:
    """Validate a write token (returns True/False, never raises)."""
    try:
        raw_payload, raw_sig = token.split(".")
        payload = _unb64(raw_payload)
        sig = _unb64(raw_sig)
        expected = hmac.new(_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return False
        ts = int(payload.split(b"|")[0])
        return (time.time() - ts) <= TOKEN_TTL
    except Exception:
        return False


def require_write_token(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: demand a valid write token for write endpoints."""
    token = ""
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="需要写入口令（登录后可写入）")
    return token
