"""Copy one recorded own-RGB frame per distinct issued pose into a test fixture.

Source: record_rendered_frames.py raw (seed 911, renderer ON, no controller).
Conditions: nominal (r1, r2) and raise_grip_loss (r2 gripper opened at 12 s).
The first frame of each distinct issued servo tuple (1,3,4,5,6) is kept.
eval_label is copied for provenance only; tests never use it as an input.

Usage: python make_frame_fixture.py <raw_root> <fixture_dir>
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

KEEP = [('nominal', 'r1'), ('nominal', 'r2'), ('raise_grip_loss', 'r2')]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(raw_root, dest):
    raw_root, dest = Path(raw_root), Path(dest)
    index = json.loads((raw_root/'index.json').read_text())
    dest.mkdir(parents=True, exist_ok=False)
    frames = []
    for cond, rid in KEEP:
        seen = set()
        for f in index['frames']:
            if f['condition'] != cond or f['rid'] != rid:
                continue
            key = tuple(f['issued_servo'][s] for s in '13456')
            if key in seen:
                continue
            seen.add(key)
            name = f"{cond}_{rid}_{f['t']:05.1f}.jpg"
            shutil.copyfile(raw_root/f['file'], dest/name)
            assert sha(dest/name) == f['sha256']
            frames.append({'file': name, 'condition': cond, 'rid': rid, 't': f['t'],
                           'sha256': f['sha256'], 'issued_servo': f['issued_servo'],
                           'eval_label_provenance_only': f['eval_label']})
    manifest = {'schema': 'highpose_recorded_frames_v1', 'source_root': str(raw_root),
                'source_index_sha256': sha(raw_root/'index.json'), 'source_sha': index['source_sha'],
                'seed': index.get('seed', 911), 'render': index.get('render', True), 'controller': index.get('controller'),
                'builder_sha256': sha(__file__), 'selection': 'first frame per distinct issued servo (1,3,4,5,6)',
                'frames': frames}
    (dest/'manifest.json').write_text(json.dumps(manifest, indent=1)+'\n')
    print(len(frames), sum((dest/f['file']).stat().st_size for f in frames))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
