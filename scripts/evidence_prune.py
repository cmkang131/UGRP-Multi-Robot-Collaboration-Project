#!/usr/bin/env python3
"""Prune completed dev evidence for a closed/merged PR, only with --execute."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.storage_common import (TRACE_LIMIT, atomic_text, files, hash_tsv, idle_reason,
                                    inventory, lock_run, run_dirs, sha256, snapshot)
from scripts.worktree_guard import Refused, refuse_if_in_use

REPO = 'kcm0127-dotcom/ugrp'
MEDIA = {'.jpg', '.jpeg', '.png', '.webp', '.npz', '.npy', '.mp4', '.mov', '.avi', '.mkv'}
PERMANENT = ('summary', 'result', 'verdict', 'judgment', 'request', 'response', 'llm',
             'command', 'trajectory', 'action', 'ledger', 'sha256', 'hashes', 'manifest',
             'score', 'integrity', 'admission', 'run_meta', 'compressed')


def pr_info(number: int) -> dict:
    result = subprocess.run(['gh', 'pr', 'view', str(number), '--repo', REPO,
                             '--json', 'number,state,headRefName'], capture_output=True,
                            text=True, check=True, timeout=30)
    data = json.loads(result.stdout)
    if data.get('number') != number or data.get('state') not in {'MERGED', 'CLOSED'}:
        raise ValueError(f'PR #{number} is not MERGED/CLOSED')
    opened = subprocess.run(['gh', 'pr', 'list', '--repo', REPO, '--state', 'open',
                             '--head', data['headRefName'], '--json', 'number'],
                            capture_output=True, text=True, check=True, timeout=30)
    if json.loads(opened.stdout):
        raise ValueError('branch has another open PR')
    return data


def keep_paths(meta: dict) -> list[Path]:
    keep = meta.get('keep', [])
    if not isinstance(keep, list) or any(not isinstance(s, str) for s in keep):
        raise ValueError('RUN_META.keep must be a list of relative paths')
    result = [Path(s) for s in keep]
    if any(p.is_absolute() or '..' in p.parts or str(p) == '.' for p in result):
        raise ValueError('invalid RUN_META.keep path')
    return result


def heavy(relative: Path, size: int, meta: dict, original_sizes: dict) -> bool:
    name = relative.name.lower()
    if any(part.lower().startswith('representative') for part in relative.parts):
        return False
    # Explicit keep works for directories and compressed forms of the same file.
    plain = relative.with_suffix('') if relative.suffix == '.zst' else relative
    for kept in keep_paths(meta):
        if relative == kept or kept in relative.parents or plain == kept or kept in plain.parents:
            return False
    # Text requests/responses/commands and verdicts survive regardless of size.
    if any(word in plain.name.lower() for word in PERMANENT) or any(
            part.lower() in {'llm', 'requests', 'responses', 'commands', 'trajectories'}
            for part in relative.parts[:-1]):
        return False
    if plain.suffix.lower() in MEDIA:
        return True
    uncompressed = original_sizes.get(relative.as_posix(), size)
    return plain.suffix.lower() in {'.json', '.jsonl'} and uncompressed > TRACE_LIMIT


def plan(root: Path, number: int) -> dict:
    meta = json.loads((root / 'RUN_META.json').read_text())
    reason = idle_reason(root)
    if meta.get('pr') != number or meta.get('class') != 'dev':
        reason = 'PR mismatch or protected class'
    # Parent study/milestone classification wins over a nested dev marker.
    for parent in root.parents:
        marker = parent / 'RUN_META.json'
        if marker.is_file():
            owner = json.loads(marker.read_text())
            if owner.get('class') != 'dev' or owner.get('pr') != number:
                reason = 'protected parent run or another PR'
    paths = list(files(root))
    if any(p.name == 'RUN_META.json' and p.parent != root for p in paths):
        reason = 'nested runs: prune separately'
    keep_paths(meta)
    if reason:
        return {'run': str(root), 'skipped': reason, 'bytes': 0, 'candidates': []}
    original_sizes = {}
    manifest = root / 'COMPRESSED.jsonl'
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            item = json.loads(line)
            original_sizes[item['compressed_path']] = item['bytes']
    rows = []
    for path in paths:
        relative = path.relative_to(root)
        if heavy(relative, path.stat().st_size, meta, original_sizes):
            before = snapshot(path)
            digest = sha256(path)
            if snapshot(path) != before:
                raise ValueError(f'file changed during planning: {path}')
            rows.append({'path': relative.as_posix(), 'bytes': before[2],
                         'sha256': digest, 'snapshot': before})
    return {'run': str(root), 'bytes': sum(r['bytes'] for r in rows), 'candidates': rows}


def execute(root: Path, number: int, records: Path):
    # Process/file checks reuse the worktree retirement guard; no time-based retention.
    with lock_run(root):
        refuse_if_in_use(root, 0, None)
        info = pr_info(number)  # fresh status immediately before mutation
        planned = plan(root, number)
        if 'skipped' in planned:
            raise ValueError(planned['skipped'])
        all_rows = inventory(root)
        full = root / 'ALL-hashes.tsv'
        listing = hash_tsv(all_rows)
        atomic_text(full, full.read_text() + listing.split('\n', 1)[1] if full.exists() else listing)
        old = root / 'PRUNED-hashes.tsv'
        new = hash_tsv(planned['candidates'])
        # Keep previous pruning receipts when an execution is repeated.
        atomic_text(old, old.read_text() + new.split('\n', 1)[1] if old.exists() else new)
        records.mkdir(parents=True, exist_ok=True)
        tag = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8]
        receipt = records / f'pr-{number}-{tag}.json'
        record = {'schema': 'ugrp.evidence-prune.v1', 'pr': info, 'run': str(root),
                  'bytes': planned['bytes'], 'files': planned['candidates'], 'status': 'planned',
                  'all_hashes': str(root / 'ALL-hashes.tsv'), 'completed': []}
        atomic_text(receipt, json.dumps(record, indent=2) + '\n')
        for row in all_rows:
            if snapshot(root / row['path']) != tuple(row['snapshot']):
                raise ValueError('run changed after inventory')
        trash = Path.home() / '.Trash' / f'ugrp-pr-{number}-{tag}'
        for row in planned['candidates']:
            path = root / row['path']
            if path.is_symlink() or snapshot(path) != tuple(row['snapshot']) or idle_reason(root):
                raise ValueError(f'run/file changed before pruning: {path}')
            if sys.platform == 'darwin':
                destination = trash / row['path']
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(destination))
            else:
                path.unlink()
            record['completed'].append(row['path'])
            atomic_text(receipt, json.dumps(record, indent=2) + '\n')
        record.update(status='done', trash=str(trash) if sys.platform == 'darwin' else None)
        atomic_text(receipt, json.dumps(record, indent=2) + '\n')
        return planned


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pr', type=int, required=True)
    p.add_argument('roots', nargs='+', type=Path)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--records', type=Path, help='default: project outputs/cleanup-records; required outside checkout')
    a = p.parse_args(argv)
    try:
        info = pr_info(a.pr)
        records = a.records or Path(__file__).resolve().parents[1] / 'outputs' / 'cleanup-records'
        found = set()
        for root in a.roots:
            root = root.expanduser().absolute()
            if not root.is_dir():
                raise ValueError(f'missing search root: {root}')
            found.update(run_dirs(root))
        rows = []
        for root in sorted(found):
            row = plan(root, a.pr)
            if a.execute and 'skipped' not in row and row['candidates']:
                row = execute(root, a.pr, records)
            rows.append(row)
        print(json.dumps({'schema': 'ugrp.evidence-prune.v1', 'pr': info,
                          'dry_run': not a.execute, 'metadata_runs': len(found), 'runs': rows,
                          'candidate_bytes': sum(r['bytes'] for r in rows),
                          'unclassified_policy': 'missing RUN_META is preserved'}))
        return 0
    except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
        print(f'pruning refused: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
