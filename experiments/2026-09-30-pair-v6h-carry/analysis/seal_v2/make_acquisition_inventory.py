"""Pre-unblinding acquisition inventory for the b-v6h1 blinded raw.
Records path, size, sha256, mtime for every file; prints only aggregate numbers (no names, no content)."""
import hashlib, json, os, sys, time
RAW = '/Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930'
OUT = '/Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930-inventory'
os.makedirs(OUT, exist_ok=False)
end_unix = json.load(open(os.path.join(RAW, 'manifest.json')))['end_unix']
rows, total, late = [], 0, 0
for root, dirs, files in os.walk(RAW):
    dirs.sort()
    for n in sorted(files):
        p = os.path.join(root, n); st = os.lstat(p)
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
        rel = os.path.relpath(p, RAW)
        rows.append({'path': rel, 'bytes': st.st_size, 'sha256': h.hexdigest(), 'mtime': st.st_mtime})
        total += st.st_size
        if st.st_mtime > end_unix + 1.0: late += 1
doc = {'schema': 'ugrp.v6h1.acquisition_inventory.v1', 'raw': RAW, 'created_unix': time.time(),
       'driver_end_unix': end_unix, 'file_count': len(rows), 'total_bytes': total,
       'files_modified_after_driver_end': late, 'files': rows}
path = os.path.join(OUT, 'acquisition_inventory.json')
with open(path, 'w') as f: json.dump(doc, f, sort_keys=True, separators=(',', ':'))
sha = hashlib.sha256(open(path, 'rb').read()).hexdigest()
os.chmod(path, 0o444)
print(json.dumps({'file_count': len(rows), 'total_bytes': total, 'files_modified_after_driver_end': late,
                  'max_mtime_minus_end_s': max(r['mtime'] for r in rows) - end_unix, 'inventory_sha256': sha}))
