"""Allowlisted beamact3 dataset hashes on a GCP guest; never reads credentials."""
import hashlib
import json
from pathlib import Path
import sys

BASE = Path('/home/ugrp/ugrp-sim')
DATA = Path('ops-reviews/actdiag/infer-final-v1/dataset-view')
STAGES = Path('ops-reviews/beamact2/data-v1/stages.json.zst')
EXPECTED = 'a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


assert digest(BASE/DATA/'manifest.json') == EXPECTED
assert json.loads((BASE/DATA/'manifest.json').read_text())['complete'] is True
files = sorted(p for p in (BASE/DATA).rglob('*') if p.is_file()) + [BASE/STAGES]
assert all(not p.is_symlink() for p in files), 'resolve data provenance explicitly before transfer'
records = {str(p.relative_to(BASE)): {'sha256': digest(p), 'bytes': p.stat().st_size,
           'mtime_ns': p.stat().st_mtime_ns} for p in files}
result = dict(dataset_manifest_sha256=EXPECTED, files=records,
              total_bytes=sum(v['bytes'] for v in records.values()), files_n=len(records))
output = Path(sys.argv[1])
output.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({k: v for k, v in result.items() if k != 'files'}))
