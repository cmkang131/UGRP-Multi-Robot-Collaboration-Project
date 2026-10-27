"""Hash and archive only this completed diagnostic's new evidence root."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/home/ugrp/ugrp-sim/runs/pair-gpu-scoped-20261027')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    archive = ROOT.parent/(ROOT.name+'.tar.gz')
    manifest = ROOT/'RETRIEVAL_MANIFEST.json'
    if archive.exists() or manifest.exists():
        raise ValueError('new retrieval archive/manifest required')
    files = {}
    for path in sorted(ROOT.rglob('*')):
        if path.is_symlink():
            target = os.readlink(path)
            files[str(path.relative_to(ROOT))] = dict(kind='symlink', target=target,
                sha256=hashlib.sha256(os.fsencode(target)).hexdigest())
        elif path.is_file():
            files[str(path.relative_to(ROOT))] = dict(kind='file', bytes=path.stat().st_size, sha256=digest(path))
    with manifest.open('x') as stream:
        json.dump(dict(utc=datetime.now(timezone.utc).isoformat(), root=str(ROOT), files=files), stream, indent=2)
    subprocess.run(['tar', '-czf', str(archive), '-C', str(ROOT.parent), ROOT.name], check=True)
    meta = dict(archive=str(archive), bytes=archive.stat().st_size, sha256=digest(archive),
        manifest=str(manifest), manifest_sha256=digest(manifest), file_count=len(files),
        raw_bytes=sum(row.get('bytes',0) for row in files.values()),
        symlink_count=sum(row['kind']=='symlink' for row in files.values()))
    with (ROOT.parent/(ROOT.name+'-archive-meta.json')).open('x') as stream:
        json.dump(meta, stream, indent=2)
    print(json.dumps(meta, indent=2), flush=True)


if __name__ == '__main__':
    main()
