import json, hashlib
from pathlib import Path

BASE = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\loads")
OUT = BASE / "_file_tracking.json"
TEXT_EXT = {'.py', '.json', '.js', '.ts', '.md', '.txt', '.csv', '.yaml', '.yml', '.toml', '.html', '.css'}
BINARY_SKIP = {'.png', '.jpg', '.jpeg', '.gif', '.mp4', '.rar', '.pdf', '.db', '.sqlite', '.sqlite-wal', '.sqlite-shm'}

files = []
for root, dirs, filenames in os.walk(BASE):
    root_path = Path(root)
    dirs[:] = [d for d in dirs if not any(c in d for c in ['{', '}', '<', '>', '"', '|', '\n', '\r'])]
    for name in sorted(filenames):
        p = root_path / name
        rel = p.relative_to(BASE)
        ext = p.suffix.lower()
        if ext in BINARY_SKIP:
            continue
        if any(c in str(rel) for c in ['{', '}', '<', '>', '"', '|', '\n', '\r']):
            continue
        try:
            stat = p.stat()
            h = hashlib.sha256(usedforsecurity=False)
            if ext in TEXT_EXT:
                h.update(p.read_bytes())
            else:
                h.update(f"{rel}:{stat.st_size}:{stat.st_mtime_ns}".encode())
            files.append({
                'path': str(rel),
                'bytes': stat.st_size,
                'mtime_ns': stat.st_mtime_ns,
                'sha256': h.hexdigest()[:16],
                'text': ext in TEXT_EXT,
            })
        except Exception:
            continue

manifest = {
    'root': str(BASE),
    'count': len(files),
    'files': sorted(files, key=lambda x: x['path']),
}
OUT.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
print('wrote', OUT, 'count=', len(files))
