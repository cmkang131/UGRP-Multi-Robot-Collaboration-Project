"""Run on gcp2 L4: hash only the explicitly authorized immutable training view."""
import hashlib
import json
from pathlib import Path
import time

root = Path('/home/ugrp/ugrp-sim/ops-reviews/actdiag/infer-final-v1/dataset-view')
output = Path('/home/ugrp/ugrp-sim/setup/gcp5setup-source/dataset-sha256.json')
started = time.time()
files = []
for path in sorted(root.rglob('*')):
    if not path.is_file():
        continue
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024**2), b''):
            digest.update(block)
    files.append(dict(path=str(path.relative_to(root)), resolved_source=str(path.resolve()),
                      bytes=path.stat().st_size, sha256=digest.hexdigest()))
result = dict(root=str(root), manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
              files=files, bytes=sum(x['bytes'] for x in files), wall_s=time.time()-started)
assert result['manifest_sha256'] == 'a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(dict(files=len(files), bytes=result['bytes'], wall_s=result['wall_s'])), flush=True)
