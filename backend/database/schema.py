from backend.database.nebula_client import get_client


TAG_DEFINITIONS = [
    {
        "name": "category",
        "props": [
            ("name", "string"),
            ("level", "int"),
            ("description", "string"),
        ]
    },
    {
        "name": "technology",
        "props": [
            ("name", "string"),
            ("description", "string"),
            ("trl", "int"),
            ("status", "string"),
            ("keywords", "string"),
            ("created_at", "datetime"),
            ("updated_at", "datetime"),
        ]
    },
    {
        "name": "component",
        "props": [
            ("name", "string"),
            ("function", "string"),
            ("specifications", "string"),
            ("manufacturer", "string"),
        ]
    },
    {
        "name": "standard",
        "props": [
            ("name", "string"),
            ("code", "string"),
            ("organization", "string"),
            ("type", "string"),
            ("publish_year", "int"),
            ("description", "string"),
        ]
    },
    {
        "name": "patent",
        "props": [
            ("title", "string"),
            ("number", "string"),
            ("applicant", "string"),
            ("inventors", "string"),
            ("abstract", "string"),
            ("apply_date", "string"),
            ("status", "string"),
        ]
    },
    {
        "name": "resource",
        "props": [
            ("name", "string"),
            ("type", "string"),
            ("description", "string"),
            ("contact", "string"),
            ("link", "string"),
            ("department", "string"),
        ]
    },
    {
        "name": "document",
        "props": [
            ("title", "string"),
            ("file_type", "string"),
            ("summary", "string"),
            ("content", "string"),
            ("source", "string"),
            ("uploaded_at", "datetime"),
        ]
    },
]

EDGE_DEFINITIONS = [
    {
        "name": "belongs_to",
        "props": [("weight", "double")],
        "description": "technology -> category"
    },
    {
        "name": "contains",
        "props": [("weight", "double")],
        "description": "category -> category (parent-child)"
    },
    {
        "name": "relates_to",
        "props": [("relation_type", "string"), ("weight", "double")],
        "description": "technology -> technology"
    },
    {
        "name": "has_standard",
        "props": [("compliance_level", "string")],
        "description": "technology -> standard"
    },
    {
        "name": "has_patent",
        "props": [("relevance", "double")],
        "description": "technology -> patent"
    },
    {
        "name": "references",
        "props": [("relevance", "double")],
        "description": "technology -> resource"
    },
    {
        "name": "implements",
        "props": [("status", "string")],
        "description": "product -> technology"
    },
    {
        "name": "depends_on",
        "props": [("description", "string")],
        "description": "technology -> component"
    },
    {
        "name": "derived_from",
        "props": [("source_type", "string")],
        "description": "document -> source_vertex"
    },
]

SPACE_NQL = f"""
CREATE SPACE IF NOT EXISTS auto_knowledge(
    vid_type = FIXED_STRING(256),
    partition_num = 10,
    replica_factor = 1
);
USE auto_knowledge;
"""

TAG_NQLS = []
for tag in TAG_DEFINITIONS:
    props_str = ", ".join(f"{p[0]} {p[1]}" for p in tag["props"])
    TAG_NQLS.append(f"CREATE TAG IF NOT EXISTS {tag['name']}({props_str});")

EDGE_NQLS = []
for edge in EDGE_DEFINITIONS:
    props_str = ", ".join(f"{p[0]} {p[1]}" for p in edge["props"]) if edge["props"] else ""
    if props_str:
        EDGE_NQLS.append(f"CREATE EDGE IF NOT EXISTS {edge['name']}({props_str});")
    else:
        EDGE_NQLS.append(f"CREATE EDGE IF NOT EXISTS {edge['name']}();")

CREATE_TAG_INDEX_NQLS = [
    "CREATE TAG INDEX IF NOT EXISTS idx_technology_name ON technology(name);",
    "CREATE TAG INDEX IF NOT EXISTS idx_category_name ON category(name);",
    "CREATE TAG INDEX IF NOT EXISTS idx_standard_code ON standard(code);",
    "CREATE TAG INDEX IF NOT EXISTS idx_patent_number ON patent(number);",
    "CREATE TAG INDEX IF NOT EXISTS idx_document_title ON document(title);",
]


def init_schema():
    client = get_client()
    client.execute(SPACE_NQL)
    for nql in TAG_NQLS:
        client.execute(nql)
    for nql in EDGE_NQLS:
        client.execute(nql)
    for nql in CREATE_TAG_INDEX_NQLS:
        client.execute(nql)
    return True
