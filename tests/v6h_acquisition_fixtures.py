"""Synthetic inventory using the committed 0b77ae4b generator's exact format.

Never import/run that generator: its top-level paths address blinded evidence.
"""
import json
import os
import time
from pathlib import Path

from tests import test_v6h_blinded_run_manifest as base


def inventory_for(raw, manifest_path, manifest):
    assert raw.name == 'synthetic' and '/outputs/' not in str(raw)
    if not (raw / 'manifest.json').exists():
        base.base.write_json(raw / 'manifest.json', {'end_unix': time.time(), 'status': 'synthetic'})
    end = json.loads((raw / 'manifest.json').read_bytes())['end_unix']
    rows, total, late = [], 0, 0
    for root, dirs, files in os.walk(raw):
        dirs.sort()
        for name in sorted(files):
            path = Path(root) / name
            st = path.lstat()
            rows.append({'path': os.path.relpath(path, raw), 'bytes': st.st_size,
                         'sha256': base.cp.sha256(path), 'mtime': st.st_mtime})
            total += st.st_size
            if st.st_mtime > end + 1.0:
                late += 1
    doc = {'schema': 'ugrp.v6h1.acquisition_inventory.v1', 'raw': str(raw.resolve()),
           'created_unix': time.time(), 'driver_end_unix': end, 'file_count': len(rows),
           'total_bytes': total, 'files_modified_after_driver_end': late, 'files': rows}
    path = raw.parent / 'synthetic_inventory.json'
    path.write_text(json.dumps(doc, sort_keys=True, separators=(',', ':')))
    manifest['raw'].update(path=doc['raw'], file_count=len(rows), total_bytes=total,
                          raw_manifest_json_sha256=base.cp.sha256(raw / 'manifest.json'))
    base.base.write_json(manifest_path, manifest)
    return path, {**{k: doc[k] for k in ('schema', 'raw', 'file_count', 'total_bytes')},
                  'inventory_sha256': base.cp.sha256(path)}


def synthetic_acquisition(tmp_path):
    raw, manifest_path, manifest, plan = base.synthetic_run(tmp_path, 72)
    inventory, pin = inventory_for(raw, manifest_path, manifest)
    return raw, plan, manifest_path, base.cp.sha256(manifest_path), inventory, pin
