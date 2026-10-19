"""Minimal Nebula session helper for AI4KnowledgeNet."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

from backend.config import (
    NEBULA_HOST,
    NEBULA_PASSWORD,
    NEBULA_PORT,
    NEBULA_SPACE,
    NEBULA_USER,
)


class NebulaError(RuntimeError):
    pass


class NebulaClient:
    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None

    def connect(self) -> None:
        if self._pool is not None:
            return
        cfg = Config()
        cfg.max_connection_pool_size = 8
        pool = ConnectionPool()
        ok = pool.init([(NEBULA_HOST, NEBULA_PORT)], cfg)
        if not ok:
            raise NebulaError(f"cannot connect Nebula at {NEBULA_HOST}:{NEBULA_PORT}")
        self._pool = pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    @contextmanager
    def session(self, use_space: bool = True) -> Iterator:
        self.connect()
        assert self._pool is not None
        sess = self._pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
        try:
            if use_space:
                self._run(sess, f"USE {NEBULA_SPACE};")
            yield sess
        finally:
            sess.release()

    def execute(self, nql: str, use_space: bool = True):
        with self.session(use_space=use_space) as sess:
            return self._run(sess, nql)

    @staticmethod
    def _run(sess, nql: str):
        resp = sess.execute(nql)
        if not resp.is_succeeded():
            raise NebulaError(f"{resp.error_msg()}\n--- nGQL ---\n{nql}")
        return resp


_client: NebulaClient | None = None


def get_client() -> NebulaClient:
    global _client
    if _client is None:
        _client = NebulaClient()
    return _client
