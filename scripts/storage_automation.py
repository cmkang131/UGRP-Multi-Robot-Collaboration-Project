#!/usr/bin/env python3
"""Daily/pressure evidence maintenance. No VM lifecycle or credentials on servers."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import evidence_prune as prune
from scripts.compress_json_traces import compress_run
from scripts.storage_common import (atomic_text, files, has_symlink, idle_reason,
    latest_evidence, lock_run, persistent, run_dirs, safe_path)
from scripts.worktree_guard import Refused, refuse_if_in_use

GIB = 2**30
FLOORS = {'mac': 20, 'arm': 25, 'azure': 8}
REPO = 'kcm0127-dotcom/ugrp'
CATALOG_TTL = 300
# Confirmed against PR bodies/experiments on 2026-10-11. Specific view jobs first.
PREFIXES = [(r'^egomap70view', 437), (r'^s4live11view', 436), (r'^e2e3view', 434),
            (r'^s3view3', 432), (r'^s4view', 431), (r'^s3view', 427),
            (r'^egomap', 405), (r'^s4(?:live|grip)', 425),
            (r'^s3fix\d', 416), (r'^e2e[1-4](?:-|$)', 433)]
EXCLUDED = {'cleanup-records', 'storage-auto', 'storage-alerts', 'tensorboard',
            'tensorboard-archive', 'retired-worktrees'}


def fetch_catalog() -> dict:
    result = subprocess.run(['gh', 'api', '--paginate', '--slurp',
        f'repos/{REPO}/pulls?state=all&per_page=100'], text=True, capture_output=True,
        check=True, timeout=120)
    rows = []
    for page in json.loads(result.stdout):
        for p in page:
            rows.append({'number': p['number'], 'state': 'MERGED' if p['merged_at'] else p['state'].upper(),
                         'headRefName': p['head']['ref'], 'title': p['title'], 'body': p['body'] or ''})
    return {'schema': 'ugrp.pr-catalog.v1', 'repo': REPO, 'fetched_at': time.time(), 'prs': rows,
            'references': reference_index(rows)}


def reference_index(prs):
    """Read only experiment directories actually linked from PR bodies."""
    source = Path(os.environ.get('UGRP_PROJECT_PATH', str(Path(__file__).resolve().parents[1])))
    refs = {}
    for pr in prs:
        names = set()
        for rel in set(re.findall(r'experiments/[\w./-]+', pr.get('body', ''))):
            target = source / rel.rstrip('.')
            if not target.exists():
                continue
            paths = [target] if target.is_file() else list(target.glob('*.md'))
            for path in paths:
                if path.suffix not in {'.md', '.json'} or path.stat().st_size > 1024**2:
                    continue
                text = path.read_text(errors='replace')
                names.update(re.findall(r'(?:outputs|ugrp-sim/runs|ugrp-archive/runs)/([\w.-]+)', text))
        for name in names:
            refs.setdefault(name, []).append(pr['number'])
    return refs


def validate_catalog(data):
    age = time.time() - data['fetched_at']
    if data.get('repo') != REPO or not 0 <= age <= CATALOG_TTL:
        raise ValueError('PR catalog is expired/wrong repository; refresh on Mac')
    if not isinstance(data.get('prs'), list) or not data['prs']:
        raise ValueError('empty PR catalog')


def catalog_pr(data, number):
    validate_catalog(data)
    row = next((r for r in data['prs'] if r['number'] == number), None)
    if not row or row['state'] not in {'MERGED', 'CLOSED'}:
        raise ValueError(f'PR #{number} is not MERGED/CLOSED')
    if any(r['state'] == 'OPEN' and r['headRefName'] == row['headRefName'] for r in data['prs']):
        raise ValueError('branch has another open PR')
    return row


def orphan_branch_open(meta, data):
    # Retrospective unknown PRs can still carry an exact known branch.
    return bool(meta.get('branch')) and any(r['state'] == 'OPEN' and
        r['headRefName'] == meta['branch'] for r in data['prs'])


def infer_meta(root, catalog, references=None):
    matches = []
    source = 'unresolved: PR-less DEV; eligible after 7 days when pressure persists'
    for pattern, number in PREFIXES:
        if re.search(pattern, root.name):
            matches = [r for r in catalog['prs'] if r['number'] == number]
            source = 'name prefix verified in PR body/experiment records'
            break
    # Exact path/name references are stronger than a broad family prefix.
    exact = [r for r in catalog['prs'] if re.search(
        r'(?<![\w.-])' + re.escape(root.name) + r'(?![\w.-])', r.get('body', ''))]
    if len(exact) == 1:
        matches, source = exact, 'exact run name in PR body'
    if not matches and references:
        numbers = references.get(root.name, [])
        if len(numbers) == 1:
            matches = [r for r in catalog['prs'] if r['number'] == numbers[0]]
            source = 'exact run name in experiment linked by PR'
    row = matches[0] if len(matches) == 1 else None
    sha_file = root / 'SOURCE_SHA'
    sha = sha_file.read_text().strip() if safe_path(sha_file, root) and sha_file.is_file() else None
    if sha and not re.fullmatch('[0-9a-f]{40}', sha):
        sha = None
    # Existing metadata is never downgraded. Explicit study/milestone markers win.
    klass = 'study' if (root / 'STUDY').is_file() else 'milestone' if (root / 'MILESTONE').is_file() else 'dev'
    return {'schema': 'ugrp.run-meta.v1', 'class': klass, 'pr': row['number'] if row else None,
            'branch': row['headRefName'] if row else None, 'sha': sha, 'batch': root.name,
            'keep': [], 'retrospective': True, 'note': source,
            'evidence_mtime': latest_evidence(root)}


def batches(root):
    """Top-level batches plus EXIT-complete nested runs; no following archive links."""
    if has_symlink(root):
        raise ValueError('symlink search root')
    found = set()
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.is_symlink() or child.name.startswith('.') or child.name in EXCLUDED:
            continue
        found.add(child)
        for directory, dirs, names in os.walk(child, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
            if 'EXIT' in names:
                found.add(Path(directory))
    return sorted(found)


def backfill(root, catalog, execute=False):
    rows = []
    inferred = {}
    for batch in batches(root):
        marker = batch / 'RUN_META.json'
        if marker.exists() or marker.is_symlink():
            continue
        meta = infer_meta(batch, catalog, catalog.get('references'))
        for parent in batch.parents:
            if parent == root:
                break
            owner = inferred.get(parent)
            if owner is None and (parent / 'RUN_META.json').is_file():
                owner = json.loads((parent / 'RUN_META.json').read_text())
            if owner:
                if meta['pr'] is None:
                    meta.update(pr=owner.get('pr'), branch=owner.get('branch'),
                                note='inherited batch metadata: ' + str(parent))
                if owner.get('class') in {'study', 'milestone'}:
                    meta['class'] = owner['class']
                break
        inferred[batch] = meta
        row = {'run': str(batch), 'meta': meta, 'written': False}
        if execute:
            # Metadata may be attached to active legacy runs; never invent EXIT.
            with lock_run(batch):
                if not marker.exists():
                    atomic_text(marker, json.dumps(meta, indent=2) + '\n')
                    row['written'] = True
        rows.append(row)
    return rows


def eligible(root, catalog, number):
    meta = json.loads((root / 'RUN_META.json').read_text())
    if number is None:
        validate_catalog(catalog)
        if orphan_branch_open(meta, catalog):
            return 'PR-less branch has an open PR'
    else:
        try:
            catalog_pr(catalog, number)
        except ValueError as exc:
            return str(exc)
    if idle_reason(root):
        return idle_reason(root)
    if time.time() - latest_evidence(root) < (7 * 86400 if number is None else 86400):
        return 'recent evidence: 7d PR-less / 24h known PR'
    return None


def maintenance(root, host, catalog, records, execute=False, include_orphans=False):
    persistent(root)
    validate_catalog(catalog)
    report = {'schema': 'ugrp.storage-auto.v1', 'host': host, 'root': str(root),
              'dry_run': not execute, 'before_free_bytes': shutil.disk_usage(root).free,
              'stages': [], 'backfill': backfill(root, catalog, execute), 'errors': []}
    pressure = report['before_free_bytes'] < (FLOORS[host] + 10) * GIB
    # Dry-run uses virtual metadata; never writes raw directories.
    virtual = {Path(r['run']): r['meta'] for r in report['backfill']}
    runs = sorted(set(run_dirs(root)) | set(virtual))
    groups = {'closed_dev': [], 'prless_dev_7d': []}
    skips = {}
    for run in runs:
        try:
            meta = virtual.get(run) or json.loads((run / 'RUN_META.json').read_text())
            number = meta.get('pr')
            if not (run / 'RUN_META.json').exists():
                # Virtual planning: metadata-free legacy execution remains read-only.
                if number is not None:
                    catalog_pr(catalog, number)
                reason = idle_reason(run)
                if time.time() - latest_evidence(run) < (7 * 86400 if number is None else 86400):
                    reason = 'recent evidence'
            else:
                reason = eligible(run, catalog, number)
            if meta.get('class') != 'dev':
                reason = 'protected class'
            if reason:
                skips[str(run)] = reason
                continue
            groups['prless_dev_7d' if number is None else 'closed_dev'].append((run, number, meta))
        except (OSError, ValueError, KeyError) as exc:
            skips[str(run)] = str(exc)
    report['skipped'] = skips
    if pressure:
        stage = {'stage': 'a_compress', 'runs': []}
        for run, number, meta in groups['closed_dev'] + groups['prless_dev_7d']:
            try:
                # Any nested active run is checked by the existing compressor.
                stage['runs'].append(compress_run(run, execute))
            except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
                report['errors'].append({'run': str(run), 'stage': stage['stage'], 'error': str(exc)})
        report['stages'].append(stage)
    for name in ('closed_dev', 'prless_dev_7d'):
        if name == 'prless_dev_7d' and not (include_orphans or
                (pressure and shutil.disk_usage(root).free < (FLOORS[host] + 10) * GIB)):
            report['stages'].append({'stage': 'c_prless_dev_7d', 'skipped': 'space above pressure threshold'})
            continue
        stage = {'stage': 'b_closed_dev' if name == 'closed_dev' else 'c_prless_dev_7d', 'runs': []}
        for run, number, meta in groups[name]:
            try:
                if execute:
                    row = prune.plan(run, number, idle_hours=24)
                    if row.get('candidates'):
                        row = prune.execute(run, number, records, catalog=catalog, idle_hours=24)
                elif run in virtual:
                    row = virtual_plan(run, number, meta)
                else:
                    row = prune.plan(run, number, idle_hours=24)
                stage['runs'].append(row)
            except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
                report['errors'].append({'run': str(run), 'stage': stage['stage'], 'error': str(exc)})
        report['stages'].append(stage)
    report['after_free_bytes'] = shutil.disk_usage(root).free
    report['candidate_bytes'] = sum(row.get('bytes', 0) for s in report['stages'] for row in s.get('runs', []))
    if host == 'mac':
        try:
            trash = Path.home() / '.Trash'
            report['trash_bytes'] = sum(p.stat().st_size for p in files(trash)) if trash.exists() else 0
            if execute and report['trash_bytes'] > 10 * GIB:
                atomic_text(records / 'TRASH-OVER-10GiB.txt',
                    'UGRP 휴지통이 10 GiB를 넘었습니다. 자동으로 비우지 않습니다.\n')
        except OSError as exc:
            report['errors'].append({'stage': 'trash_measurement', 'error': str(exc)})
    if execute and report['after_free_bytes'] < FLOORS[host] * GIB:
        atomic_text(records / f'LOW-SPACE-{host}.json', json.dumps({
            'host': host, 'free_bytes': report['after_free_bytes'], 'floor_gib': FLOORS[host],
            'note': 'protected/active evidence retained; no other projects touched'}) + '\n')
    return report


def virtual_plan(root, number, meta):
    # Missing metadata dry-run: same classifier, parent protection and representative rule.
    paths = list(files(root))
    if any(p.name == 'RUN_META.json' and p.parent != root for p in paths):
        return {'run': str(root), 'skipped': 'nested runs: prune separately', 'bytes': 0}
    for parent in root.parents:
        marker = parent / 'RUN_META.json'
        if marker.is_file():
            owner = json.loads(marker.read_text())
            if owner.get('class') != 'dev' or owner.get('pr') != number:
                return {'run': str(root), 'skipped': 'protected parent run or another PR', 'bytes': 0}
    original_sizes = {}
    manifest = root / 'COMPRESSED.jsonl'
    if manifest.is_file():
        for line in manifest.read_text().splitlines():
            r = json.loads(line)
            original_sizes[r['compressed_path']] = r['bytes']
    mp4s = sorted(p for p in paths if p.suffix.lower() == '.mp4')
    representative = mp4s[0] if mp4s else None
    candidates = []
    for path in paths:
        if representative and (path == representative or (not representative.name.lower().startswith('representative')
                and path.parent == representative.parent
                and path.suffix.lower() in {'.json', '.jsonl', '.zst', '.npz', '.npy'})):
            continue
        relative = path.relative_to(root)
        if prune.heavy(relative, path.stat().st_size, meta, original_sizes):
            before = prune.snapshot(path)
            digest = prune.sha256(path)
            if prune.snapshot(path) != before:
                raise ValueError('file changed during planning')
            candidates.append({'path': relative.as_posix(), 'bytes': before[2], 'sha256': digest, 'snapshot': before})
    return {'run': str(root), 'bytes': sum(r['bytes'] for r in candidates), 'candidates': candidates}


def post_run(root):
    """Common wrapper hook: retain exit status even if maintenance fails."""
    root = Path(root)
    report = {'schema': 'ugrp.run-storage.v1', 'bytes': sum(p.stat().st_size for p in files(root)),
              'warning_threshold_bytes': 300 * 2**20}
    report['over_300mb'] = report['bytes'] > report['warning_threshold_bytes']
    if report['over_300mb']:
        print(f'UGRP storage warning: {root} is {report["bytes"] / 2**20:.1f} MiB (>300 MiB)', file=sys.stderr)
    try:
        report['compression'] = compress_run(root, execute=True)
    except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
        report['compression_error'] = str(exc)
    atomic_text(root / 'RUN_STORAGE.json', json.dumps(report, indent=2) + '\n')
    return report


def remote_run(catalog, execute, include_orphans=False):
    # Credentials stay on Mac. SSH transports only a short-lived live PR catalog.
    command = shlex.join(['python3', 'ugrp-storage-tools/scripts/storage_automation.py',
        '--host', 'arm', '--root', 'ugrp-archive/runs', '--catalog-stdin'] +
        (['--execute'] if execute else []) + (['--include-orphans'] if include_orphans else []))
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'oracle', command],
        input=json.dumps(catalog), text=True, capture_output=True, timeout=3600)
    if result.returncode:
        raise ValueError(f'ARM maintenance failed: {result.stderr[-1000:]}')
    return json.loads(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=FLOORS, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--records', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--catalog-stdin', action='store_true')
    parser.add_argument('--remote-arm', action='store_true')
    parser.add_argument('--scheduled', action='store_true', help='5min check; expensive work daily or low disk')
    parser.add_argument('--include-orphans', action='store_true', help='explicit manual 7d PR-less sweep')
    args = parser.parse_args(argv)
    root = args.root.expanduser().absolute()
    records = args.records or (root / 'cleanup-records')
    try:
        records.mkdir(parents=True, exist_ok=True)
        with (records / '.maintenance.lock').open('a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({'skipped': 'another maintenance is running'}))
                return 0
            state_file = records / 'schedule-state.json'
            state = json.loads(state_file.read_text()) if state_file.exists() else {}
            now = time.time()
            if args.scheduled:
                daily_due = now - state.get('last_success', 0) >= 86400
                low = shutil.disk_usage(root).free < FLOORS[args.host] * GIB
                # Also query ARM free space over SSH, without touching any other host.
                arm_low = False
                if args.remote_arm:
                    from scripts.storage_budget import free_bytes
                    try:
                        arm_low = free_bytes('~/ugrp-archive/runs', 'oracle') < 35 * GIB
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        atomic_text(records / 'ARM-CONNECTION-ERROR.json', json.dumps({'at': now, 'error': str(exc)})+'\n')
                if not daily_due and not low and not arm_low:
                    print(json.dumps({'skipped': 'daily maintenance not due; space sufficient'}))
                    return 0
                if now - state.get('last_attempt', 0) < 3600:
                    print(json.dumps({'skipped': 'pressure retry limited to hourly'}))
                    return 0
                atomic_text(state_file, json.dumps({**state, 'last_attempt': now})+'\n')
            catalog = json.load(sys.stdin) if args.catalog_stdin else fetch_catalog()
            report = maintenance(root, args.host, catalog, records, args.execute, args.include_orphans)
            if args.remote_arm:
                # Refresh just before remote execution (large Mac hashes can take minutes).
                try:
                    report['arm'] = remote_run(fetch_catalog(), args.execute, args.include_orphans)
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    report['errors'].append({'stage': 'arm', 'error': str(exc)})
            tag = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8]
            atomic_text(records / f'auto-{tag}.json', json.dumps(report, indent=2)+'\n')
            if args.execute and not report['errors'] and not report.get('arm', {}).get('errors'):
                atomic_text(state_file, json.dumps({'last_attempt': now, 'last_success': now})+'\n')
            print(json.dumps(report))
            return int(bool(report['errors'] or report.get('arm', {}).get('errors')))
    except (OSError, ValueError, Refused, subprocess.SubprocessError) as exc:
        atomic_text(records / 'MAINTENANCE-ERROR.json', json.dumps({'at': time.time(), 'error': str(exc)})+'\n')
        print(str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
