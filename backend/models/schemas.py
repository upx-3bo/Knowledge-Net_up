from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TechnologyCreate(BaseModel):
    name: str
    description: str = ""
    trl: int = 1
    status: str = "active"
    keywords: str = ""
    category: str = ""


class TechnologyOut(BaseModel):
    vid: str
    name: str
    description: str
    trl: int
    status: str
    keywords: str


class CategoryCreate(BaseModel):
    name: str
    level: int = 0
    description: str = ""
    parent: Optional[str] = None


class CategoryOut(BaseModel):
    vid: str
    name: str
    level: int
    description: str


class StandardCreate(BaseModel):
    name: str
    code: str
    organization: str = ""
    type: str = ""
    publish_year: Optional[int] = None
    description: str = ""


class PatentCreate(BaseModel):
    title: str
    number: str
    applicant: str = ""
    inventors: str = ""
    abstract: str = ""
    apply_date: str = ""
    status: str = ""


class ResourceCreate(BaseModel):
    name: str
    type: str
    description: str = ""
    contact: str = ""
    link: str = ""
    department: str = ""


class DocumentUpload(BaseModel):
    title: str
    file_type: str = "pdf"
    content: str = ""
    summary: str = ""
    source: str = ""
    auto_extract: bool = True
    target_technology: Optional[str] = None


class RelationCreate(BaseModel):
    edge_type: str
    src_vid: str
    dst_vid: str
    props: dict = {}


class IntelligenceSource(BaseModel):
    url: str = ""
    keywords: str = ""
    source_type: str = "patent"
