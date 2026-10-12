"""Opt-in tar/zstd SSH transport; ARM hashes files on its native filesystem.

The receiver is a forced SSH command restricted to one archive directory.
Sources, old incoming trees, and failed native incoming trees are never removed.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

COMMAND = 'ugrp-archive-native-v1'
SCHEMA = 'ugrp.archive-native.v1'
HEADER_LIMIT = 64 * 2**20
RESERVE = 25 * 2**30


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def inventory(folder):
    """Regular files only; fail on links/special files instead of following them."""
    result = {}
    def failed(error):
        raise error
    for directory, dirs, names in os.walk(folder, onerror=failed):
        dirs.sort()
        for name in dirs + sorted(names):
            p = Path(directory) / name
            if p.is_symlink() or not (p.is_file() or p.is_dir()):
                raise ValueError('native transport requires regular files/directories')
            if p.is_dir():
                continue
            before = p.stat()
            with p.open('rb') as stream:
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = p.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise RuntimeError('source changed while hashing')
            result[p.relative_to(folder).as_posix()] = {'bytes': after.st_size, 'sha256': sha}
    return result


def validate(header):
    if header.get('schema') != SCHEMA or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', header['run']):
        raise ValueError('invalid transport header/run')
    hashes = header['inventory']
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('empty/invalid inventory')
    for name, row in hashes.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.as_posix() != name or name in ('', '.'):
            raise ValueError('unsafe inventory path')
        if set(row) != {'bytes', 'sha256'} or type(row['bytes']) is not int or row['bytes'] < 0:
            raise ValueError('invalid inventory size')
        if not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('invalid SHA-256')
    return hashes


def emit(value):
    print(json.dumps(value), flush=True)


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def extract(stream, incoming, hashes):
    """Bound extraction to manifest sizes; refuse links, traversal and extras."""
    seen = set()
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for member in archive:
            name = member.name
            if name.startswith('./'):
                name = name[2:]
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or (name not in ('', '.') and path.as_posix() != name.rstrip('/')):
                raise ValueError('unsafe tar path')
            if member.isdir():
                if name not in ('', '.') and not any(k.startswith(name.rstrip('/') + '/') for k in hashes):
                    # Empty directories carry no file evidence; still bounded by safe paths.
                    continue
            elif not member.isfile() or name not in hashes or name in seen or member.size != hashes[name]['bytes']:
                raise ValueError('tar member outside inventory or duplicate')
            else:
                seen.add(name)
            archive.extract(member, incoming, filter='data')
    if seen != set(hashes):
        raise RuntimeError('incomplete tar inventory')


def receive(archive_root):
    if os.environ.get('SSH_ORIGINAL_COMMAND') != COMMAND:
        raise ValueError('only the archive protocol command is allowed')
    if archive_root.is_symlink() or archive_root.resolve() != archive_root.absolute() or not archive_root.is_dir():
        raise ValueError('archive root must be an existing native directory')
    wire = sys.stdin.buffer.readline(HEADER_LIMIT + 1)
    if len(wire) > HEADER_LIMIT:
        raise ValueError('inventory header exceeds protocol limit')
    header = json.loads(wire)
    hashes = validate(header)
    locks = archive_root / '.native-locks'
    locks.mkdir(exist_ok=True)
    # Serialize native writes so independent senders cannot double-spend reserve.
    lock_path = locks / 'transport.lock'
    if locks.is_symlink() or lock_path.is_symlink():
        raise ValueError('archive lock must stay in native root')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return receive_locked(archive_root, header, hashes)


def receive_locked(root, header, hashes):
    started = time.monotonic()
    target = root / ('native-' + header['run'])
    reused = target.exists()
    if target.is_symlink():
        raise ValueError('published destination is a symlink')
    if not reused:
        size = sum(row['bytes'] for row in hashes.values())
        if shutil.disk_usage(root).free - size - 64 * 2**20 < RESERVE:
            raise RuntimeError('ARM projected free below 25 GiB')
        incoming = root / ('.incoming-native-' + header['run'] + '-' + uuid.uuid4().hex)
        incoming.mkdir(mode=0o750)
        emit({'ready': True, 'incoming': str(incoming)})
        decoder = subprocess.Popen(['zstd', '-qdc'], stdin=sys.stdin.buffer, stdout=subprocess.PIPE)
        try:
            extract(decoder.stdout, incoming, hashes)
            # Drain tar padding; insist on a complete, checksum-valid zstd frame.
            while decoder.stdout.read(2**20):
                pass
            if decoder.wait() != 0:
                raise RuntimeError('zstd stream failed')
        finally:
            decoder.stdout.close()
            if decoder.poll() is None:
                decoder.terminate()
                decoder.wait()
        if inventory(incoming) != hashes:
            raise RuntimeError('native ARM full-file SHA mismatch')
        for name in hashes:
            with (incoming / name).open('rb') as stream:
                os.fsync(stream.fileno())
        for directory, _, _ in os.walk(incoming, topdown=False):
            sync_directory(directory)
        if target.exists() or target.is_symlink():
            raise RuntimeError('published destination appeared; no overwrite')
        incoming.rename(target)
        sync_directory(root)
    elif inventory(target) != hashes:
        raise RuntimeError('existing archive mismatch; no overwrite')
    proof = {'verified': True, 'schema': SCHEMA, 'native_arm_path': str(target),
             'files': len(hashes), 'hash_matches': len(hashes), 'inventory_sha256': digest(hashes),
             'reused': reused, 'receiver_seconds': round(time.monotonic() - started, 3)}
    emit(proof)
    return proof


def transport(run, hashes, host, identity):
    if not host or not identity or host.startswith('-'):
        raise ValueError('native SSH host/identity must be explicitly configured')
    header = {'schema': SCHEMA, 'run': run.name, 'inventory': hashes}
    validate(header)
    wire = (json.dumps(header) + '\n').encode()
    if len(wire) > HEADER_LIMIT:
        raise ValueError('inventory header exceeds protocol limit')
    command = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=10',
               '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
               '-i', identity, '--', host, COMMAND]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as receiver:
        receiver.stdin.write(wire)
        receiver.stdin.flush()
        first = json.loads(receiver.stdout.readline())
        if first.get('ready') is True:
            with subprocess.Popen(['tar', '--hard-dereference', '-I', 'zstd -T1 -3', '-cf', '-',
                                   '-C', str(run), '.'], stdout=receiver.stdin) as packer:
                if packer.wait() != 0:
                    raise RuntimeError('tar/zstd producer failed; source and incoming retained')
            receiver.stdin.close()
            proof = json.loads(receiver.stdout.readline())
        else:
            proof = first
            receiver.stdin.close()
        if receiver.wait() != 0:
            raise RuntimeError('SSH receiver failed; source and incoming retained')
    if proof.get('verified') is not True or proof.get('inventory_sha256') != digest(hashes) or proof.get('files') != len(hashes):
        raise RuntimeError('native verification proof mismatch')
    return proof


def archive(root, run):
    from scripts.azure_shutdown import archived, run_processes, source_state, write_json
    started = time.monotonic()
    marker = root / 'lifecycle/archives' / (run.name + '.json')
    if marker.exists() and archived(root, run):
        existing = json.loads(marker.read_text())
        if Path(existing['path']).is_dir():
            return existing
    if run.is_symlink() or not (run / 'EXIT').is_file() or run_processes(run):
        raise RuntimeError('completed source without writers required')
    before = source_state(run)
    hashes = inventory(run)
    if before != source_state(run):
        raise RuntimeError('source changed while preparing transport')
    transfer_started = time.monotonic()
    proof = transport(run, hashes, os.environ.get('UGRP_ARCHIVE_NATIVE_HOST'),
                      os.environ.get('UGRP_ARCHIVE_NATIVE_IDENTITY'))
    transfer_seconds = time.monotonic() - transfer_started
    if inventory(run) != hashes or before != source_state(run) or run_processes(run):
        raise RuntimeError('source changed before marker publication')
    path = root / 'arm' / ('native-' + run.name)
    if not path.is_dir():
        raise RuntimeError('native target unavailable via lifecycle mount')
    value = {'verified': True, 'path': str(path), 'source': str(run), 'source_state': before,
             'inventory': hashes, 'native_verification': proof, 'preserved_local': True,
             'transport': {'mode': 'tar-zstd-ssh-v1', 'seconds': round(transfer_seconds, 3)},
             'elapsed_seconds': round(time.monotonic() - started, 3)}
    write_json(marker, value)
    if not archived(root, run):
        raise RuntimeError('lifecycle rejected native verification marker')
    (root / 'leases' / run.name).unlink(missing_ok=True)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['receive'])
    parser.add_argument('--archive-root', type=Path, required=True)
    args = parser.parse_args()
    receive(args.archive_root)


if __name__ == '__main__':
    main()
