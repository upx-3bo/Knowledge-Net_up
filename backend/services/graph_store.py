import os


def get_store():
    """根据 KNOWLEDGE_ENGINE 环境变量返回图存储实例.
    - 'nebula' : 使用 NebulaGraph（需要 NEBULA_HOST/PORT 等环境变量）
    - 其他/默认 : SQLite 本地引擎
    """
    engine = os.getenv("KNOWLEDGE_ENGINE", "sqlite").lower()

    if engine == "nebula":
        from backend.services.nebula_store import NebulaKnowledgeStore
        store = NebulaKnowledgeStore()
        store.connect()
        return store

    from backend.services.knowledge_base import KnowledgeBase
    return KnowledgeBase()


def close_store(store):
    if hasattr(store, "close"):
        try:
            store.close()
        except Exception:
            pass
