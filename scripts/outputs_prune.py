#!/usr/bin/env python3
"""Apply a reviewed, explicit outputs retention manifest; default is read-only.

No glob expansion and no candidate discovery happen here. Generate/review a new
manifest when a size, timestamp, content hash, or retained file has changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import time
import uuid

DEFAULT_ROOT = Path('/Users/changmin/projects/ugrp/outputs')
SCHEMA = 'ugrp.outputs-retention.v2'
MIN_AGE_SECONDS = 24 * 60 * 60


class Refusal(RuntimeError):
    """The reviewed batch cannot be applied safely to the current filesystem."""


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\\' in value:
        raise Refusal(f'invalid relative path: {value!r}')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')):
        raise Refusal(f'outside outputs or noncanonical path: {value!r}')
    return p


def no_symlinks(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise Refusal(f'symlink not allowed: {part}')


def protected(rel: PurePosixPath) -> bool:
    return any(p in {'agent-locks', 'prune-receipts'} or p.startswith('tensorboard')
               for p in rel.parts)


def checked_path(root: Path, rel: str, *, deletion: bool = False) -> Path:
    value = relative_path(rel)
    if deletion and protected(value):
        raise Refusal(f'protected infrastructure: {rel}')
    p = root.joinpath(*value.parts)
    no_symlinks(p)
    if not p.exists():
        raise Refusal(f'missing path: {rel}')
    return p


def _file_hash_fd(fd: int) -> str:
    with os.fdopen(os.dup(fd), 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fingerprint(path: Path, *, now: float | None = None, enforce_age: bool = True,
                identities: dict | None = None) -> dict:
    """Hash every regular file and directory, without following symlinks.

    Directory entries and mtimes are part of the digest: adding even an empty
    directory invalidates a reviewed recursive deletion. Bytes are logical;
    allocated_bytes is only a du-style projection, not promised free space.
    """
    no_symlinks(path)
    now = time.time() if now is None else now
    digest = hashlib.sha256()
    totals = {'bytes': 0, 'allocated_bytes': 0, 'files': 0, 'directories': 0}
    newest = 0

    def visit(parent_fd, name, rel):
        nonlocal newest
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):
            raise Refusal(f'non-regular file or symlink: {path}/{rel}')
        if enforce_age and before.st_mtime > now - MIN_AGE_SECONDS:
            raise Refusal(f'modified within 24 hours: {path}/{rel}')
        newest = max(newest, before.st_mtime_ns)
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if stat.S_ISDIR(before.st_mode):
            flags |= os.O_DIRECTORY
        fd = os.open(name, flags, dir_fd=parent_fd)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise Refusal(f'changed during scan: {path}/{rel}')
            kind = 'directory' if stat.S_ISDIR(opened.st_mode) else 'file'
            if identities is not None:
                identities[rel] = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            content_hash = ''
            if kind == 'directory':
                totals['directories'] += 1
            else:
                totals['files'] += 1
                totals['bytes'] += opened.st_size
                content_hash = _file_hash_fd(fd)
            totals['allocated_bytes'] += opened.st_blocks * 512
            digest.update((json.dumps([rel, kind, opened.st_size if kind == 'file' else 0,
                                       opened.st_mtime_ns, content_hash],
                                      ensure_ascii=True, separators=(',', ':')) + '\n').encode())
            if kind == 'directory':
                for child in sorted(os.listdir(fd)):
                    visit(fd, child, f'{rel}/{child}' if rel else child)
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
            if identity(after) != identity(before) or identity(current) != identity(before):
                raise Refusal(f'changed during scan: {path}/{rel}')
        finally:
            os.close(fd)

    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        visit(parent, path.name, '')
    finally:
        os.close(parent)
    return {**totals, 'kind': 'directory' if path.is_dir() else 'file',
            'newest_mtime_ns': newest, 'tree_sha256': digest.hexdigest()}


def assert_idle(root: Path) -> None:
    """agent_lock does not identify output paths, so any live lock blocks all."""
    lockroot = root / 'agent-locks'
    no_symlinks(lockroot)
    if not lockroot.exists():
        return
    for lock in lockroot.iterdir():
        no_symlinks(lock)
        if not lock.is_dir():
            continue  # released.jsonl is history, not a held lock
        owner_path = lock / 'owner.json'
        no_symlinks(owner_path)
        try:
            owner = json.loads(owner_path.read_text())
            pid = owner['pid']
            if type(pid) is not int or pid <= 0:
                raise ValueError('invalid pid')
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise Refusal(f'unknown lock state: {lock}') from error
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass  # Alive but owned by a different user is still active.
        raise Refusal(f'active agent_lock: {lock.name}, pid={pid}')


def load_kept(manifest: dict, manifest_path: Path, root: Path) -> list[dict]:
    kept = list(manifest.get('keep_files', []))
    for entry in manifest.get('keep_lists', []):
        p = manifest_path.parent.joinpath(*relative_path(entry['path']).parts)
        no_symlinks(p)
        if sha256(p) != entry['sha256']:
            raise Refusal(f'keep-list hash changed: {p}')
        kept.extend(json.loads(p.read_text())['files'])
    for row in kept:
        p = checked_path(root, row['path'])
        if not p.is_file() or p.stat().st_size != row['bytes'] or sha256(p) != row['sha256']:
            raise Refusal(f'kept file changed: {row["path"]}')
    return kept


def load_selection(row: dict, manifest_path: Path) -> None:
    entry = row['selection_file']
    p = manifest_path.parent.joinpath(*relative_path(entry['path']).parts)
    no_symlinks(p)
    if sha256(p) != entry['sha256']:
        raise Refusal(f'selection-list hash changed: {p}')
    names = json.loads(p.read_text())['delete_names']
    if not isinstance(names, list) or len(set(names)) != len(names) or not names:
        raise Refusal('selection must be a nonempty unique filename list')
    for name in names:
        if len(relative_path(name).parts) != 1:
            raise Refusal(f'selection must list immediate filenames: {name}')
    row['_delete_names'] = sorted(names)


def validate_plan(manifest: dict, manifest_path: Path, root: Path) -> list[dict]:
    no_symlinks(root)
    if not root.is_dir() or root.name != 'outputs':
        raise Refusal('expected an existing outputs directory')
    if manifest.get('schema') != SCHEMA or manifest.get('outputs_root') != str(root):
        raise Refusal('manifest schema or outputs root mismatch')
    entries = manifest.get('delete')
    if not isinstance(entries, list):
        raise Refusal('delete must be an explicit list')
    paths = []
    for row in entries:
        p = relative_path(row['path'])
        checked_path(root, row['path'], deletion=True)
        if any(p == other or p in other.parents or other in p.parents for other in paths):
            raise Refusal(f'overlapping deletion paths: {p}')
        if not row.get('rule_id') or not row.get('reason'):
            raise Refusal(f'missing decision evidence: {p}')
        if row.get('kind') == 'selection':
            load_selection(row, manifest_path)
        paths.append(p)
    kept = load_kept(manifest, manifest_path, root)
    for row in kept:
        p = relative_path(row['path'])
        for other, deletion in zip(paths, entries):
            overlaps = p == other or other in p.parents
            if overlaps and deletion.get('kind') == 'selection' and p != other:
                overlaps = p.relative_to(other).parts[0] in deletion['_delete_names']
            if overlaps:
                raise Refusal(f'deletion overlaps kept file: {p}')
    return entries


def verify_entry(root: Path, row: dict) -> dict:
    identities = {}
    actual = fingerprint(checked_path(root, row['path'], deletion=True), identities=identities)
    expected = row['snapshot'] if row['kind'] == 'selection' else row
    for key in ('bytes', 'files', 'directories', 'kind', 'newest_mtime_ns', 'tree_sha256'):
        if actual[key] != expected.get(key):
            raise Refusal(f'{key} changed: {row["path"]}')
    if row['kind'] == 'selection':
        files = [checked_path(root, row['path'] + '/' + name, deletion=True) for name in row['_delete_names']]
        if any(not p.is_file() for p in files):
            raise Refusal('selection contains a non-file')
        if sum(p.stat().st_size for p in files) != row['bytes'] or len(files) != row['files']:
            raise Refusal(f'selection size changed: {row["path"]}')
    return identities


def _remove(root: Path, path: Path, identities: dict, record: dict, save, *, names=None) -> None:
    """Unlink through directory fds; never traverse a replacement symlink."""
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.relative_to(root).parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child

        def visit(parent_fd, name, rel):
            assert_idle(root)
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            if identity != identities.get(rel):
                raise Refusal(f'changed after preflight: {path}/{rel}')
            if before.st_mtime > time.time() - MIN_AGE_SECONDS:
                raise Refusal(f'modified within 24 hours during deletion: {rel}')
            if stat.S_ISDIR(before.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
                try:
                    if os.fstat(fd).st_ino != before.st_ino:
                        raise Refusal(f'directory replaced: {rel}')
                    for child in sorted(os.listdir(fd)):
                        visit(fd, child, rel + '/' + child if rel else child)
                    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                        raise Refusal(f'directory replaced: {rel}')
                    os.rmdir(name, dir_fd=parent_fd)
                    record['deleted_directories'] += 1
                finally:
                    os.close(fd)
            elif stat.S_ISREG(before.st_mode):
                os.unlink(name, dir_fd=parent_fd)
                record['deleted_files'] += 1
                record['deleted_bytes'] += before.st_size
            else:
                raise Refusal(f'non-regular file during deletion: {rel}')
            record['last_deleted_path'] = str(path.relative_to(root)) + ('/' + rel if rel else '')

        if names is None:
            visit(parent, path.name, '')
        else:
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                s = os.fstat(fd)
                if (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns) != identities['']:
                    raise Refusal(f'changed after preflight: {path}')
                for name in names:
                    visit(fd, name, name)
            finally:
                os.close(fd)
    finally:
        os.close(parent)
        save()  # Includes partial counts if an OS error interrupted this entry.


def prune(manifest_path: Path, *, execute: bool = False, root: Path = DEFAULT_ROOT) -> dict:
    # root injection is for isolated tests. The CLI always uses DEFAULT_ROOT.
    root = root.absolute()
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    entries = validate_plan(manifest, manifest_path, root)
    summary = {'execute': execute, 'paths': len(entries),
               'bytes': sum(row['bytes'] for row in entries),
               'allocated_bytes': sum(row['allocated_bytes'] for row in entries)}
    # Dry-run reports totals even when a live lock would block execution, but it
    # still verifies every candidate and keep-list without writing any receipt.
    if execute:
        assert_idle(root)
    for row in entries:
        verify_entry(root, row)
    try:
        assert_idle(root)
        summary['execution_blocker'] = None
    except Refusal as error:
        if execute:
            raise
        summary['execution_blocker'] = str(error)
    if not execute:
        return summary

    receipts = root / 'prune-receipts'
    no_symlinks(receipts)
    receipts.mkdir(exist_ok=True)
    receipt = receipts / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex + '.json')
    result = {**summary, 'schema': 'ugrp.outputs-prune-receipt.v1',
              'manifest_sha256': hashlib.sha256(raw).hexdigest(),
              'started_unix': time.time(), 'state': 'running', 'deleted': []}

    def save():
        # Atomic replacement of this process's unique receipt only.
        tmp = receipt.with_suffix('.tmp')
        with tmp.open('x') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, receipt)

    save()
    try:
        for row in entries:
            assert_idle(root)
            identities = verify_entry(root, row)  # Full preflight + immediate per-entry recheck.
            record = {'path': row['path'], 'rule_id': row['rule_id'], 'state': 'deleting',
                      'deleted_files': 0, 'deleted_directories': 0, 'deleted_bytes': 0}
            result['deleted'].append(record)
            save()
            kwargs = {'names': row['_delete_names']} if row['kind'] == 'selection' else {}
            _remove(root, checked_path(root, row['path'], deletion=True), identities, record, save, **kwargs)
            record.update(state='deleted', finished_unix=time.time())
            save()
        result['kept_files_verified_after'] = len(load_kept(manifest, manifest_path, root))
        result['state'] = 'complete'
    except Exception as error:
        result.update(state='partial_failure', error=str(error))
        raise
    finally:
        result['finished_unix'] = time.time()
        save()
    return {**summary, 'receipt': str(receipt)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--execute', action='store_true', help='only after the user approves this batch')
    args = parser.parse_args(argv)
    try:
        result = prune(args.manifest, execute=args.execute)
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
