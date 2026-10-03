"""Bounded-memory v3 retention batches and crash-resumable unlink journal.

Only explicit, hash-bound filenames are used. No globs, recursive deletion or
candidate discovery. A durable pending batch bridges unlink/journal crashes;
missing files are accepted ONLY there and reported as recovered_absent.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid
import zlib

from scripts.outputs_prune import (MIN_AGE_SECONDS, Refusal, assert_idle,
                                   no_symlinks, protected, relative_path, sha256)

SCHEMA = 'ugrp.outputs-retention.v3'
MAX_BATCH = 512
MAX_LINE = 1024 * 1024


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, separators=(',', ':')) + '\n').encode()


def pack_names(names):
    return base64.b64encode(zlib.compress(canonical(names), 9)).decode('ascii')


def unpack_names(row):
    packed = base64.b64decode(row['names_zlib_base64'], validate=True)
    d = zlib.decompressobj()
    raw = d.decompress(packed, MAX_LINE + 1)
    if len(raw) > MAX_LINE or not d.eof or d.unused_data:
        raise Refusal('invalid or oversized filename list')
    names = json.loads(raw)
    if not isinstance(names, list) or not 0 < len(names) <= MAX_BATCH:
        raise Refusal('invalid batch size')
    if names != sorted(set(names)):
        raise Refusal('filenames must be unique and sorted')
    for name in names:
        if len(relative_path(name).parts) != 1:
            raise Refusal('batch must contain immediate filenames')
    if row['files'] != len(names):
        raise Refusal('batch file count mismatch')
    return names


def rows(manifest, manifest_path, action):
    previous = None
    for entry in manifest[action + '_lists']:
        p = manifest_path.parent.joinpath(*relative_path(entry['path']).parts)
        no_symlinks(p)
        if sha256(p) != entry['sha256']:
            raise Refusal(f'{action}-list hash changed: {p}')
        count = 0
        with p.open('rb') as stream:
            while line := stream.readline(MAX_LINE + 1):
                if len(line) > MAX_LINE:
                    raise Refusal('oversized batch record')
                row = json.loads(line)
                folder = row['folder']
                if folder:
                    rel = relative_path(folder)
                    if action == 'delete' and protected(rel):
                        raise Refusal(f'protected infrastructure: {folder}')
                if action == 'delete' and (row.get('rule_id') not in {'D1', 'D2', 'D3', 'D5'} or not row.get('reason')):
                    raise Refusal('missing deletion decision evidence')
                names = unpack_names(row)
                if action == 'delete' and any(protected(relative_path('/'.join(filter(None, (folder, n))))) for n in names):
                    raise Refusal('protected infrastructure filename')
                first, last = (folder, names[0]), (folder, names[-1])
                if previous is not None and first <= previous:
                    raise Refusal('overlapping or unsorted batch filenames')
                previous = last
                count += 1
                yield row, names
        if count != entry['batches']:
            raise Refusal('list batch count mismatch')


def assert_disjoint(manifest, path):
    def keys(action):
        for row, names in rows(manifest, path, action):
            for name in names:
                yield row['folder'], name
    left, right = iter(keys('delete')), iter(keys('keep'))
    a, b = next(left, None), next(right, None)
    while a is not None and b is not None:
        if a == b:
            raise Refusal(f'deletion overlaps kept file: {a}')
        if a < b:
            a = next(left, None)
        else:
            b = next(right, None)
    # Exhaust both to validate every sidecar and its global ordering.
    for _ in left:
        pass
    for _ in right:
        pass


@contextmanager
def directory_fd(root, folder):
    no_symlinks(root)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative_path(folder).parts if folder else ():
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def file_record(fd, name, *, deletion=False):
    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise Refusal(f'non-regular file or symlink: {name}')
    if deletion and before.st_mtime > time.time() - MIN_AGE_SECONDS:
        raise Refusal(f'modified within 24 hours: {name}')
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    try:
        if identity(os.fstat(handle)) != identity(before):
            raise Refusal(f'changed during open: {name}')
        with os.fdopen(os.dup(handle), 'rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if identity(os.fstat(handle)) != identity(before) or identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != identity(before):
            raise Refusal(f'changed during hash: {name}')
    finally:
        os.close(handle)
    return {'name': name, 'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns,
            'allocated_bytes': before.st_blocks * 512, 'sha256': digest,
            'identity': list(identity(before))}


def digest_records(records):
    digest = hashlib.sha256()
    for r in records:
        digest.update(canonical([r['name'], r['bytes'], r['mtime_ns'], r['sha256']]))
    return digest.hexdigest()


def validate_records(row, names, records):
    if ([r['name'] for r in records] != names or
            digest_records(records) != row['content_sha256'] or
            sum(r['bytes'] for r in records) != row['bytes']):
        raise Refusal(f'batch content changed: {row["folder"]}')


def verify_batch(root, row, names, *, deletion=False):
    with directory_fd(root, row['folder']) as fd:
        records = [file_record(fd, name, deletion=deletion) for name in names]
    validate_records(row, names, records)
    return records


def atomic_json(path, data):
    no_symlinks(path)
    tmp = path.parent / (path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('xb') as stream:
        stream.write(canonical(data))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def progress(stage, n, files, every):
    if every and (n == 1 or n % every == 0):
        print(f'{stage}: {n} batches / {files:,} files', file=sys.stderr, flush=True)


def _receipt_paths(root, resume):
    base = root / 'prune-receipts'
    no_symlinks(base)
    if resume:
        receipt = Path(resume).absolute()
        if receipt.parent != base or receipt.suffix != '.json':
            raise Refusal('resume must be a receipt inside outputs/prune-receipts')
        no_symlinks(receipt)
    else:
        receipt = base / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex + '.json')
    return receipt, receipt.with_suffix('.done.jsonl'), receipt.with_suffix('.pending.json')


def read_journal(path):
    """A torn final append is ignored; durable pending intent recovers it."""
    no_symlinks(path)
    if not path.exists():
        return [], 0
    events, end = [], 0
    with path.open('rb') as stream:
        while line := stream.readline(MAX_LINE + 1):
            if len(line) > MAX_LINE:
                raise Refusal('oversized journal record')
            if not line.endswith(b'\n'):
                break
            e = json.loads(line)
            if e['batch_index'] != len(events):
                raise Refusal('noncontiguous resume journal')
            events.append(e)
            end = stream.tell()
    return events, end


def _relative(folder, name):
    return folder + '/' + name if folder else name


def _unlink_pending(root, row, records):
    deleted, recovered = 0, 0
    with directory_fd(root, row['folder']) as fd:
        for i, expected in enumerate(records):
            assert_idle(root)
            name = expected['name']
            try:
                actual = file_record(fd, name, deletion=True)
            except FileNotFoundError:
                recovered += 1
                continue
            if actual != expected:
                raise Refusal(f'changed after pending intent: {_relative(row["folder"], name)}')
            # Recheck the directory binding: a renamed parent must not redirect deletion.
            with directory_fd(root, row['folder']) as current:
                if (os.fstat(current).st_dev, os.fstat(current).st_ino) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino):
                    raise Refusal('directory replaced during deletion')
            os.unlink(name, dir_fd=fd)
            deleted += 1
        os.fsync(fd)
    return deleted, recovered


def prune_stream(manifest_path, *, execute=False, root, resume=None, progress_every=100):
    root = Path(root).absolute()
    manifest_path = Path(manifest_path).absolute()
    no_symlinks(root)
    if root.name != 'outputs' or not root.is_dir():
        raise Refusal('expected an existing outputs directory')
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get('schema') != SCHEMA or manifest.get('outputs_root') != str(root):
        raise Refusal('manifest schema or outputs root mismatch')
    if resume and not execute:
        raise Refusal('--resume requires --execute')
    for evidence in ([manifest['folder_summary']] if 'folder_summary' in manifest else []) + manifest.get('evidence_files', []):
        p = manifest_path.parent.joinpath(*relative_path(evidence['path']).parts)
        no_symlinks(p)
        if sha256(p) != evidence['sha256']:
            raise Refusal(f'evidence-list hash changed: {p}')
    manifest_sha = hashlib.sha256(raw).hexdigest()
    receipt, journal, pending_path = _receipt_paths(root, resume)
    lock_fd = None
    try:
        if execute:
            assert_idle(root)
            receipt.parent.mkdir(exist_ok=True)
            lockpath = receipt.parent / '.execution.lock'
            no_symlinks(lockpath)
            lock_fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise Refusal('another pruning process is active') from error
        events, journal_end = read_journal(journal) if resume else ([], 0)
        pending = None
        if resume:
            prior = json.loads(receipt.read_bytes())
            if prior.get('manifest_sha256') != manifest_sha or prior.get('outputs_root') != str(root):
                raise Refusal('resume manifest or root mismatch')
            no_symlinks(pending_path)
            if pending_path.exists():
                pending = json.loads(pending_path.read_bytes())
                if pending and pending['batch_index'] < len(events):
                    if pending['batch_index'] != len(events) - 1:
                        raise Refusal('unexpected stale pending batch')
                    pending = None  # journal append committed, cleanup had not run
            if pending and (pending['batch_index'] != len(events) or pending['manifest_sha256'] != manifest_sha):
                raise Refusal('pending batch identity mismatch')
        assert_disjoint(manifest, manifest_path)
        kept_files = 0
        kept_by_folder = {}
        for i, (row, names) in enumerate(rows(manifest, manifest_path, 'keep'), 1):
            verify_batch(root, row, names)
            kept_files += len(names)
            kept_by_folder[row['folder']] = kept_by_folder.get(row['folder'], 0) + len(names)
            progress('verify keep', i, kept_files, progress_every)
        planned_files = planned_bytes = allocated = batch_count = 0
        removed_hash = hashlib.sha256()
        folders = {}
        for i, (row, names) in enumerate(rows(manifest, manifest_path, 'delete')):
            if i < len(events):
                event = events[i]
                if (any(type(event.get(k)) is not int or event[k] < 0 for k in ('deleted_files_observed', 'recovered_absent'))
                        or event['deleted_files_observed'] + event['recovered_absent'] != row['files']):
                    raise Refusal('invalid resume journal counts')
                if event['batch_sha256'] != hashlib.sha256(canonical(row)).hexdigest():
                    raise Refusal('journal does not match manifest batch')
                with directory_fd(root, row['folder']) as fd:
                    for name in names:
                        try:
                            os.stat(name, dir_fd=fd, follow_symlinks=False)
                        except FileNotFoundError:
                            pass
                        else:
                            raise Refusal(f'completed deletion path reappeared: {name}')
                _add_completed(row, names, event, folders, removed_hash)
            elif pending and i == pending['batch_index']:
                validate_records(row, names, pending['records'])
                with directory_fd(root, row['folder']) as fd:
                    for expected in pending['records']:
                        try:
                            actual = file_record(fd, expected['name'], deletion=True)
                        except FileNotFoundError:
                            continue  # durable intent is the ONLY missing-file exception
                        if actual != expected:
                            raise Refusal(f'pending file changed: {expected["name"]}')
            else:
                verify_batch(root, row, names, deletion=True)
            batch_count += 1
            planned_files += row['files']
            planned_bytes += row['bytes']
            allocated += row['allocated_bytes']
            progress('verify delete', batch_count, planned_files, progress_every)
        if len(events) > batch_count or (pending and pending['batch_index'] >= batch_count):
            raise Refusal('resume cursor exceeds manifest')
        summary = {'execute': execute, 'schema': SCHEMA, 'batches': batch_count,
                   'files': planned_files, 'bytes': planned_bytes, 'allocated_bytes': allocated,
                   'kept_files_verified': kept_files, 'manifest_sha256': manifest_sha}
        for key, value in (('files', planned_files), ('bytes', planned_bytes), ('allocated_bytes', allocated)):
            if manifest['delete_totals'][key] != value:
                raise Refusal(f'manifest total mismatch: {key}')
        try:
            assert_idle(root)
            summary['execution_blocker'] = None
        except Refusal as error:
            if execute:
                raise
            summary['execution_blocker'] = str(error)
        if not execute:
            return summary
        result = {**summary, 'schema': 'ugrp.outputs-prune-receipt.v2', 'outputs_root': str(root),
                  'started_unix': prior['started_unix'] if resume else time.time(),
                  'state': 'running', 'completed_batches': len(events)}
        def save():
            # Full batches are committed in the journal. A failed batch may have
            # unlinked files after its durable intent; report those separately
            # instead of losing them from the partial receipt or double counting.
            displayed = {folder: dict(counts) for folder, counts in folders.items()}
            observed_hash = removed_hash.copy()
            pending_missing = 0
            try:
                if pending_path.exists():
                    intent = json.loads(pending_path.read_bytes())
                    if intent and intent['batch_index'] == result['completed_batches']:
                        current_row = next((r for n, (r, _) in enumerate(rows(manifest, manifest_path, 'delete'))
                                            if n == intent['batch_index']), None)
                        if current_row:
                            folder = current_row['folder']
                            counts = displayed.setdefault(folder, {'removed_files': 0, 'removed_bytes': 0,
                                                                    'deleted_files_observed': 0, 'recovered_absent': 0})
                            with directory_fd(root, folder) as fd:
                                for record in intent['records']:
                                    try:
                                        os.stat(record['name'], dir_fd=fd, follow_symlinks=False)
                                    except FileNotFoundError:
                                        pending_missing += 1
                                        counts['removed_files'] += 1
                                        counts['removed_bytes'] += record['bytes']
                                        observed_hash.update((_relative(folder, record['name']) + '\n').encode())
                            counts['pending_absent_uncommitted'] = pending_missing
            except (OSError, Refusal, ValueError, KeyError, TypeError) as error:
                result['pending_receipt_scan_error'] = str(error)
            for folder, counts in displayed.items():
                counts['kept_files_verified'] = kept_by_folder.get(folder, 0)
                # Current immediate file count includes new, unlisted files too.
                if result['state'] != 'running':
                    try:
                        with directory_fd(root, folder) as fd:
                            with os.scandir(fd) as entries:
                                counts['kept_files_after'] = sum(e.is_file(follow_symlinks=False) for e in entries)
                    except (OSError, Refusal) as error:
                        counts['remaining_count_error'] = str(error)
            result.update(folders=displayed, removed_paths_sha256=observed_hash.hexdigest(),
                          deleted_paths_sha256=observed_hash.hexdigest(),
                          completed_batch_paths_sha256=removed_hash.hexdigest(),
                          pending_absent_uncommitted=pending_missing,
                          removed_paths_encoding='UTF-8 relative path + LF, manifest batch order',
                          finished_unix=time.time())
            atomic_json(receipt, result)
        save()
        if resume and journal.exists():
            with journal.open('r+b') as stream:
                stream.truncate(journal_end)
                stream.flush()
                os.fsync(stream.fileno())
        try:
            with journal.open('ab') as log:
                for i, (row, names) in enumerate(rows(manifest, manifest_path, 'delete')):
                    if i < len(events):
                        continue
                    assert_idle(root)
                    if pending and i == pending['batch_index']:
                        records = pending['records']
                    else:
                        records = verify_batch(root, row, names, deletion=True)
                        atomic_json(pending_path, {'batch_index': i, 'manifest_sha256': manifest_sha,
                                                  'records': records})
                    count, recovered = _unlink_pending(root, row, records)
                    event = {'batch_index': i, 'batch_sha256': hashlib.sha256(canonical(row)).hexdigest(),
                             'deleted_files_observed': count, 'recovered_absent': recovered}
                    log.write(canonical(event))
                    log.flush()
                    os.fsync(log.fileno())
                    _add_completed(row, names, event, folders, removed_hash)
                    result['completed_batches'] = i + 1
                    atomic_json(pending_path, None)
                    if (i + 1) % 100 == 0:
                        save()
                    progress('unlink', i + 1, sum(f['removed_files'] for f in folders.values()), progress_every)
            for row, names in rows(manifest, manifest_path, 'keep'):
                verify_batch(root, row, names)
            result.update(state='complete', kept_files_verified_after=kept_files)
        except BaseException as error:
            result.update(state='interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'partial_failure',
                          error=str(error), pending_batch_may_be_partially_removed=True)
            raise
        finally:
            save()
        return {**summary, 'receipt': str(receipt), 'removed_paths_sha256': removed_hash.hexdigest()}
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


def _add_completed(row, names, event, folders, digest):
    folder = row['folder']
    counts = folders.setdefault(folder, {'removed_files': 0, 'removed_bytes': 0,
                                         'deleted_files_observed': 0, 'recovered_absent': 0})
    counts['removed_files'] += row['files']
    counts['removed_bytes'] += row['bytes']
    counts['deleted_files_observed'] += event['deleted_files_observed']
    counts['recovered_absent'] += event['recovered_absent']
    for name in names:
        digest.update((_relative(folder, name) + '\n').encode('utf-8'))
