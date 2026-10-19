"""Check Nebula connectivity and space stats."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.store import GraphStore  # noqa: E402


def main() -> None:
    store = GraphStore()
    print("ping:", store.ping())
    print("stats:", store.stats())


if __name__ == "__main__":
    main()
