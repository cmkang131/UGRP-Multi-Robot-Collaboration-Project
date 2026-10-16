import hashlib, json, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1]); man = []
for p in sorted(root.rglob('*')):
    if p.is_file() and p.suffix in ('.json', '.jsonl') and p.stat().st_size > 65536:
        data = p.read_bytes(); h = hashlib.sha256(data).hexdigest()
        z = p.with_name(p.name + '.zst')
        subprocess.run(['zstd', '-q', '-19', '-f', str(p), '-o', str(z)], check=True)
        back = subprocess.check_output(['zstd', '-qdc', str(z)])
        assert hashlib.sha256(back).hexdigest() == h, p
        man.append(dict(path=str(p.relative_to(root)), bytes=len(data), sha256=h, zst_sha256=hashlib.sha256(z.read_bytes()).hexdigest()))
        p.unlink()
(root/'COMPRESSED.json').write_text(json.dumps(man, indent=1) + '\n')
print(root.name, len(man), sum(m['bytes'] for m in man))
