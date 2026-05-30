import os, json

root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
out_dir = os.path.dirname(__file__)

map_data = {}

for dirpath, dirnames, filenames in os.walk(root):
    # 跳过 Supports 和 __pycache__
    dirnames[:] = [d for d in dirnames if d not in ('Supports', '__pycache__')]
    
    for f in filenames:
        if f.endswith('.pyc'):
            continue
        full = os.path.join(dirpath, f)
        rel = os.path.relpath(full, root).replace('\\', '/')
        ext = os.path.splitext(f)[1] or '(no ext)'
        map_data[rel] = {
            'type': 'file',
            'ext': ext,
            'size': os.path.getsize(full),
            'path': rel
        }

# 按层级排序
sorted_data = dict(sorted(map_data.items(), key=lambda x: (x[1]['path'].count('/'), x[1]['path'])))

out = {
    'project': 'Kval',
    'root': 'Kval',
    'files': sorted_data,
    'total_files': len(sorted_data)
}

out_path = os.path.join(out_dir, 'project_structure.map')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

print(f'Generated map with {len(sorted_data)} files -> {out_path}')
