"""CPU file/hash/HEAD checks only. No simulator, torch, GPU or policy calls."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(reference):
    rows = []
    for row in reference['files']:
        item = dict(row)
        path = Path(row['path'])
        if path.is_file():
            digest = sha256(path)
            item.update(sha256=digest, bytes=path.stat().st_size, match=digest == row['expected_sha256'])
        else:
            item.update(match=False, error='missing')
        rows.append(item)
    trees = {}
    for name, expected in reference['source_heads'].items():
        path = reference['aliases'][name]
        head = subprocess.check_output(['git', '-C', path, 'rev-parse', 'HEAD'], text=True).strip()
        status = subprocess.check_output(['git', '-C', path, 'status', '--porcelain', '--untracked-files=no'], text=True)
        trees[name] = dict(path=path, head=head, expected_head=expected, match=head == expected, tracked_status=status)
    disk = shutil.disk_usage('/home/ugrp/ugrp-sim')
    return dict(schema='ugrp.baseline-treatment.hash-check.v1', utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        files=rows, trees=trees, all_match=all(r['match'] for r in rows) and
        all(t['match'] and not t['tracked_status'] for t in trees.values()),
        disk=dict(total=disk.total, free=disk.free))


if __name__ == '__main__':
    result = verify(json.loads((Path(__file__).parent / 'baseline-reference.json').read_text()))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['all_match'] else 1)
