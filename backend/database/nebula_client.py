from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config
from backend.config import NEBULA_HOST, NEBULA_PORT, NEBULA_USER, NEBULA_PASSWORD, NEBULA_SPACE


class NebulaClient:
    def __init__(self):
        self.pool = None
        self.session = None

    def connect(self):
        config = Config()
        config.max_connection_pool_size = 10
        self.pool = ConnectionPool()
        addr = (NEBULA_HOST, NEBULA_PORT)
        if not self.pool.init([addr], config):
            raise Exception("NebulaGraph connection pool init failed")
        self.session = self.pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
        self.session.execute(f"USE {NEBULA_SPACE};")
        return self

    def close(self):
        if self.session:
            self.session.release()
        if self.pool:
            self.pool.close()

    def execute(self, nql):
        return self.session.execute(nql)

    def execute_json(self, nql):
        return self.session.execute_json(nql)

    def query(self, nql):
        result = self.session.execute(nql)
        if result.is_succeeded():
            return result.as_data()
        return []

    def insert_vertex(self, tag, vid, props):
        props_str = ", ".join(f"{k}: {v!r}" if isinstance(v, str) else f"{k}: {v}" for k, v in props.items())
        nql = f"INSERT VERTEX {tag}({', '.join(props.keys())}) VALUES '{vid}': ({props_str});"
        return self.execute(nql)

    def insert_edge(self, edge_type, src, dst, props=None):
        if props:
            props_str = ", ".join(f"{k}: {v!r}" if isinstance(v, str) else f"{k}: {v}" for k, v in props.items())
            nql = f"INSERT EDGE {edge_type}({', '.join(props.keys())}) VALUES '{src}' -> '{dst}': ({props_str});"
        else:
            nql = f"INSERT EDGE {edge_type}() VALUES '{src}' -> '{dst}': ();"
        return self.execute(nql)


_client = None


def get_client():
    global _client
    if _client is None:
        _client = NebulaClient().connect()
    return _client
