"""Bounded flush/archive for cost stops; originals are never removed here."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path('/home/ugrp/ugrp-sim')
GRACE_SECONDS = 600


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    with temp.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def admission_closed(root=ROOT):
    marker = root / 'lifecycle/STOPPING.json'
    return marker.exists() and json.loads(marker.read_text())['boot_id'] == boot_id()


def inventory(folder):
    result = {}
    for directory, dirs, names in os.walk(folder):
        dirs.sort()
        for name in sorted(names):
            path = Path(directory) / name
            key = path.relative_to(folder).as_posix()
            if path.is_symlink():
                result[key] = {'symlink': os.readlink(path)}
            elif path.is_file():
                before = path.stat()
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError('source changed while hashing')
                result[key] = {'bytes': after.st_size, 'sha256': digest}
        for name in dirs[:]:
            path = Path(directory) / name
            if path.is_symlink():
                result[path.relative_to(folder).as_posix()] = {'symlink': os.readlink(path)}
                dirs.remove(name)
    return result


def archived(root, run):
    if run.is_symlink():
        return run.exists()  # Existing full-checksum archive publisher.
    marker = root / 'lifecycle/archives' / (run.name + '.json')
    if not marker.exists():
        return False
    data = json.loads(marker.read_text())
    # Markers are written only after full verification; reject subsequent writes.
    return data.get('verified') is True and data['source_state'] == source_state(run)


def source_state(folder):
    # Fast local check for post-verification changes; hash inventories stay durable.
    return {p.relative_to(folder).as_posix(): [p.lstat().st_size, p.lstat().st_mtime_ns, p.lstat().st_ctime_ns]
            for p in folder.rglob('*') if p.is_file() or p.is_symlink()}


def run_dirs(root):
    runs = root / 'runs'
    return sorted(p for p in runs.iterdir() if p.is_symlink() or p.is_dir()) if runs.exists() else []


def blockers(root=ROOT):
    pending = [p.name for p in run_dirs(root) if not archived(root, p)]
    leases = root / 'leases'
    live = [p.name for p in leases.iterdir() if time.time() - p.stat().st_mtime < 120] if leases.exists() else []
    return {'unarchived': pending, 'leases': live, 'stopping': admission_closed(root)}


def process_start(pid):
    # comm can contain spaces: fields after its final ')' start at stat field 3.
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def run_processes(run):
    """Tracked supervisors plus old wrappers, restricted to this run's paths."""
    found = set()
    record = run / 'PROCESS.json'
    if record.exists():
        data = json.loads(record.read_text())
        try:
            if process_start(data['pid']) == data['start'] and data['boot_id'] == boot_id():
                found.add(data['pid'])
        except (OSError, ProcessLookupError):
            pass
    source = (run / 'SOURCE_SHA').read_text().strip() if (run / 'SOURCE_SHA').exists() else ''
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            argv = (entry / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            executable = argv[0].rsplit('/', 1)[-1]
            raw_path = any(arg == str(run) or arg.startswith(str(run) + '/') for arg in argv)
            output_path = any(arg == 'outputs/' + run.name or arg.startswith('outputs/' + run.name + '/') for arg in argv)
            own_source = source and os.readlink(entry / 'cwd') == str(run.parent.parent / 'src' / source)
            if executable.startswith(('python', 'bash', 'time')) and (
                    raw_path or (own_source and output_path)):
                found.add(int(entry.name))
            # Legacy commands need not mention their output name in argv.
            for fd in (entry / 'fd').iterdir():
                try:
                    flags = (entry / 'fdinfo' / fd.name).read_text().split('flags:', 1)[1].split()[0]
                    if (int(flags, 8) & os.O_ACCMODE) != os.O_RDONLY and os.readlink(fd).startswith(str(run) + '/') and executable.startswith(('python', 'bash', 'time')):
                        found.add(int(entry.name))
                        break
                except OSError:
                    pass
        except OSError:
            pass
    return found


def signal_runs(root):
    signalled = []
    for run in run_dirs(root):
        if run.is_symlink():
            continue
        for pid in run_processes(run):
            try:
                os.kill(pid, signal.SIGINT)
                signalled.append({'run': run.name, 'pid': pid})
            except ProcessLookupError:
                pass
    return signalled


class ArchiveBusy(RuntimeError):
    pass


def archive_copy_matches(argv, root, run):
    """Scheduled archiver's exact source and registered incoming destination."""
    if not argv or Path(argv[0]).name != 'rsync':return False
    args=[a.rstrip('/') for a in argv[1:] if a]
    destinations={str(root/'arm'/('.incoming-'+run.name)),
                  str(root/'arm'/('.incoming-shutdown-'+run.name))}
    return str(run) in args and bool(destinations.intersection(args))


def active_archive_processes(root, run):
    """Identify an existing archive worker, including workers started before locks.

    This is only admission coordination: the raw remains an ordinary stop
    blocker until its independent checksum marker is verified.
    """
    found=set()
    proc=Path('/proc')
    if not proc.exists():return found
    for p in proc.iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            argv=(p/'cmdline').read_bytes().decode().split('\0')
            if archive_copy_matches(argv,root,run):
                found.add(int(p.name));continue
            if str(Path(__file__).resolve()) not in argv or 'archive-one' not in argv:continue
            if argv[argv.index('--run')+1]!=run.name:continue
            selected=Path(argv[argv.index('--root')+1]) if '--root' in argv else ROOT
            if selected!=root:continue
            if Path(argv[0]).name.startswith('python'):found.add(int(p.name))
        except (OSError,ValueError,IndexError,UnicodeError):continue
    return found


def archive_one(root, run):
    locks=root/'lifecycle/archive-locks';locks.mkdir(parents=True,exist_ok=True)
    with (locks/(run.name+'.lock')).open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ArchiveBusy('archive worker already owns '+run.name) from None
        # A sibling may finish verification while this admission waits. Reuse
        # only its full-checksum marker with unchanged source and mounted target.
        marker=root/'lifecycle/archives'/(run.name+'.json')
        if marker.exists() and archived(root,run) and os.path.ismount(root/'arm'):
            if Path(json.loads(marker.read_text())['path']).is_dir():return
        return _archive_one(root,run)


def _archive_one(root, run):
    """Resumable separate destination; preserve both source and failed incoming."""
    archive = root / 'arm'
    if not os.path.ismount(archive):
        raise RuntimeError('ARM mount unavailable')
    if run_processes(run):
        raise RuntimeError('run still flushing')
    if not (run / 'EXIT').exists():
        # After reboot there is no writer: preserve partial run as HOST_ERROR.
        write_json(run / 'HOST_ERROR.json', {'reason': 'interrupted_before_exit', 'boot_id': boot_id()})
        (run / 'EXIT').write_text('74\n')
    if os.environ.get('UGRP_ARCHIVE_NATIVE', 'off') == 'on_v1':
        from scripts.azure_archive_native import archive
        return archive(root, run)
    left = inventory(run)
    # Flush the completed command's local files inside the bounded copy worker.
    for path in run.rglob('*'):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    size = sum(value.get('bytes', 0) for value in left.values())
    if shutil.disk_usage(archive).free - size < 25 * 2**30:
        raise RuntimeError('ARM reserve would fall below 25 GiB')
    target = archive / ('shutdown-' + run.name)
    incoming = archive / ('.incoming-shutdown-' + run.name)
    if not target.exists():
        incoming.mkdir(exist_ok=True)
        subprocess.run(['rsync', '-ac', '--', str(run) + '/', str(incoming) + '/'], check=True, capture_output=True)
        check = subprocess.run(['rsync', '-anc', '--out-format=%n', '--', str(run) + '/', str(incoming) + '/'],
                               check=True, capture_output=True, text=True)
        if check.stdout.strip() or left != inventory(incoming) or left != inventory(run) or run_processes(run):
            raise RuntimeError('archive checksum mismatch or source changed')
        incoming.rename(target)
    if left != inventory(target) or left != inventory(run):
        raise RuntimeError('existing archive mismatch; no overwrite')
    write_json(root / 'lifecycle/archives' / (run.name + '.json'),
               {'verified': True, 'path': str(target), 'inventory': left, 'source_state': source_state(run)})
    (root / 'leases' / run.name).unlink(missing_ok=True)


def bounded_archive(root, run, seconds):
    logs = root / 'lifecycle/archive-attempts'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / (run.name + '-' + uuid.uuid4().hex + '.log')).open('w') as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'archive-one',
                                    '--root', str(root), '--run', run.name],
                                   stdout=log, stderr=log, start_new_session=True)
        try:
            return process.wait(timeout=max(0.01, seconds)) == 0
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            log.write('ARCHIVE_TIMEOUT: originals and incoming copy retained\n')
            return False
        finally:
            log.flush()
            os.fsync(log.fileno())


ARCHIVE_LOCK = '/tmp/ugrp-auto-archive.lock'


def lifecycle(action, reason, root=ROOT, grace=GRACE_SECONDS):
    grace = min(max(grace, 0), GRACE_SECONDS)
    started = time.monotonic()
    deadline = started + grace
    state = root / 'lifecycle'
    state.mkdir(parents=True, exist_ok=True)
    # Same lock as scheduled archival; never race compression/source publication.
    with open(ARCHIVE_LOCK, 'a') as lock:
        if action == 'stop':
            write_json(state / 'STOPPING.json', {'boot_id': boot_id(), 'reason': reason})
        signalled = signal_runs(root) if action == 'stop' else []
        report = {'id': uuid.uuid4().hex, 'action': action, 'reason': reason,
                  'boot_id': boot_id(), 'status': 'running', 'signalled': signalled, 'archived': [], 'failed': []}
        record = state / 'events' / (report['id'] + '.json')
        write_json(record, report)
        # Give the command's finally blocks/record writer at most 60 seconds.
        flush_deadline = min(deadline, started + 60)
        while action == 'stop' and any(run_processes(p) for p in run_dirs(root) if not p.is_symlink()):
            if time.monotonic() >= flush_deadline:
                break
            time.sleep(min(1, max(0, flush_deadline - time.monotonic())))
        for run in run_dirs(root):
            if run.is_symlink():
                continue
            # Repeated azctl start is also batch admission on an already running
            # VM. Recovery preserves live, identity-checked sibling writers;
            # ordinary stop still sees them as blockers and cost stop signals.
            if action == 'recover' and run_processes(run):
                report.setdefault('active_preserved', []).append(run.name)
                write_json(record, report)
                continue
            deferred = False
            if action == 'recover' and active_archive_processes(root,run):
                report.setdefault('active_archive_preserved', []).append(run.name)
                deferred = True
            ok = archived(root, run)
            attempts = 0
            while not ok and not deferred and time.monotonic() < deadline:
                if action == 'recover':
                    # The scheduled archiver may publish or start copying after
                    # the first scan. Recheck instead of waiting on its mutex.
                    if archived(root,run):ok=True;break
                    if active_archive_processes(root,run):
                        report.setdefault('active_archive_preserved',[]).append(run.name)
                        deferred=True;break
                remaining = deadline - time.monotonic()
                locked = False
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except BlockingIOError:
                    pass
                ok = locked and bounded_archive(root, run, remaining)
                if locked:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                attempts += 1
                report['attempts'] = {**report.get('attempts', {}), run.name: attempts}
                write_json(record, report)
                if not ok:
                    time.sleep(min(10, max(0, deadline - time.monotonic())))
            if action == 'recover':
                # A deferred copy or successful worker exit is not verification.
                # Admission stays blocked until the unchanged-source marker exists.
                ok = archived(root, run)
            report['archived' if ok else 'failed'].append(run.name)
            if not ok:
                leases = root / 'leases'
                leases.mkdir(exist_ok=True)
                (leases / run.name).touch()  # Durable pending record; never drop failed lease.
            write_json(record, report)
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        report['status'] = 'complete'
        write_json(record, report)
        print(json.dumps(report), flush=True)
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['stop', 'recover', 'status', 'admit', 'daily', 'archive-one'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--reason', default='cost_cap')
    parser.add_argument('--grace-seconds', type=float, default=GRACE_SECONDS)
    parser.add_argument('--run')
    args = parser.parse_args()
    if args.action in ('status', 'daily'):
        state = blockers(args.root)
        print(json.dumps(state), flush=True)
        if any(state.values()):
            if args.action == 'daily':
                write_json(args.root / 'lifecycle/events' / (uuid.uuid4().hex + '.json'),
                           {'action': 'daily', 'result': 'skipped', 'blockers': state})
            return 75
        if args.action == 'daily':
            report = lifecycle('stop', 'daily_backup', args.root, args.grace_seconds)
            return 74 if report['failed'] else 0
    elif args.action == 'admit':
        return 75 if admission_closed(args.root) else 0
    elif args.action == 'archive-one':
        if not args.run or Path(args.run).name != args.run:
            raise ValueError('unsafe run name')
        archive_one(args.root, args.root / 'runs' / args.run)
    else:
        report = lifecycle(args.action, args.reason, args.root, args.grace_seconds)
        return 74 if report['failed'] else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
