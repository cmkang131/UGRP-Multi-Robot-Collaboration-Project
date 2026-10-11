#!/usr/bin/env python3
"""Lossless zstd for >64 KiB JSON/JSONL in EXIT-complete runs; dry-run by default."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.storage_common import (TRACE_LIMIT, atomic_text, files, hash_tsv, idle_reason,
                                    inventory, lock_run, safe_path, sha256, snapshot)
from scripts.worktree_guard import Refused, refuse_if_in_use


def decompressed_hash(path: Path) -> str:
    proc = subprocess.Popen(['zstd', '-q', '-d', '-c', '--', str(path)], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        digest = hashlib.file_digest(proc.stdout, 'sha256').hexdigest()
    finally:
        proc.stdout.close()
    if proc.wait() != 0:
        raise ValueError(f'zstd decompression failed: {path}')
    return digest


def compress_run(root: Path, execute=False) -> dict:
    reason = idle_reason(root)
    if reason:
        return {'run': str(root), 'skipped': reason, 'files': 0, 'saved_bytes': 0}
    candidates = [p for p in files(root) if p.suffix in {'.json', '.jsonl'} and p.stat().st_size > TRACE_LIMIT
                  and p.name not in {'RUN_META.json', 'COMPRESSED.jsonl'}]
    if not execute:
        return {'run': str(root), 'dry_run': True, 'files': len(candidates),
                'input_bytes': sum(p.stat().st_size for p in candidates)}
    with lock_run(root):
        refuse_if_in_use(root, 0, None)
        if idle_reason(root):
            raise ValueError('run became active')
        # A nested active run blocks the whole operation; never compress its partial logs.
        for meta in files(root):
            if meta.name == 'RUN_META.json' and idle_reason(meta.parent):
                raise ValueError(f'nested run unfinished/in-use: {meta.parent}')
        original_inventory = root / 'ALL-hashes.tsv'
        listing = hash_tsv(inventory(root))
        atomic_text(original_inventory, original_inventory.read_text() + listing.split('\n', 1)[1]
                    if original_inventory.exists() else listing)
        saved = 0
        count = 0
        manifest = root / 'COMPRESSED.jsonl'
        for source in candidates:
            before = snapshot(source)
            original_hash = sha256(source)
            target = source.with_name(source.name + '.zst')
            if target.exists() or target.is_symlink():
                raise ValueError(f'compressed target exists; refusing overwrite: {target}')
            temporary = target.with_name(target.name + f'.tmp-{os.getpid()}')
            try:
                subprocess.run(['zstd', '-q', '-3', '-T1', '-o', str(temporary), '--', str(source)], check=True)
                if decompressed_hash(temporary) != original_hash or snapshot(source) != before:
                    raise ValueError(f'sha256 mismatch/source changed: {source}')
                # Publish without replacing an existing target.
                os.link(temporary, target)
                temporary.unlink()
                record = {'path': source.relative_to(root).as_posix(), 'bytes': before[2],
                          'sha256': original_hash, 'compressed_path': target.relative_to(root).as_posix(),
                          'compressed_bytes': target.stat().st_size, 'compressed_sha256': sha256(target),
                          'codec': 'zstd -3 -T1', 'verified': 'decompressed_sha256'}
                # Durable manifest BEFORE removing any original.
                with manifest.open('a') as stream:
                    stream.write(json.dumps(record) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                if not safe_path(source, root) or snapshot(source) != before or idle_reason(root):
                    raise ValueError(f'source/run changed before removal: {source}')
                source.unlink()
                saved += record['bytes'] - record['compressed_bytes']
                count += 1
            finally:
                temporary.unlink(missing_ok=True)
        atomic_text(root / 'SHA256SUMS.tsv', hash_tsv(inventory(root)))
        return {'run': str(root), 'files': count, 'saved_bytes': saved, 'sha256_verified': True}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs', nargs='+', type=Path)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    try:
        rows = [compress_run(root.expanduser(), a.execute) for root in a.runs]
        print(json.dumps(rows))
        return 1 if any('skipped' in row for row in rows) else 0
    except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
        print(f'compression refused: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
