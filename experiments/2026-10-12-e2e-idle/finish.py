#!/usr/bin/env python3
"""E2E17 post-EXIT lite export, standard zstd, and verified native ARM archive.

Deploy beside export_lite.py. No source-checkout imports or raw deletion.
RUN_META PR453 is authoritative; legacy result.json PR metadata is preserved.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

BAD_SHA = 'c0b87f0028681ebca96581833b2dd0da0b152d8b'
TOOLS = Path('/usr/local/lib/ugrp-storage/scripts')


def write(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def admit(base, name):
    if Path(name).name != name:
        raise ValueError('RUN_NAME_REQUIRED')
    run = base / 'runs' / name
    if run.is_symlink() or run.resolve() != run or not (run / 'EXIT').is_file():
        raise ValueError('COMPLETED_PERSISTENT_RUN_REQUIRED')
    process_file = run / 'PROCESS.json'
    if process_file.exists() and Path('/proc').is_dir():
        tracked = json.loads(process_file.read_text())
        try:
            ticks = (Path('/proc') / str(tracked['pid']) / 'stat').read_text().rsplit(')', 1)[1].split()[19]
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            if ticks == str(tracked.get('start')) and boot == tracked.get('boot_id'):
                raise ValueError('SUPERVISOR_STILL_FLUSHING')
        except (FileNotFoundError, ProcessLookupError):
            pass
    meta = json.loads((run / 'RUN_META.json').read_text())
    if meta.get('pr') != 453 or meta.get('class') != 'dev':
        raise ValueError('DEV_PR453_REQUIRED')
    normal = re.fullmatch(r'e2e-idle-[ab]-s6100[1-9](?:-r[2-9][0-9]*)?', name)
    malformed = re.fullmatch(r'e2e-idle-(?:1000|105|24|27|30|4)-s6100[1-9]', name)
    if not normal and not (malformed and meta.get('sha') == BAD_SHA):
        raise ValueError('E2E17_SCOPE_REQUIRED')
    source = (run / 'SOURCE_SHA').read_text().strip()
    if not re.fullmatch('[0-9a-f]{40}', source) or source != meta.get('sha'):
        raise ValueError('SOURCE_SHA_MISMATCH')
    return run


def state(run):
    return {p.relative_to(run).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns]
            for p in run.rglob('*') if p.is_file()}


def verified(base, run):
    marker = base / 'lifecycle/archives' / (run.name + '.json')
    if not marker.is_file():
        return None
    data = json.loads(marker.read_text())
    proof = data.get('native_verification', {})
    inventory = data.get('inventory', {})
    expected_path = base / 'arm' / ('native-' + run.name)
    digest = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    if (data.get('verified') is not True or proof.get('verified') is not True or
            proof.get('schema') != 'ugrp.archive-native.v1' or
            data.get('source') != str(run) or data.get('path') != str(expected_path) or
            not expected_path.is_dir() or not inventory or
            proof.get('files') != len(inventory) or proof.get('hash_matches') != len(inventory) or
            proof.get('inventory_sha256') != digest or data.get('source_state') != state(run)):
        raise ValueError('NATIVE_ARCHIVE_PROOF_INVALID')
    # Native receiver independently hashed every file before publishing this receipt.
    return {'name': run.name, 'verified': True, 'path': proof['native_arm_path'],
            'files': len(inventory), 'hash_matches': proof['hash_matches'],
            'inventory_sha256': digest, 'bytes': sum(v['bytes'] for v in inventory.values()),
            'marker_sha256': hashlib.sha256(marker.read_bytes()).hexdigest()}


def lock_until(path, deadline):
    stream = path.open('a')
    while True:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return stream
        except BlockingIOError:
            if time.monotonic() >= deadline:
                stream.close()
                raise TimeoutError('FINISH_LOCK_DEADLINE')
            time.sleep(2)


def command(argv, deadline, attempts=1):
    for attempt in range(attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('FINISH_DEADLINE')
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            stdout, _ = process.communicate(timeout=min(300, remaining))
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, 15)
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, 9)
                process.communicate()
        else:
            if process.returncode == 0:
                return stdout
        if attempt + 1 < attempts:
            time.sleep(min(10, max(0, deadline - time.monotonic())))
    raise RuntimeError('POSTRUN_STEP_FAILED:' + Path(argv[1]).name)


def finish(base, name, timeout_s):
    run = admit(base, name)
    deadline = time.monotonic() + timeout_s
    records = base / 'e2e-idle-finished'
    records.mkdir(exist_ok=True)
    locks = base / 'lifecycle/e2e-idle-finish-locks'
    locks.mkdir(parents=True, exist_ok=True)
    with lock_until(locks / (name + '.lock'), deadline):
        proof = verified(base, run)
        if proof:
            (base / 'leases' / name).unlink(missing_ok=True)
            return proof
        lease = base / 'leases' / name
        lease.parent.mkdir(exist_ok=True)
        lease.touch()
        stop = threading.Event()
        def heartbeat():
            while not stop.wait(20):
                lease.touch()
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            exporter = Path(__file__).resolve().with_name('export_lite.py')
            command([sys.executable, str(exporter), str(run)], deadline)
            compressor = [sys.executable, str(TOOLS / 'compress_json_traces.py'), str(run), '--execute']
            command(compressor, deadline, attempts=6)
            # Refresh actual .zst paths/hashes, then rebuild standard source hash inventory.
            command([sys.executable, str(exporter), str(run)], deadline)
            command(compressor, deadline, attempts=6)
            with lock_until(base / '.e2e-idle-archive.lock', deadline):
                command([sys.executable, str(TOOLS / 'azure_shutdown.py'), 'archive-one',
                         '--root', str(base), '--run', name], deadline, attempts=60)
            proof = verified(base, run)
            if not proof:
                raise ValueError('ARCHIVE_RECEIPT_MISSING')
            write(records / (name + '.json'), {**proof, 'finished_unix': time.time(),
                                             'authoritative_pr': 453, 'raw_preserved': True})
            stop.set()
            thread.join()
            lease.unlink(missing_ok=True)
            return proof
        except BaseException as exc:
            # No raw mutation after native publication; failure evidence stays outside run.
            stop.set()
            thread.join()
            lease.touch()
            write(records / (name + '-failed.json'), {'name': name, 'verified': False,
                  'error_type': type(exc).__name__, 'raw_preserved': True, 'lease_preserved': True,
                  'failed_unix': time.time()})
            raise
        finally:
            stop.set()
            thread.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    parser.add_argument('--base', type=Path, default=Path.home() / 'ugrp-sim')
    parser.add_argument('--timeout-s', type=int, default=1800)
    args = parser.parse_args()
    try:
        if not 1 <= args.timeout_s <= 3600:
            raise ValueError('FINITE_TIMEOUT_REQUIRED')
        result = finish(args.base.expanduser().resolve(), args.name, args.timeout_s)
    except Exception as exc:
        print(json.dumps({'name': args.name, 'verified': False, 'error_type': type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result), flush=True)
