#!/usr/bin/env python3
"""Verify stored run hashes and every zstd restore on the Linux source host."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Linux':
        parser.error('verify on the original Linux host; Mac fetch-lite only')
    root = args.input.resolve()
    if args.output.exists() or args.output.resolve().is_relative_to(root):
        parser.error('output must be a new file outside the original run')
    summary = json.loads((root / 'summary.json').read_text())
    if summary['status'] == 'RUNNING':
        parser.error('source run is still running')
    manifest = root / Path(summary['sha256_manifest']).name
    raw = subprocess.check_output(['zstd', '-q', '-d', '-c', str(manifest)]) if manifest.suffix == '.zst' else manifest.read_bytes()
    listed = json.loads(raw)
    bad = [name for name, expected in listed.items() if sha((root / name).read_bytes()) != expected]
    restored_bytes = 0
    bad_restores = []
    metas = list(root.rglob('*.compression.json'))
    for path in metas:
        meta = json.loads(path.read_text())
        restored = subprocess.check_output(['zstd', '-q', '-d', '-c', str(path.parent / meta['compressed_path'])])
        restored_bytes += len(restored)
        if sha(restored) != meta['original_sha256']:
            bad_restores.append(str(path.relative_to(root)))
    result = {'schema': 'ugrp.scene_tex2_preservation.v1', 'raw': str(root),
              'source_sha': summary['source_sha'], 'manifest': manifest.name,
              'manifest_sha256': sha(manifest.read_bytes()), 'file_count': len(listed),
              'bytes': sum((root / name).stat().st_size for name in listed),
              'bad_files': bad, 'compressed_records': len(metas),
              'restored_bytes': restored_bytes, 'bad_restores': bad_restores,
              'verification_script_sha256': sha(Path(__file__).read_bytes())}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return int(bool(bad or bad_restores))


if __name__ == '__main__':
    raise SystemExit(main())
