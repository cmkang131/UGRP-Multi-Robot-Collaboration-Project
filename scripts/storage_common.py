"""Small, dependency-free evidence helpers shared by storage tools."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess

TRACE_LIMIT = 64 * 1024


def files(root: Path):
    """Never follow symlinks, including symlink roots."""
    if root.is_symlink():
        return
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if path.is_file() and not path.is_symlink():
                yield path


def run_dirs(root: Path):
    """Find metadata without stat'ing every raw frame."""
    if root.is_symlink():
        return
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        marker = Path(directory) / 'RUN_META.json'
        if 'RUN_META.json' in names and marker.is_file() and not marker.is_symlink():
            yield Path(directory)


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(path: Path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def atomic_text(path: Path, value: str):
    temporary = path.with_name(path.name + f'.tmp-{os.getpid()}')
    with temporary.open('x') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def persistent(path: Path):
    resolved = path.resolve()
    if any(resolved == p or p in resolved.parents for p in
           (Path('/tmp'), Path('/private/tmp'), Path('/var/tmp'), Path('/dev/shm'), Path('/run'))):
        raise ValueError(f'ephemeral evidence location: {resolved}')
    if Path('/proc/self/mountinfo').exists():
        result = subprocess.run(['findmnt', '-n', '-o', 'FSTYPE', '-T', str(resolved)],
                                capture_output=True, text=True, check=True)
        if result.stdout.strip() in {'tmpfs', 'ramfs'}:
            raise ValueError(f'tmpfs/ramfs evidence location: {resolved}')


def idle_reason(root: Path) -> str | None:
    if root.is_symlink():
        return 'symlink root'
    if not (root / 'EXIT').is_file():
        return 'EXIT absent (unfinished)'
    for parent in (root, *root.parents):
        if any((parent / marker).exists() for marker in ('RUNNING', '.IN_USE', '.TEST_IN_USE')):
            return f'in-use marker: {parent}'
        meta = parent / 'RUN_META.json'
        if meta.is_file():
            data = json.loads(meta.read_text())
            if data.get('active') or data.get('in_use'):
                return f'active RUN_META: {parent}'
    return None


def lock_run(root: Path):
    lock = (root / '.evidence.lock').open('a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        lock.close()
        raise
    return lock


def inventory(root: Path) -> list[dict]:
    rows = []
    for path in files(root):
        if path.name in {'.evidence.lock', 'ALL-hashes.tsv', 'PRUNED-hashes.tsv', 'SHA256SUMS.tsv'}:
            continue
        before = snapshot(path)
        digest = sha256(path)
        if snapshot(path) != before:
            raise ValueError(f'file changed during hashing: {path}')
        rows.append({'path': path.relative_to(root).as_posix(), 'bytes': before[2],
                     'sha256': digest, 'snapshot': before})
    return rows


def hash_tsv(rows: list[dict]) -> str:
    # JSON-encoded path handles tabs/newlines without losing names.
    return 'sha256\tbytes\tpath_json\n' + ''.join(
        f"{r['sha256']}\t{r['bytes']}\t{json.dumps(r['path'], ensure_ascii=False)}\n" for r in rows)
