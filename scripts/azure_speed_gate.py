"""Azure-only finite speed admission; probes never count as cohort evidence.

Uses monotonic elapsed time and statistics.median (Python standard library).
The existing workflow command and its source/profile flags are reused verbatim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import socket
import statistics
import subprocess
import sys
import time

PROBE_SIM_S = 30.
WARNING_SECONDS = 600.


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError('positive finite number required')
    return result


def override_reason(value):
    if not value.strip():
        raise argparse.ArgumentTypeError('--speed-gate-override requires a nonempty reason')
    return value.strip()


def add_arguments(parser):
    parser.add_argument('--speed-gate-limit', type=positive, default=4.)
    parser.add_argument('--speed-gate-override', type=override_reason)


def require_azure(root):
    if platform.system() != 'Linux' or not socket.gethostname().split('.')[0].startswith('ugrp-sim-azure'):
        raise ValueError('SPEED_GATE_AZURE_ONLY')
    if not Path(root).resolve().is_relative_to((Path.home() / 'ugrp-sim/runs').resolve()):
        raise ValueError('SPEED_GATE_PERSISTENT_RUN_REQUIRED')


def replace_option(command, flag, value):
    command = list(command)
    if flag in command:
        index = command.index(flag)
        command[index + 1] = str(value)
    else:
        command.extend((flag, str(value)))
    return command


def probe_command(command, target):
    command = replace_option(command, '--output', Path(target) / 'raw')
    command = replace_option(command, '--measure-sim-s', PROBE_SIM_S)
    # Preflight must not add the per-frame diagnostic hash to the planned workload.
    command = replace_option(command, '--rbpf-audit-hash', 'none')
    return command


def verdict(samples, expected, limit, override=None):
    positive(limit)
    if override is not None:
        override = override_reason(override)
    ratios = []
    failures = []
    for index, row in enumerate(samples):
        try:
            sim, wall = float(row['sim_s']), float(row['wall_s'])
            valid = (math.isfinite(sim) and sim >= PROBE_SIM_S - 1e-6
                     and math.isfinite(wall) and wall > 0
                     and row.get('expected_stop') is True and row.get('finalization_errors') == []
                     and row.get('exit') in (0, 1))
        except (KeyError, ValueError, TypeError):
            valid = False
        if valid:
            ratios.append(wall / sim)
        else:
            failures.append(index)
    median = statistics.median(ratios) if ratios else None
    passed = expected > 0 and len(samples) == expected and len(ratios) == expected and median <= limit
    return dict(status='SPEED_GATE_PASS' if passed else 'SPEED_GATE_OVERRIDE' if override else 'SPEED_GATE_FAIL',
                admitted=passed or bool(override), measured_pass=passed, override_reason=override,
                limit_wall_per_sim=limit, probe_sim_s=PROBE_SIM_S, planned_concurrency=expected,
                completed=len(ratios), median_wall_per_sim=median, invalid_samples=failures, samples=samples)


class SpeedWarning:
    """Require continuous slow 30-second intervals, including stalled progress."""
    def __init__(self, limit, interval_s=30., duration_s=WARNING_SECONDS):
        self.limit = positive(limit) * 1.5
        self.interval_s, self.duration_s = interval_s, duration_s
        self.previous = None
        self.slow_since = None

    def observe(self, now, sim_s):
        if not math.isfinite(sim_s) or sim_s < 0:
            sim_s = self.previous[1] if self.previous else 0.
        if self.previous is None:
            self.previous = now, sim_s
            return None
        wall = now - self.previous[0]
        if wall < self.interval_s:
            return None
        sim_s = max(sim_s, self.previous[1])
        delta = sim_s - self.previous[1]
        ratio = wall / delta if delta > 0 else math.inf
        previous_time = self.previous[0]
        self.previous = now, sim_s
        if ratio > self.limit:
            if self.slow_since is None:
                self.slow_since = previous_time
            if now - self.slow_since >= self.duration_s:
                return dict(status='SPEED_GATE_WARNING', limit_wall_per_sim=self.limit,
                            wall_per_sim=ratio if math.isfinite(ratio) else None, stalled=delta <= 0,
                            continuous_slow_s=now - self.slow_since, sim_s=sim_s,
                            recorded_unix=time.time())
        else:
            self.slow_since = None
        return None


def progress_sim(target):
    try:
        return float(json.loads((Path(target) / 'raw/e2e-progress.json').read_text())['sim_s'])
    except (OSError, ValueError, TypeError, KeyError):
        return 0.


def kill_group(process, signum=signal.SIGINT):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass


def preflight(specs, root, limit=4., override=None, *, timeout_s=None):
    root = Path(root)
    require_azure(root)
    if not specs or len({s['name'] for s in specs}) != len(specs):
        raise ValueError('SPEED_GATE_DISTINCT_PLAN_REQUIRED')
    positive(limit)
    if override is not None:
        override = override_reason(override)
    if any((Path(spec['target']) / 'raw').exists() for spec in specs):
        raise ValueError('SPEED_GATE_FRESH_COHORT_REQUIRED')
    root.mkdir(parents=True, exist_ok=False)
    parent = json.loads((Path(specs[0]['target']) / 'RUN_META.json').read_text())
    write(root / 'RUN_META.json', {**parent, 'class': 'dev', 'batch': root.name,
                                 'purpose': 'speed_gate_preflight', 'research_result': False})
    if override is not None:
        record = verdict([], len(specs), limit, override)
        write(root / 'SPEED_GATE_OVERRIDE.json', record)
        finish_record(root, record, specs)
        return record
    # A failed 30-second probe is bounded even when initialization never progresses.
    timeout_s = timeout_s or max(300., PROBE_SIM_S * limit * 3.)
    jobs, samples, failure = [], [], None
    previous_handlers = {}
    def stop(signum, frame):
        raise KeyboardInterrupt('SPEED_GATE_INTERRUPTED')
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.signal(sig, stop)
    try:
        # Prepare all directories before launching any child: planned concurrency, not sequential timings.
        prepared = []
        for spec in specs:
            target = root / ('speed-gate-' + spec['name'])
            target.mkdir()
            metadata = json.loads((Path(spec['target']) / 'RUN_META.json').read_text())
            write(target / 'RUN_META.json', {**metadata, 'class': 'dev', 'batch': root.name,
                                           'run': target.name, 'research_result': False})
            command = probe_command(spec['command'], target)
            prepared.append((target, command, spec.get('env')))
        for target, command, env in prepared:
            log = (target / 'log.txt').open('x')
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
            jobs.append((target, process, log, time.monotonic()))
        while any(proc.poll() is None for _, proc, _, _ in jobs):
            if any(time.monotonic() - started > timeout_s and proc.poll() is None
                   for _, proc, _, started in jobs):
                failure = 'PROBE_WALL_TIMEOUT'
                break
            time.sleep(.5)
    except (Exception, KeyboardInterrupt) as exc:
        failure = type(exc).__name__ + ':' + str(exc)
    finally:
        for _, proc, _, _ in jobs:
            kill_group(proc)
        for target, proc, log, _ in jobs:
            try:
                code = proc.wait(timeout=45)
            except subprocess.TimeoutExpired:
                kill_group(proc, signal.SIGKILL)
                code = proc.wait()
            log.close()
            (target / 'EXIT').write_text(str(code) + '\n')
            try:
                sample = json.loads((target / 'measurement.json').read_text())
                result = json.loads((target / 'raw/result.json').read_text())
                sample['finalization_errors'] = result.get('finalization_errors')
                sample['expected_stop'] = (sample.get('expected_stop') is True
                                           and result.get('failure') == 'MEASUREMENT_SIM_LIMIT')
            except (OSError, ValueError):
                sample = dict(error='MISSING_MEASUREMENT_OR_RESULT')
            samples.append({**sample, 'name': target.name, 'exit': code, 'raw': str(target / 'raw')})
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    record = verdict(samples, len(specs), limit)
    if failure:
        record.update(status='SPEED_GATE_FAIL', admitted=False, measured_pass=False, reason=failure)
    finish_record(root, record, specs)
    return record


def finish_record(root, record, specs):
    write(root / 'summary.json', record)
    if not record['admitted']:
        write(root / 'SPEED_GATE_FAIL.json', record)
        for spec in specs:
            target = Path(spec['target'])
            write(target / 'SPEED_GATE_FAIL.json', dict(status='COHORT_NOT_STARTED', gate_root=str(root)))
            (target / 'EXIT').write_text('75\n')
    # Make the parent preflight tree eligible for the normal immutable archive.
    with (root / 'SHA256SUMS').open('w') as stream:
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.name not in ('SHA256SUMS', 'EXIT'):
                with path.open('rb') as data:
                    digest = hashlib.file_digest(data, 'sha256').hexdigest()
                stream.write(f'{digest}  {path.relative_to(root).as_posix()}\n')
    (root / 'EXIT').write_text(('0' if record['admitted'] else '1') + '\n')


def watch(target, command, limit):
    require_azure(target)
    warning = SpeedWarning(limit)
    child = subprocess.Popen(command, start_new_session=True)
    previous = {}
    def stop(signum, frame):
        kill_group(child, signum)
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, stop)
    try:
        while child.poll() is None:
            row = warning.observe(time.monotonic(), progress_sim(target))
            if row:
                write(Path(target) / 'SPEED_GATE_WARNING.json', row)
            time.sleep(2)
        return child.returncode
    finally:
        kill_group(child)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    plan = commands.add_parser('add')
    plan.add_argument('--plan', type=Path, required=True)
    plan.add_argument('--name', required=True)
    plan.add_argument('--target', type=Path, required=True)
    plan.add_argument('command', nargs=argparse.REMAINDER)
    check = commands.add_parser('preflight')
    check.add_argument('--plan', type=Path, required=True)
    check.add_argument('--root', type=Path, required=True)
    add_arguments(check)
    monitor = commands.add_parser('watch')
    monitor.add_argument('--run', type=Path, required=True)
    monitor.add_argument('--speed-gate-limit', type=positive, default=4.)
    monitor.add_argument('command', nargs=argparse.REMAINDER)
    start = commands.add_parser('start')
    start.add_argument('--plan', type=Path, required=True)
    start.add_argument('--gate-root', type=Path, required=True)
    add_arguments(start)
    a = parser.parse_args(argv)
    if a.action == 'add':
        specs = json.loads(a.plan.read_text()) if a.plan.exists() else []
        command = a.command[1:] if a.command[:1] == ['--'] else a.command
        if not command or a.name in {s['name'] for s in specs}:
            parser.error('unique name and command required')
        write(a.plan, [*specs, dict(name=a.name, target=str(a.target), command=command)])
        return 0
    if a.action == 'watch':
        return watch(a.run, a.command[1:] if a.command[:1] == ['--'] else a.command, a.speed_gate_limit)
    specs = json.loads(a.plan.read_text())
    root = a.root if a.action == 'preflight' else a.gate_root
    record = preflight(specs, root, a.speed_gate_limit, a.speed_gate_override)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if not record['admitted']:
        return 1
    if a.action == 'start':
        # Launch only after the entire preflight has passed; preserve the standard supervisor.
        for spec in specs:
            target = Path(spec['target'])
            command = [sys.executable, '-m', 'scripts.azure_speed_gate', 'watch', '--run', str(target),
                       '--speed-gate-limit', str(a.speed_gate_limit), '--', *spec['command']]
            supervisor = [sys.executable, '/usr/local/lib/ugrp-storage/scripts/remote_run_finish.py',
                          '--source', str(Path.cwd()), '--run', str(target), '--', *command]
            write(target / 'speed-gate-admission.json', {k:v for k,v in record.items() if k != 'samples'})
            with (target / 'launch.log').open('x') as log:
                proc = subprocess.Popen(supervisor, stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True)
            write(target / 'speed-gate-launch.json', dict(pid=proc.pid, gate_root=str(root)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
