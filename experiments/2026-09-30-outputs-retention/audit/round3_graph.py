"""Rebuild PR309 from read-only raw + content/reference edges (no execute mode).

All scratch data goes to --scratch; products go to this worktree experiment.
Run phases in order: inventory, references, classify, emit. Originals and round2
sidecars are never modified. Candidate scope can only SHRINK from round2.
"""
from __future__ import annotations

import argparse
import ast
import base64
import collections
import csv
import fnmatch
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time
import zlib

REPO = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts import outputs_retention_graph as graph
from scripts import outputs_prune_stream as batches
from scripts.outputs_prune import sha256


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO)


def inventory(db, root):
    db.executescript('''
    CREATE TABLE files(path TEXT PRIMARY KEY, size INTEGER, allocated INTEGER,
      mtime INTEGER, mode INTEGER, dev INTEGER, ino INTEGER, sha TEXT,
      old_action TEXT, rule TEXT, reason TEXT, protection TEXT, source TEXT);
    CREATE TABLE sources(source TEXT PRIMARY KEY, sha TEXT, size INTEGER,
      status TEXT, references_count INTEGER);
    CREATE TABLE refs(kind TEXT, target TEXT, source TEXT, PRIMARY KEY(kind,target));
    CREATE TABLE matched_refs(kind TEXT, target TEXT, PRIMARY KEY(kind,target));
    CREATE TABLE folders(folder TEXT, source TEXT, reason TEXT,
      PRIMARY KEY(folder,reason));
    CREATE TABLE errors(source TEXT PRIMARY KEY, reason TEXT);
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
    ''')
    start = time.time()
    count = 0
    def scan(folder):
        nonlocal count
        with os.scandir(folder) as entries:
            for e in entries:
                s = e.stat(follow_symlinks=False)
                p = Path(e.path).relative_to(root).as_posix()
                db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL)',
                           (p, s.st_size, s.st_blocks * 512, s.st_mtime_ns, s.st_mode, s.st_dev, s.st_ino))
                count += 1
                if e.is_dir(follow_symlinks=False):
                    scan(Path(e.path))
                if count % 100000 == 0:
                    db.commit()
                    print('inventory', count, flush=True)
    scan(root)
    db.commit()
    manifest_path = DEST / 'round2-manifest.json'
    old = json.loads(manifest_path.read_text())
    # Validate the immutable round2 batches and record individual full hashes.
    # Only read syscalls run in root; never create receipts/locks/caches there.
    for action in ['delete', 'keep']:
        n = 0
        for row, names in batches.rows(old, manifest_path, action):
            records = batches.verify_batch(root, row, names, deletion=action == 'delete')
            for rec in records:
                p = '/'.join(filter(None, [row['folder'], rec['name']]))
                current = db.execute('SELECT size,mtime FROM files WHERE path=?', (p,)).fetchone()
                if current != (rec['bytes'], rec['mtime_ns']):
                    raise RuntimeError(f'changed since inventory: {p}')
                db.execute('UPDATE files SET sha=?,old_action=?,rule=?,reason=? WHERE path=?',
                           (rec['sha256'], action, row.get('rule_id'), row.get('reason'), p))
            n += len(names)
            if n // 50000 != (n - len(names)) // 50000:
                db.commit()
                print('verify old', action, n, flush=True)
        db.commit()
    db.execute('CREATE INDEX files_sha ON files(sha)')
    db.execute('CREATE INDEX files_action ON files(old_action)')
    db.execute('INSERT INTO meta VALUES(?,?)', ('inventory', json.dumps({
        'started_unix': start, 'finished_unix': time.time(), 'entries': count,
        'round2_manifest_sha256': sha256(manifest_path),
        'root': str(root), 'cutoff_unix': old['created_unix'] - 86400,
    })))
    db.commit()


def unit(path):
    parts = path.split('/')
    return '/'.join(parts[:2]) if parts[0] == 'retired-worktrees' and len(parts) > 1 else parts[0]


def add_folder(db, folder, source, reason):
    folder = graph.glob_parent(folder).strip('/')
    if folder in {'.', '..'} or '..' in folder.split('/'):
        raise ValueError('noncanonical folder edge')
    db.execute('INSERT OR IGNORE INTO folders VALUES(?,?,?)', (folder, source, reason))


def collect_stream(db, source, stream, suffix):
    refs = set()
    # Repeated telemetry keys can dominate multi-GiB contact logs. Deduplicate
    # short strings before extraction; bound the cache and never retain large
    # inline image payload strings. This changes cost, not the reference set.
    seen = set()
    for value in graph.structured_strings(stream, suffix):
        if len(value) <= 4096:
            if value in seen:
                continue
            if len(seen) < 65536:
                seen.add(value)
        refs.update(graph.references(value))
    db.executemany('INSERT OR IGNORE INTO refs VALUES(?,?,?)',
                   [(kind, target, source) for kind, target in sorted(refs)])
    return len(refs)


def collect_raw(db, root):
    files = db.execute('SELECT path,size,mtime,sha FROM files WHERE mode & 61440=32768').fetchall()
    records = [row for row in files if graph.structured_suffix(row[0])]
    print('structured sources', len(records), flush=True)
    for n, (p, size, stamp, digest) in enumerate(records, 1):
        source = 'outputs/' + p
        if (db.execute('SELECT 1 FROM sources WHERE source=?', (source,)).fetchone()
                and graph.structured_suffix(p) not in graph.TEXT_EXTENSIONS):
            continue
        try:
            before = (root / p).stat(follow_symlinks=False)
            if (before.st_size, before.st_mtime_ns) != (size, stamp):
                raise ValueError('changed since inventory')
            with graph.open_record(root / p) as stream:
                count = collect_stream(db, source, stream, graph.structured_suffix(p))
            digest = digest or sha256(root / p)
            after = (root / p).stat(follow_symlinks=False)
            if (after.st_size, after.st_mtime_ns) != (size, stamp):
                raise ValueError('changed during scan')
            db.execute('UPDATE files SET sha=? WHERE path=?', (digest, p))
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)', (source, digest, size, 'parsed', count))
        except (OSError, ValueError, TypeError, OverflowError) as e:
            # Do not expose potentially secret parser excerpts in committed logs.
            reason = type(e).__name__
            db.execute('INSERT OR REPLACE INTO errors VALUES(?,?)', (source, reason))
            add_folder(db, unit(p), source, 'unreadable_or_changing_record')
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)', (source, digest, size, reason, 0))
        if n % 2000 == 0:
            db.commit()
            print('parse raw', n, '/', len(records), flush=True)
    db.commit()


def trace_report_sources(db):
    """Snapshot HEAD/main/open PR blobs, including sparse-excluded .json*.gz.

    Entire reported run families are protected, even when a script constructs a
    filename dynamically or selects only some frames. No attempt to infer a
    safe complement from an evaluator's stride/glob is made.
    """
    branches = json.loads(subprocess.check_output([
        'gh', 'pr', 'list', '--state', 'open', '--limit', '100',
        '--json', 'number,headRefName,headRefOid'], cwd=REPO))
    sources = [{'ref': 'HEAD', 'sha': git('rev-parse', 'HEAD').decode().strip()},
               {'ref': 'origin/main', 'sha': git('rev-parse', 'origin/main').decode().strip()}]
    sources += [{'ref': 'origin/' + b['headRefName'], 'sha': b['headRefOid'], 'pr': b['number']}
                for b in branches if b['number'] != 309]
    db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('source_refs', json.dumps(sources)))
    blobs = {}
    tree_paths = {}
    for source in sources:
        for entry in git('ls-tree', '-r', '-z', source['sha']).split(b'\0'):
            if not entry:
                continue
            meta, path = entry.split(b'\t', 1)
            mode, kind, oid = meta.decode().split()
            path = path.decode()
            if kind != 'blob':
                continue
            structured = path.startswith('experiments/') and graph.structured_suffix(path)
            report = path == 'docs/current_status.md' or (path.startswith('experiments/') and path.endswith('.md'))
            script = path.startswith(('scripts/', 'experiments/', 'harness/')) and path.endswith('.py')
            if structured or report or script:
                blobs.setdefault(oid, (source['sha'] + ':' + path, path, structured, report, script))
                tree_paths.setdefault(path, set()).add(oid)
    units = sorted({unit(p) for p, in db.execute('SELECT path FROM files')}, key=len, reverse=True)
    # Search by actual inventory identities; avoids inventing a stem/date map.
    unit_pattern = re.compile(r'(?<![\w.-])(?:' + '|'.join(re.escape(u) for u in units) + r')(?![\w.-])')
    script_refs = collections.defaultdict(set)
    script_texts = {}
    report_folders = collections.defaultdict(set)
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for n, (oid, (source, path, structured, report, script)) in enumerate(blobs.items(), 1):
            proc.stdin.write((oid + '\n').encode()); proc.stdin.flush()
            header = proc.stdout.readline().split()
            raw = proc.stdout.read(int(header[2])); proc.stdout.read(1)
            digest = hashlib.sha256(raw).hexdigest()
            count = 0
            if structured:
                try:
                    content = gzip.decompress(raw) if path.endswith('.gz') else raw
                    count = collect_stream(db, source, io.BytesIO(content), structured)
                except (ValueError, OSError, TypeError, OverflowError) as e:
                    db.execute('INSERT OR REPLACE INTO errors VALUES(?,?)', (source, type(e).__name__))
                    # At minimum protect every family that can be named in even
                    # a malformed source; also retain residual media below.
                db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?)', (source, digest, len(raw), 'tracked', count))
            if report or script:
                # A retention planner's own stat/hash reads are not scientific
                # analysis dependencies (otherwise discovery protects itself).
                # Its JSON/CSV *content references* were still scanned above.
                if path.startswith('experiments/2026-09-30-outputs-retention/'):
                    continue
                text = raw.decode('utf-8')
                if report:
                    # Retention proposals are not research claims. Their JSON/
                    # CSV references ARE scanned above, without an exception.
                    if path.startswith('experiments/2026-09-30-outputs-retention/'):
                        continue
                    roots = set(unit_pattern.findall(text))
                    for folder in roots:
                        add_folder(db, folder, source, 'reported_run_conservative_closure')
                    report_folders[path.rpartition('/')[0]].update(roots)
                    for script_path in re.findall(r'(?:scripts|experiments|harness)/[\w./-]+\.py', text):
                        script_refs[script_path].add(source)
                    for line_no, line in enumerate(text.splitlines(), 1):
                        db.executemany('INSERT OR IGNORE INTO refs VALUES(?,?,?)',
                                       [(k, t, source + f':{line_no}') for k, t in graph.references(line)])
                elif script:
                    script_texts[(path, oid)] = (source, text)
            if n % 1000 == 0:
                db.commit(); print('tracked blobs', n, '/', len(blobs), flush=True)
    finally:
        proc.stdin.close(); proc.wait()
    traces = []
    reviewer_readers = {
        'scripts/build_carry_act_data.py', 'scripts/train_carry_input_act.py',
        'scripts/dispatch_pair_skill.py', 'harness/camera_varied_start_student.py',
        'harness/vision_pose_source.py', 'harness/vision_loc_client.py',
    }
    for (path, oid), (source, text) in sorted(script_texts.items()):
        name = Path(path).name
        selected = (name.startswith(('eval_', 'analyze_', 'audit_')) or name == 'sim_equivalence.py'
                    or path in script_refs or path in reviewer_readers or path.startswith('experiments/'))
        if not selected:
            continue
        tree = ast.parse(text)
        reads = []
        roots = set(unit_pattern.findall(text))
        roots.update(report_folders.get(path.rpartition('/')[0], set()))
        cited_by = script_refs.get(path, set())
        for report_source in cited_by:
            report_path = report_source.split(':', 1)[1]
            roots.update(report_folders.get(report_path.rpartition('/')[0], set()))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ''
                if name in {'glob', 'rglob', 'read_bytes', 'read_text', 'open', 'imread', 'load', 'loadtxt', 'genfromtxt', 'read_csv', 'read_json',
                            'observe', 'predict_student', 'predict_stage', 'imdecode', 'cvtColor', 'post'}:
                    reads.append({'line': node.lineno, 'operation': name,
                                  'expression': ast.get_source_segment(text, node)[:400]})
        if not reads:
            continue
        for folder in roots:
            add_folder(db, folder, source, 'analysis_script_input_directory')
        traces.append({'script': source, 'git_blob': oid, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                       'cited_by': sorted(cited_by), 'protected_families': sorted(roots), 'reads': reads,
                       'scope': 'whole reported/input family including glob directories; unresolved residual media stays protected'})
    write_json(DEST / 'round3-script-inputs.json', {'scripts': traces})
    db.commit()


def collect_local_experiments(db):
    """Include on-disk/untracked records too, not just Git's sparse inventory."""
    for base in [REPO / 'experiments', Path('/Users/changmin/projects/ugrp/experiments')]:
        for directory, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(directory) / d).is_symlink()]
            for name in names:
                path = Path(directory) / name
                suffix = graph.structured_suffix(path)
                if not suffix or path.is_symlink():
                    continue
                source = ('worktree/' if base.parent == REPO else 'primary/') + str(path.relative_to(base.parent))
                if db.execute('SELECT 1 FROM sources WHERE source=?', (source,)).fetchone():
                    continue
                before = path.stat()
                try:
                    with graph.open_record(path) as stream:
                        count = collect_stream(db, source, stream, suffix)
                    digest = sha256(path)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError('changed local experiment source')
                    db.execute('INSERT INTO sources VALUES(?,?,?,?,?)', (source, digest, before.st_size, 'parsed', count))
                except (ValueError, OSError, TypeError, OverflowError) as e:
                    db.execute('INSERT OR REPLACE INTO errors VALUES(?,?)', (source, type(e).__name__))
    db.commit()


def resolve_references(db, root):
    db.execute("DELETE FROM meta WHERE key='reviewer_match'")
    db.execute('CREATE TABLE IF NOT EXISTS matched_refs(kind TEXT,target TEXT,PRIMARY KEY(kind,target))')
    db.execute('DELETE FROM matched_refs')
    db.execute("DELETE FROM folders WHERE reason IN ('referenced_glob_directory','referenced_input_directory')")
    db.execute('UPDATE files SET protection=NULL,source=NULL WHERE protection IS NOT NULL OR source IS NOT NULL')
    db.commit()
    # Direct output roots are dependencies too. An input may live outside its
    # consumer's directory (ACT training from retired realtime is one example).
    directories = {p for p, in db.execute('SELECT path FROM files WHERE mode & 61440=16384')}
    exact_glob_files = []
    for target, source in db.execute("SELECT target,source FROM refs WHERE kind='output'"):
        prefix = graph.glob_parent(target)
        if prefix in directories:
            add_folder(db, prefix, source, 'referenced_input_directory')
            db.execute('INSERT OR IGNORE INTO matched_refs VALUES(?,?)', ('output', target))
        elif any(c in target for c in '*?['):
            # A first-component wildcard selects known families. A placeholder
            # such as outputs/{run}/... is not an actual root-wide glob.
            if not prefix:
                # SQLite GLOB narrows the same full-path pattern; final match
                # uses Python fnmatchcase. [!...] is SQLite's [^...].
                for path, mode in db.execute('SELECT path,mode FROM files WHERE path GLOB ?',
                                             (target.replace('[!', '[^'),)):
                    folder = graph.matched_glob_folder(target, path, stat.S_ISDIR(mode))
                    if folder is not None:
                        add_folder(db, folder, source, 'referenced_glob_directory')
                        db.execute('INSERT OR IGNORE INTO matched_refs VALUES(?,?)', ('output', target))
                    elif fnmatch.fnmatchcase(path, target):
                        exact_glob_files.append(('output', path, source))
    db.executemany('INSERT OR IGNORE INTO refs VALUES(?,?,?)', exact_glob_files)
    # Reverse suffix index via Python maps. A relative rgb/foo.jpg appearing
    # anywhere protects that suffix in EVERY run, never only the first hit.
    def ref_map(kind):
        return {sys.intern(target): sys.intern(source) for target, source in db.execute(
            'SELECT target,source FROM refs WHERE kind=?', (kind,))}
    image_refs = ref_map('image')
    hashes = ref_map('sha256')
    outputs = ref_map('output')
    folders = collections.defaultdict(list)
    for folder, source, reason in db.execute('SELECT folder,source,reason FROM folders ORDER BY reason,folder'):
        folders[folder].append((source, reason))
    exclusions = json.loads((DEST / 'reviewer-exclusions.json').read_text())
    matched_review = hashlib.sha256()
    review_totals = collections.Counter()
    row_count = db.execute('SELECT count(*) FROM files').fetchone()[0]
    rows = db.execute('SELECT path,size,allocated,mtime,mode,sha,old_action,rule FROM files ORDER BY path')
    # Every file in the frozen proposal already has a full verified hash.
    # Live/recent/unlisted files are unconditionally protected by scope; do not
    # freeze a running producer's images merely to rediscover that protection.
    for n, (p, size, allocated, stamp, mode, digest, old_action, rule) in enumerate(rows, 1):
        if not stat.S_ISREG(mode):
            continue
        parts = p.split('/')
        image = Path(p).suffix.lower() in graph.IMAGE_EXTENSIONS
        if image and not digest and old_action is not None:
            before = (root / p).stat(follow_symlinks=False)
            digest = sha256(root / p)
            after = (root / p).stat(follow_symlinks=False)
            if (before.st_size, before.st_mtime_ns, after.st_size, after.st_mtime_ns) != (size, stamp, size, stamp):
                digest = None
                db.execute('UPDATE files SET protection=?,source=? WHERE path=?',
                           ('changed_during_hash', 'outputs/' + p, p))
            else:
                db.execute('UPDATE files SET sha=? WHERE path=?', (digest, p))
        reasons = []
        review = graph.exclusion_ids(p, exclusions)
        if review:
            reasons.append(('reviewer:' + ','.join(review), 'reviewer-exclusions.json'))
            if old_action == 'delete':
                matched_review.update((p + '\n').encode())
                review_totals.update(files=1, bytes=size, allocated_bytes=allocated)
        if digest in hashes:
            reasons.append(('content_sha256_reference', hashes[digest]))
            db.execute('INSERT OR IGNORE INTO matched_refs VALUES(?,?)', ('sha256', digest))
        if p in outputs:
            reasons.append(('explicit_output_reference', outputs[p]))
            db.execute('INSERT OR IGNORE INTO matched_refs VALUES(?,?)', ('output', p))
        for i in range(len(parts)):
            suffix = '/'.join(parts[i:])
            if suffix in image_refs:
                reasons.append(('image_path_reference', image_refs[suffix]))
                db.execute('INSERT OR IGNORE INTO matched_refs VALUES(?,?)', ('image', suffix))
                break
        for i in range(len(parts) + 1):
            ancestor = '/'.join(parts[:i])
            if ancestor in folders:
                source, reason = folders[ancestor][0]
                reasons.append((reason, source))
        # Proving absence of arbitrary dynamic Python I/O is not possible from
        # a static graph. Unresolved render/retired bulk is uncertainty, never a
        # newly asserted safe negative. Only caches/exact reconstructions can
        # survive without a complete producer/consumer binding in this batch.
        if old_action == 'delete' and rule in {'D1', 'D2'} and not reasons:
            reasons.append(('unresolved_producer_consumer', 'round3 conservative fail-closed'))
        if old_action is None:
            reasons.append(('outside_frozen_round2_scope', 'inventory: live/recent/unlisted files are never added as candidates'))
        if reasons:
            reason, source = reasons[0]
            db.execute('UPDATE files SET protection=?,source=? WHERE path=?', (reason, source, p))
        if n % 100000 == 0:
            db.commit(); print('classify', n, '/', row_count, flush=True)
    actual = dict(review_totals)
    actual['sorted_paths_lf_sha256'] = matched_review.hexdigest()
    expected = exclusions['union_delete_totals']
    for key, value in actual.items():
        if expected[key] != value:
            raise RuntimeError(f'reviewer exclusion mismatch: {key}: {value} != {expected[key]}')
    db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('reviewer_match', json.dumps(actual)))
    db.commit()


def emit(db, root):
    if db.execute("SELECT value FROM meta WHERE key='reviewer_match'").fetchone() is None:
        raise RuntimeError('classify phase has not completed; no manifest may be emitted')
    old = json.loads((DEST / 'round2-manifest.json').read_text())
    lists, totals = {}, {}
    for action in ['delete', 'keep']:
        directory = DEST / ('round3-' + action)
        directory.mkdir(exist_ok=True)
        # Re-generation replaces only this tool's worktree products.
        for p in directory.glob('*.jsonl'):
            p.unlink()
        condition = "old_action='delete' AND protection IS NULL" if action == 'delete' else "old_action IS NOT NULL AND NOT (old_action='delete' AND protection IS NULL)"
        rows = db.execute(f'''SELECT path,size,allocated,mtime,sha,rule,reason FROM files
                              WHERE {condition} ORDER BY path''')
        entries, total = [], collections.Counter()
        groups = collections.defaultdict(list)
        # Sorting by (folder,basename) is distinct from sorting full paths.
        for p, size, allocated, stamp, digest, rule, reason in rows:
            folder, _, name = p.rpartition('/')
            groups[folder].append((name, size, allocated, stamp, digest, rule, reason))
        handle = None
        outfile = None
        part = part_size = part_batches = 0
        def close():
            nonlocal handle
            if handle:
                handle.close()
                entries.append({'path': str(outfile.relative_to(DEST)), 'sha256': sha256(outfile), 'batches': part_batches})
                handle = None
        def output(folder, group):
            nonlocal handle, part, part_size, part_batches, outfile
            records = [{'name': r[0], 'bytes': r[1], 'mtime_ns': r[3], 'sha256': r[4]} for r in group]
            row = {'folder': folder, 'files': len(group), 'bytes': sum(r[1] for r in group),
                   'allocated_bytes': sum(r[2] for r in group),
                   'names_zlib_base64': batches.pack_names([r[0] for r in group]),
                   'content_sha256': batches.digest_records(records)}
            if action == 'delete':
                row.update(rule_id=group[0][5], reason=group[0][6])
            raw = batches.canonical(row)
            if handle is None or part_size + len(raw) > 850000:
                close(); part += 1
                outfile = directory / f'{part:03d}.jsonl'
                handle = outfile.open('wb'); part_size = part_batches = 0
            handle.write(raw); part_size += len(raw); part_batches += 1
            total.update({k: row[k] for k in ('files', 'bytes', 'allocated_bytes')})
        for folder, items in sorted(groups.items()):
            group, prior = [], None
            for row in sorted(items):
                key = (row[5], row[6]) if action == 'delete' else None
                if group and (len(group) == 512 or key != prior):
                    output(folder, group); group = []
                group.append(row); prior = key
            if group:
                output(folder, group)
        close()
        lists[action + '_lists'] = entries
        totals[action] = {key: total[key] for key in ('files', 'bytes', 'allocated_bytes')}
        print('emit', action, totals[action], flush=True)
    # Additive per-family accounting; no claim that live writes have stopped.
    families = collections.defaultdict(collections.Counter)
    reasons = collections.defaultdict(collections.Counter)
    deleted_paths = set()
    seen_inodes = set()
    for p, size, allocated, mode, old_action, protection, rule, dev, ino in db.execute(
            'SELECT path,size,allocated,mode,old_action,protection,rule,dev,ino FROM files ORDER BY path'):
        value = families[unit(p)]
        value['before_allocated_bytes'] += 0 if (dev, ino) in seen_inodes else allocated
        seen_inodes.add((dev, ino))
        if stat.S_ISREG(mode):
            value['files_before'] += 1
            value['before_bytes'] += size
        if old_action == 'delete':
            value['round2_delete_allocated_bytes'] += allocated
            r = reasons[protection or ('candidate:' + rule)]
            r.update(files=1, bytes=size, allocated_bytes=allocated)
            if not protection:
                value.update(delete_files=1, delete_bytes=size, delete_allocated_bytes=allocated)
                deleted_paths.add(p)
    with (DEST / 'manifest.csv').open('w') as f:
        keys = ['path', 'files_before', 'before_bytes', 'before_allocated_bytes', 'round2_delete_allocated_bytes',
                'delete_files', 'delete_bytes', 'delete_allocated_bytes', 'after_allocated_bytes']
        writer = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); writer.writeheader()
        for family, value in sorted(families.items()):
            value['after_allocated_bytes'] = value['before_allocated_bytes'] - value['delete_allocated_bytes']
            writer.writerow({'path': family, **{k: value[k] for k in keys if k != 'path'}})
    # Filter D5 restoration links rather than leaving stale mappings executable.
    reconstruction = []
    for file in sorted((DEST / 'json-reconstruction').glob('*.csv')):
        with file.open() as f:
            for row in csv.DictReader(f):
                if row['deleted_path'] in deleted_paths:
                    reconstruction.append(row)
    if reconstruction:
        with (DEST / 'round3-json-reconstruction.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=list(reconstruction[0]), lineterminator='\n')
            writer.writeheader(); writer.writerows(reconstruction)
    else:
        (DEST / 'round3-json-reconstruction.csv').write_text('deleted_path,retained_source,bytes,sha256,reconstruction_rule\n')
    report = {'schema': 'ugrp.retention-evidence-graph.v1', 'round': 3,
              'audit_code': [{'path': str(path.relative_to(REPO)), 'sha256': sha256(path)}
                             for path in [Path(__file__), REPO / 'scripts/outputs_retention_graph.py']],
              'measured': json.loads(db.execute("SELECT value FROM meta WHERE key='inventory'").fetchone()[0]),
              'reviewer_match': json.loads(db.execute("SELECT value FROM meta WHERE key='reviewer_match'").fetchone()[0]),
              'source_count': db.execute('SELECT count(*) FROM sources').fetchone()[0],
              'reference_counts': dict(db.execute('SELECT kind,count(*) FROM refs GROUP BY kind')),
              'source_errors': [{'source': p, 'kind': k} for p, k in db.execute('SELECT * FROM errors ORDER BY source')],
              'folder_edges': db.execute('SELECT count(*) FROM folders').fetchone()[0],
              'round2_reclassification': dict(sorted(reasons.items())),
              'delete_totals': totals['delete'], 'keep_totals': totals['keep'],
              'inventory_allocated_bytes': sum(row['before_allocated_bytes'] for row in families.values()),
              'projected_allocated_bytes': sum(row['after_allocated_bytes'] for row in families.values()),
              'reference_scope': 'all regular JSON/JSONL/CSV/TSV/log/txt (also gzip) in outputs, both local experiments trees, and experiments HEAD/main/open PR blobs; all keys and string values; inline images; report/script directory closure; symlinks not followed',
              'uncertainty': 'unresolved D1/D2 media/bulk and unreadable/changing producer families remain protected',
              'hash_scope': 'all round2 delete+keep files verified in full; incoming records from all scopes scanned; unlisted/live/recent files protected regardless of whether a content hash was frozen',
              'actual_deleted_files': 0, 'd5_reconstruction_rows': len(reconstruction)}
    write_json(DEST / 'round3-graph-summary.json', report)
    questions = []
    for identifier, title, prefixes, loss, sources in [
        ('Q1', '9/25 TOP RGB 작업 결과 판정 v1/v2',
         ['zone-rgb-outcome-20260925', 'zone-rgb-outcome-v2-20260925'],
         '전후·시계열 픽셀에서 delivered/미확정 판정과 false-delivered 수치를 다시 계산하거나 판정 시점을 감사할 수 없음',
         ['experiments/2026-09-25-zone-rgb-outcome/README.md', 'scripts/eval_zone_rgb_outcome.py']),
        ('Q2', '9/25 상자 4색 검출 평가', ['zone-rgb-color-20260925'],
         'RGB와 정답 segmentation에서 오검출·색별 재현율·위치 오차를 다시 채점할 수 없음',
         ['experiments/2026-09-25-zone-rgb-color/README.md', 'scripts/eval_zone_color_detection.py']),
        ('Q3', '9/25 AprilTag 자기 카메라 위치 추정 오프라인 평가', ['owncam-loc-20260925'],
         '태그 재검출→위치 추정→오차 점수와 자세별 태그 가시율을 원본 영상에서 다시 검증할 수 없음',
         ['experiments/2026-09-25-zone-owncam-loc/README.md', 'scripts/eval_owncam_localization.py']),
    ]:
        counts = collections.Counter()
        names = hashlib.sha256(); contents = hashlib.sha256()
        for p, size, allocated, digest in db.execute('SELECT path,size,allocated,sha FROM files ORDER BY path'):
            if Path(p).suffix.lower() not in graph.IMAGE_EXTENSIONS or not any(graph.under(p, prefix) for prefix in prefixes):
                continue
            if p in deleted_paths or not digest:
                raise RuntimeError(f'optional question must be fully retained and hashed: {p}')
            counts.update(files=1, bytes=size, allocated_bytes=allocated)
            names.update((p + '\n').encode())
            contents.update(batches.canonical([p, size, digest]))
        questions.append({'id': identifier, 'research_line': title, 'prefixes': prefixes,
                          'selector': 'all image extensions in these families; no JSON/JSONL/CSV/models/video',
                          **counts, 'allocated_gib': counts['allocated_bytes'] / 2**30,
                          'sorted_paths_lf_sha256': names.hexdigest(),
                          'content_records_sha256': contents.hexdigest(),
                          'lost_capability': loss, 'evidence': sources, 'decision': 'KEEP; user decision pending'})
    write_json(DEST / 'round3-optional-decisions.json', {
        'schema': 'ugrp.retention-optional-questions.v1', 'executable': False,
        'scope': 'research-retirement questions only; current manifest preserves every file; coordinator must ask user and build/review a separate exact manifest after any decision',
        'model_input_note': 'E1/E2 learned input families and training checkpoints are not offered; cross-study input dependencies must still be checked before any later deletion',
        'questions': questions})
    # Compressed metadata records (not raw media); each sidecar stays <1 MiB.
    for label, query in [
        ('sources', 'SELECT source,sha,size,status,references_count FROM sources ORDER BY source'),
        ('folders', 'SELECT folder,source,reason FROM folders ORDER BY folder,reason'),
        # Unmatched arbitrary hex strings in logs are not published: they may
        # be identifiers/secrets rather than file digests. Only content-bound
        # reference edges that match this inventory are review artifacts.
        ('refs', 'SELECT r.kind,r.target,r.source FROM refs r JOIN matched_refs m USING(kind,target) ORDER BY kind,target'),
        ('protected', 'SELECT path,protection,source FROM files WHERE protection IS NOT NULL ORDER BY path')]:
        outdir = DEST / ('round3-graph-' + label); outdir.mkdir(exist_ok=True)
        for oldfile in outdir.glob('*.jsonl'):
            oldfile.unlink()
        chunk, records, part, index = [], [], 0, []
        encoded_size = 0
        def flush():
            nonlocal chunk, encoded_size, part
            if not chunk:
                return
            part += 1
            path = outdir / f'{part:03d}.jsonl'
            path.write_bytes(b''.join(chunk))
            index.append({'path': str(path.relative_to(DEST)), 'sha256': sha256(path), 'batches': len(chunk)})
            chunk = []; encoded_size = 0
        def encode():
            nonlocal records, encoded_size
            if not records:
                return
            raw = batches.canonical(records)
            packed = batches.canonical({'fields': fields, 'rows': len(records),
                'encoding': 'zlib+base64 canonical JSON array of rows',
                'uncompressed_sha256': hashlib.sha256(raw).hexdigest(),
                'entries_zlib_base64': base64.b64encode(zlib.compress(raw, 9)).decode()})
            if encoded_size + len(packed) > 850000:
                flush()
            chunk.append(packed); encoded_size += len(packed); records = []
        cursor = db.execute(query)
        fields = [r[0] for r in cursor.description]
        for row in cursor:
            records.append(row)
            if len(records) == 512:
                encode()
        encode()
        flush()
        write_json(DEST / f'round3-graph-{label}.json', index)
    manifest = {k: v for k, v in old.items() if k not in {'delete_lists', 'keep_lists', 'evidence_files', 'summary', 'folder_summary'}}
    manifest.update(**lists, outputs_root=str(root), delete_totals=totals['delete'], keep_totals=totals['keep'],
                    created_unix=time.time(), proposal_round=3,
                    rules={**old['rules'], 'D1': 'no eligible files: content/reference or unresolved producer protection',
                           'D2': 'no eligible files: reviewer exclusion/evidence protection'},
                    source_refs=json.loads(db.execute("SELECT value FROM meta WHERE key='source_refs'").fetchone()[0]),
                    supersedes={'round': 2, 'manifest_sha256': sha256(DEST / 'round2-manifest.json')},
                    execution_approval='DO NOT EXECUTE: read-only proposal; coordinator requests user decisions and independent re-review',
                    folder_summary={'path': 'manifest.csv', 'sha256': sha256(DEST / 'manifest.csv')})
    evidence_names = ['reviewer-exclusions.json', 'round3-graph-summary.json', 'round3-script-inputs.json',
                      'round3-json-reconstruction.csv', 'round3-optional-decisions.json']
    for label in ['sources', 'folders', 'refs', 'protected']:
        index = DEST / f'round3-graph-{label}.json'
        evidence_names.append(index.name)
        evidence_names.extend(item['path'] for item in json.loads(index.read_text()))
    manifest['evidence_files'] = [{'path': name, 'sha256': sha256(DEST / name)} for name in evidence_names]
    write_json(DEST / 'manifest.json', manifest)
    print('manifest', sha256(DEST / 'manifest.json'), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['inventory', 'references', 'classify', 'emit'])
    parser.add_argument('--root', type=Path, default=Path('/Users/changmin/projects/ugrp/outputs'))
    parser.add_argument('--scratch', type=Path, default=Path('/private/tmp/outputs-retention-r3'))
    args = parser.parse_args()
    root = args.root.resolve()
    scratch = args.scratch.resolve()
    if DEST.resolve().is_relative_to(root) or scratch.is_relative_to(root):
        raise SystemExit('outputs root is read-only: artifacts/scratch must be outside it')
    scratch.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(scratch / 'graph.sqlite')
    db.execute('PRAGMA journal_mode=WAL')
    if args.phase == 'inventory':
        inventory(db, root)
    elif args.phase == 'references':
        collect_raw(db, root)
        collect_local_experiments(db)
        trace_report_sources(db)
    elif args.phase == 'classify':
        resolve_references(db, root)
    else:
        emit(db, root)
    db.close()


if __name__ == '__main__':
    main()
