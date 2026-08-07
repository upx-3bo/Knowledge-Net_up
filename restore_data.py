"""下载并解压/合并分块文件"""
import gzip, os, httpx

RAW = 'https://raw.githubusercontent.com/upx-3bo/Knowledge-Net_up/main'

GZIP_FILES = {
    'data/knowledge.db': ['data/knowledge.db.gz.part001', 'data/knowledge.db.gz.part002', 'data/knowledge.db.gz.part003'],
    'data_2026.json': ['data_2026.json.gz.part001', 'data_2026.json.gz.part002'],
}

MERGE_FILES = {
    'backend/routers/graph_viz.py': ['backend/routers/graph_viz.py.part001', 'backend/routers/graph_viz.py.part002'],
}

os.makedirs('data', exist_ok=True)
os.makedirs('backend/routers', exist_ok=True)

for out_path, parts in GZIP_FILES.items():
    print(f'下载 {out_path}...')
    compressed = b''
    for part in parts:
        r = httpx.get(f'{RAW}/{part}', timeout=60)
        r.raise_for_status()
        compressed += r.content
    with open(out_path, 'wb') as f:
        f.write(gzip.decompress(compressed))
    print(f'  -> {out_path} ({os.path.getsize(out_path)//1024}KB)')

for out_path, parts in MERGE_FILES.items():
    print(f'合并 {out_path}...')
    data = b''
    for part in parts:
        r = httpx.get(f'{RAW}/{part}', timeout=60)
        r.raise_for_status()
        data += r.content
    with open(out_path, 'wb') as f:
        f.write(data)
    print(f'  -> {out_path} ({os.path.getsize(out_path)//1024}KB)')

print('完成！')
