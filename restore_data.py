"""下载并解压 gzip 分块数据文件"""
import gzip, os, httpx

# GitHub Raw URL 前缀
RAW = 'https://raw.githubusercontent.com/upx-3bo/Knowledge-Net_up/main'

FILES = {
    'data/knowledge.db': ['data/knowledge.db.gz.part001', 'data/knowledge.db.gz.part002', 'data/knowledge.db.gz.part003'],
    'data_2026.json': ['data_2026.json.gz.part001', 'data_2026.json.gz.part002'],
}

os.makedirs('data', exist_ok=True)
for out_path, parts in FILES.items():
    print(f'下载 {out_path}...')
    compressed = b''
    for part in parts:
        r = httpx.get(f'{RAW}/{part}', timeout=60)
        r.raise_for_status()
        compressed += r.content
        print(f'  {part}: {len(r.content)//1024}KB')
    with open(out_path, 'wb') as f:
        f.write(gzip.decompress(compressed))
    print(f'  -> {out_path} ({os.path.getsize(out_path)//1024}KB)')

print('完成！')
