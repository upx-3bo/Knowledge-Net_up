from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TagName = Literal["vehicle", "domain", "subdomain", "module", "technology", "material"]
EdgeName = Literal["belongs_to", "supports", "relates_to"]


class VertexCreate(BaseModel):
    tag: TagName
    vid: str | None = Field(default=None, description="可选；不填则自动生成")
    props: dict[str, Any] = Field(default_factory=dict)


class VertexUpdate(BaseModel):
    props: dict[str, Any]


class EdgeCreate(BaseModel):
    edge_type: EdgeName
    src_vid: str
    dst_vid: str
    props: dict[str, Any] = Field(default_factory=dict)


class EdgeDelete(BaseModel):
    edge_type: EdgeName
    src_vid: str
    dst_vid: str
