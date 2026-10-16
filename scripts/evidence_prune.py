#!/usr/bin/env python3
"""Prune completed dev evidence for a closed/merged PR, only with --execute."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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
                                    inventory, lock_run, run_dirs, safe_path, sha256, snapshot,
                                    HOUSEKEEPING, has_symlink)
from scripts.worktree_guard import Refused, refuse_if_in_use, capture_usage

REPO = 'kcm0127-dotcom/ugrp'
MEDIA = {'.jpg', '.jpeg', '.png', '.webp', '.npz', '.npy', '.mp4', '.mov', '.avi', '.mkv'}
PERMANENT = ('summary', 'result', 'verdict', 'judgment', 'request', 'response', 'llm',
             'command', 'trajectory', 'action', 'ledger', 'sha256', 'hashes', 'manifest',
             'score', 'integrity', 'admission', 'run_meta', 'compressed', 'evaluation',
             'run_storage', 'outcome')
LLM_RECORDS = ('ledger', 'llm', 'model', 'prompt', 'request', 'response', 'message',
               'dialogue', 'episode')


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
    if any(part.lower().startswith('representative') for part in relative.parts):
        return False
    # Explicit keep works for directories and compressed forms of the same file.
    plain = relative.with_suffix('') if relative.suffix.lower() == '.zst' else relative
    for kept in keep_paths(meta):
        if relative == kept or kept in relative.parents or plain == kept or kept in plain.parents:
            return False
    # Text requests/responses/commands and verdicts survive regardless of size.
    if plain.suffix.lower() in {'.json', '.jsonl'} and any(
            word in plain.name.lower() for word in LLM_RECORDS):
        return False
    if any(word in plain.name.lower() for word in PERMANENT) or any(
            part.lower() in {'llm', 'requests', 'responses', 'commands', 'trajectories'}
            for part in relative.parts[:-1]):
        return False
    if plain.suffix.lower() in MEDIA:
        return True
    uncompressed = original_sizes.get(relative.as_posix(), size)
    return plain.suffix.lower() in {'.json', '.jsonl'} and uncompressed > TRACE_LIMIT


def owned_files(root: Path):
    """A nested RUN_META owns its subtree; never inventory/prune it as its parent."""
    if has_symlink(root):
        return
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        if base != root and 'RUN_META.json' in names:
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if not (base / d).is_symlink())
        for name in sorted(names):
            path = base / name
            if safe_path(path, root) and path.is_file():
                yield path


def evidence_age(root: Path, paths=None):
    paths = owned_files(root) if paths is None else paths
    latest = max((p.stat().st_mtime for p in paths if p.name not in HOUSEKEEPING),
                 default=root.stat().st_mtime)
    return time.time() - latest


def completion(root, meta, age, allow_legacy_completed, inspection=None):
    reason = idle_reason(root, require_exit=False)
    if reason:
        return reason, None
    if (root / 'EXIT').is_file():
        return None, 'EXIT'
    if not allow_legacy_completed:
        return 'EXIT absent (unfinished)', None
    # 24 h is the user-approved 2026-10-16 legacy cleanup boundary, not a
    # simulation success/completion claim. Never fabricate an EXIT file.
    if age < 86400:
        return 'EXIT absent; evidence modified within 24 hours', None
    if inspection is None:
        refuse_if_in_use(root, 0, None)
    else:
        refuse_if_in_use(root, 0, None, inspection=inspection)
    return None, ('retrospective:true; idle >=24h; no process use' if
                  meta.get('retrospective') is True else 'EXIT absent; idle >=24h; no process use')


def plan(root: Path, number: int | None, *, idle_hours=0, allow_legacy_completed=False,
         inspection=None) -> dict:
    meta = json.loads((root / 'RUN_META.json').read_text())
    reason = None
    if meta.get('pr') != number or meta.get('class') != 'dev':
        reason = 'PR mismatch or protected class'
    # Parent study/milestone classification wins over a nested dev marker.
    for parent in root.parents:
        marker = parent / 'RUN_META.json'
        if marker.is_file():
            owner = json.loads(marker.read_text())
            if owner.get('class') != 'dev':
                reason = 'protected parent class'
    keep_paths(meta)
    if reason:
        return {'run': str(root), 'skipped': reason, 'bytes': 0, 'candidates': []}
    paths = list(owned_files(root))
    age = evidence_age(root, paths)
    reason, completed = completion(root, meta, age, allow_legacy_completed, inspection)
    if age < idle_hours * 3600:
        reason = 'evidence modified within idle window'
    if number is None and age < 7 * 86400:
        reason = 'PR-less DEV younger than 7 days'
    if reason:
        return {'run': str(root), 'skipped': reason, 'bytes': 0, 'candidates': []}
    ancestor_keeps = [(parent, json.loads((parent / 'RUN_META.json').read_text()))
                      for parent in root.parents if (parent / 'RUN_META.json').is_file()]
    original_sizes = {}
    unknown_original_sizes = []
    manifest = root / 'COMPRESSED.jsonl'
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            item = json.loads(line)
            compressed = item.get('compressed_path', item.get('compressed'))
            if not isinstance(compressed, str):
                raise ValueError(f'invalid compression manifest: {manifest}')
            size = item.get('bytes')
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                # Old manifests sometimes contain hashes but no original size.
                # Preserve these traces rather than guess or abort the batch.
                size = 0
                unknown_original_sizes.append(compressed)
            original_sizes[compressed] = size
    rows = []
    # Retain a representative MP4 per run even for legacy metadata without keep.
    mp4s = sorted(p.relative_to(root) for p in paths if p.suffix.lower() == '.mp4')
    representative = mp4s[0] if mp4s else None
    for path in paths:
        relative = path.relative_to(root)
        if any(any(part.lower().startswith('representative') for part in path.relative_to(parent).parts)
               or any(path.relative_to(parent) == kept or kept in path.relative_to(parent).parents
                      or (path.suffix == '.zst' and path.relative_to(parent).with_suffix('') == kept)
                      for kept in keep_paths(owner)) for parent, owner in ancestor_keeps):
            continue
        if representative is not None and (relative == representative or
                (not representative.name.lower().startswith('representative') and
                 relative.parent == representative.parent and
                 relative.suffix.lower() in {'.json', '.jsonl', '.zst', '.npz', '.npy'})):
            continue
        if heavy(relative, path.stat().st_size, meta, original_sizes):
            before = snapshot(path)
            digest = sha256(path)
            if snapshot(path) != before:
                raise ValueError(f'file changed during planning: {path}')
            rows.append({'path': relative.as_posix(), 'bytes': before[2],
                         'sha256': digest, 'snapshot': before})
    return {'run': str(root), 'bytes': sum(r['bytes'] for r in rows), 'candidates': rows,
            'completion_basis': completed, 'unknown_original_sizes': unknown_original_sizes}


def execute(root: Path, number: int | None, records: Path, *, catalog=None, idle_hours=0,
            allow_legacy_completed=False):
    # Process/file checks reuse the worktree retirement guard; no time-based retention.
    with lock_run(root):
        refuse_if_in_use(root, 0, None)
        if number is None:
            info = {'number': None, 'state': 'PRLESS_DEV_7D'}
            if catalog is not None:
                from scripts.storage_automation import validate_catalog, orphan_branch_open
                validate_catalog(catalog)
                if orphan_branch_open(json.loads((root / 'RUN_META.json').read_text()), catalog):
                    raise ValueError('PR-less branch has an open PR')
        elif catalog is not None:
            from scripts.storage_automation import catalog_pr
            live = catalog_pr(catalog, number)
            info = {key: live[key] for key in ('number', 'state', 'headRefName')}
        else:
            info = pr_info(number)  # fresh status immediately before mutation
        planned = plan(root, number, idle_hours=idle_hours,
                       allow_legacy_completed=allow_legacy_completed)
        if 'skipped' in planned:
            raise ValueError(planned['skipped'])
        all_rows = inventory(root, paths=owned_files(root))
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
        record['completion_basis'] = planned['completion_basis']
        record['unknown_original_sizes'] = planned['unknown_original_sizes']
        progress = receipt.with_suffix('.progress.jsonl')
        record['progress_journal'] = str(progress)
        trash = Path.home() / '.Trash' / f'ugrp-pr-{number}-{tag}'
        record['trash'] = str(trash) if sys.platform == 'darwin' else None
        atomic_text(receipt, json.dumps(record, indent=2) + '\n')
        for row in all_rows:
            if (not safe_path(root / row['path'], root)
                    or snapshot(root / row['path']) != tuple(row['snapshot'])):
                raise ValueError('run changed after inventory')
        # Recheck age once before mutation; own inventory writes are excluded.
        minimum_age = max(idle_hours * 3600, 7 * 86400 if number is None else 0,
                          86400 if planned['completion_basis'] != 'EXIT' else 0)
        if evidence_age(root) < minimum_age:
            raise ValueError('run changed before pruning')
        refuse_if_in_use(root, 0, None)
        moved_inodes = set()
        for row in planned['candidates']:
            if catalog is not None:
                from scripts.storage_automation import validate_catalog, catalog_pr
                validate_catalog(catalog)
                if number is not None:
                    catalog_pr(catalog, number)
            path = root / row['path']
            if (not safe_path(path, root)
                    or idle_reason(root, require_exit=planned['completion_basis'] == 'EXIT')):
                raise ValueError(f'run/file changed before pruning: {path}')
            current, expected = snapshot(path), tuple(row['snapshot'])
            if current != expected:
                # Moving/unlinking one hard link can update the shared inode's
                # ctime. Accept only our already-moved inode, unchanged size /
                # mtime / identity, and a fresh matching content hash.
                if (current[:2] not in moved_inodes or current[:4] != expected[:4]
                        or sha256(path) != row['sha256'] or snapshot(path) != current):
                    raise ValueError(f'run/file changed before pruning: {path}')
            if sys.platform == 'darwin':
                destination = trash / row['path']
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(destination))
            else:
                path.unlink()
            moved_inodes.add(expected[:2])
            record['completed'].append(row['path'])
            # Append durable progress; don't rewrite the entire candidate list per frame.
            with progress.open('a') as stream:
                stream.write(json.dumps({'path': row['path'], 'sha256': row['sha256'],
                                         'status': 'completed'}) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
        record.update(status='done', trash=str(trash) if sys.platform == 'darwin' else None)
        atomic_text(receipt, json.dumps(record, indent=2) + '\n')
        return planned


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--pr', type=int)
    group.add_argument('--prless-dev-7d', action='store_true')
    group.add_argument('--all-closed-dev', action='store_true', help='one discovery scan for all closed PRs')
    p.add_argument('--include-prless-dev-7d', action='store_true')
    p.add_argument('--allow-legacy-completed', action='store_true',
                   help='EXIT-less evidence: >=24h unchanged and no process use; record basis')
    p.add_argument('roots', nargs='+', type=Path)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--idle-hours', type=float, default=0)
    p.add_argument('--records', type=Path, help='default: project outputs/cleanup-records; required outside checkout')
    a = p.parse_args(argv)
    try:
        if a.idle_hours < 0 or not __import__('math').isfinite(a.idle_hours):
            raise ValueError('idle-hours must be finite and nonnegative')
        if a.include_prless_dev_7d and not a.all_closed_dev:
            raise ValueError('--include-prless-dev-7d requires --all-closed-dev')
        info = pr_info(a.pr) if a.pr is not None else {'number': None,
                'state': 'ALL_CLOSED_DEV' if a.all_closed_dev else 'PRLESS_DEV_7D'}
        catalog = None
        if a.pr is None:
            from scripts import storage_automation
            from scripts.storage_automation import fetch_catalog
            storage_automation._catalog_refresher = fetch_catalog
            catalog = fetch_catalog()
        records = a.records or Path(__file__).resolve().parents[1] / 'outputs' / 'cleanup-records'
        found = set()
        for root in a.roots:
            root = root.expanduser().absolute()
            if not root.is_dir():
                raise ValueError(f'missing search root: {root}')
            found.update(run_dirs(root))
        rows = []
        inspection = capture_usage() if a.allow_legacy_completed else None
        summary = defaultdict(lambda: {'bytes': 0, 'files': 0, 'runs': 0, 'skipped': Counter()})
        for index, root in enumerate(sorted(found), 1):
            meta = json.loads((root / 'RUN_META.json').read_text())
            number = meta.get('pr') if a.all_closed_dev else a.pr
            try:
                if catalog is not None:
                    from scripts.storage_automation import catalog_pr, orphan_branch_open, validate_catalog
                    validate_catalog(catalog)
                    if number is None:
                        if a.all_closed_dev and not a.include_prless_dev_7d:
                            raise ValueError('PR-less DEV not requested')
                        if orphan_branch_open(meta, catalog):
                            raise ValueError('PR-less branch has an open PR')
                    else:
                        catalog_pr(catalog, number)
                row = plan(root, number, idle_hours=a.idle_hours,
                           allow_legacy_completed=a.allow_legacy_completed, inspection=inspection)
                if a.execute and 'skipped' not in row and row['candidates']:
                    row = execute(root, number, records, catalog=catalog, idle_hours=a.idle_hours,
                                  allow_legacy_completed=a.allow_legacy_completed)
            except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
                row = {'run': str(root), 'skipped': str(exc), 'bytes': 0, 'candidates': []}
            row['pr'] = number
            bucket = summary[str(number)]
            bucket['runs'] += 1
            bucket['bytes'] += row['bytes']
            bucket['files'] += len(row['candidates'])
            if 'skipped' in row:
                bucket['skipped'][row['skipped']] += 1
            rows.append(row)
            if index % 100 == 0:
                print(f'planned {index}/{len(found)} runs', file=sys.stderr, flush=True)
        print(json.dumps({'schema': 'ugrp.evidence-prune.v1', 'pr': info,
                          'dry_run': not a.execute, 'metadata_runs': len(found), 'runs': rows,
                          'by_pr': dict(summary),
                          'candidate_bytes': sum(r['bytes'] for r in rows),
                          'unclassified_policy': 'missing RUN_META is preserved'}))
        return 0
    except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
        print(f'pruning refused: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
