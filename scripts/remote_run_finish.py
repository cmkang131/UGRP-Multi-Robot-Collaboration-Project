"""Preserve this command's standard workflow records beside its raw output."""
import argparse
from pathlib import Path
import re
import shutil
import hashlib
import json
import os
import signal
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def execute(source, run, command):
    """Signal-aware supervisor: child flushes, then workflow records and EXIT."""
    from scripts.azure_shutdown import admission_closed, boot_id, process_start, write_json
    if admission_closed(run.parent.parent):
        write_json(run / 'HOST_ERROR.json', {'reason': 'cost_stop_admission_closed'})
        (run / 'EXIT').write_text('75\n')
        return 75
    write_json(run / 'PROCESS.json', {'pid': os.getpid(), 'start': process_start(os.getpid()), 'boot_id': boot_id()})
    child = None
    stopped = False

    def interrupt(signum, frame):
        nonlocal stopped
        stopped = True
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGINT)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)

    def reset_signals():
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

    with (run / 'log.txt').open('w') as log:
        child = subprocess.Popen(['/usr/bin/time', '-f', 'wall=%e cpu=%U+%S', *command],
                                 cwd=source, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, preexec_fn=reset_signals)
        if stopped:
            os.killpg(child.pid, signal.SIGINT)
        result = child.wait()
        log.flush()
        os.fsync(log.fileno())
    try:
        copied = collect(source, run)
        write_json(run / 'record-copy.json', {'copied': copied})
    except Exception as exc:
        write_json(run / 'record-copy.json', {'error': type(exc).__name__})
        (run / 'COMMAND_EXIT').write_text(str(result))
        result = 70
    if stopped:
        write_json(run / 'HOST_ERROR.json', {'reason': 'cost_stop_signal', 'command_exit': result})
    hashes = {}
    for path in sorted(run.rglob('*')):
        if path.is_file() and not path.is_symlink() and path.name not in ('EXIT', 'SHA256SUMS'):
            with path.open('rb') as stream:
                hashes[path.relative_to(run).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    with (run / 'SHA256SUMS').open('w') as stream:
        stream.writelines(f'{digest}  {name}\n' for name, digest in hashes.items())
        stream.flush()
        os.fsync(stream.fileno())
    with (run / 'EXIT').open('w') as stream:
        stream.write(str(result) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return result


def collect(source: Path, run: Path):
    allowed = (source / 'outputs/simulation-runs').resolve()
    records = set(re.findall(r'^Simulation record: (.+/manifest\.json)$',
                             (run / 'log.txt').read_text(), re.MULTILINE))
    copied = []
    for name in sorted(records):
        manifest = Path(name).resolve()
        if not manifest.is_relative_to(allowed) or manifest.name != 'manifest.json':
            raise ValueError('Workflow record outside the committed source record directory')
        target = run / 'management' / manifest.parent.name
        if target.exists():
            raise ValueError('Refuse to overwrite existing management evidence')
        shutil.copytree(manifest.parent, target, symlinks=True)
        copied.append(manifest.parent.name)
    return copied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command:
        command = args.command[1:] if args.command[0] == '--' else args.command
        execute(args.source, args.run, command)
    else:
        print('Preserved management records:', ','.join(collect(args.source, args.run)))


if __name__ == '__main__':
    main()
