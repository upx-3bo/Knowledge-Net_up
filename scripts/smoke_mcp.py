#!/usr/bin/env python3
"""Direct smoke test of MCP tool functions (no stdio client)."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("NEBULA_HOST", "127.0.0.1")
os.environ.setdefault("NEBULA_PORT", "9669")
os.environ.setdefault("NEBULA_USER", "root")
os.environ.setdefault("NEBULA_PASSWORD", "")
os.environ.setdefault("NEBULA_SPACE", "auto_innovation_kg")

from mcp_server.server import (  # noqa: E402
    kg_add_relation,
    kg_add_technology,
    kg_get_node,
    kg_schema,
    kg_search,
    kg_stats,
    kg_subgraph,
)


def main() -> None:
    print("stats:", kg_stats())
    print("schema:", kg_schema())
    print("search:", kg_search("示例"))
    print("node:", kg_get_node(name="示例技术点"))
    print("subgraph:", kg_subgraph(name="示例技术点", depth=1)[:300], "...")
    print(
        "add_tech:",
        kg_add_technology(
            name="MCP冒烟技术点",
            domain_name="示例领域",
            subdomain_name="示例子域",
            description="mcp smoke",
            keywords="mcp",
            status="draft",
        ),
    )
    print(
        "relate:",
        kg_add_relation(
            src_name="MCP冒烟技术点",
            dst_name="示例技术点",
            edge_type="relates_to",
            relation_type="smoke",
            weight=0.5,
        ),
    )
    print("SMOKE MCP OK")


if __name__ == "__main__":
    main()
