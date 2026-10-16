"""Finite Azure paired batch; no VM lifecycle calls, own lease and early checks."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

from scripts.run_s3_release_ack import ROOT, PLAN
from scripts.run_s3_integer_carry_cohort import inspect
from scripts.evaluate_s3_continuous_distance import evaluate

ADMISSION = threading.Lock()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def commands(plan, sha):
    return [(r, [sys.executable, '-m', 'scripts.run_s3_release_ack',
        '--expected-source-sha', sha, '--output', f'outputs/{r["name"]}/raw',
        '--distance', str(r['distance_m']), '--seed', str(r['seed']),
        '--release-ack', r['option'], '--execute']) for r in plan['runs']]


def execute(item, out, sha, deadline, limits):
    row, args = item
    target = out/row['name']
    target.mkdir()
    write(target/'RUN_META.json', dict(**{'class': 'dev'}, pr=416, sha=sha,
        branch='codex/s3-no-prior-smoke', batch=out.parent.name))
    (target/'SOURCE_SHA').write_text(sha+'\n')
    write(target/'COMMAND.json', args)
    (ROOT/'outputs'/row['name']).symlink_to(target.resolve(), target_is_directory=True)
    proc = None
    result = dict(row)
    try:
        with ADMISSION:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError('batch admission deadline')
                load = os.getloadavg()
                mem = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                    if x.startswith('MemAvailable:')))*1024
                free = shutil.disk_usage(out).free
                if free < 8*2**30:
                    raise OSError('disk floor admission HOST_ERROR')
                if load[0] < 12.8 and mem >= 6*2**30:
                    break
                time.sleep(5)
            write(target/'admission.json', dict(loadavg=load, mem_available_bytes=mem,
                free_disk_bytes=free, logical_cpus=os.cpu_count(), time_utc=time.time()))
            log = (target/'log.txt').open('w')
            proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, env=dict(os.environ, MUJOCO_GL='osmesa',
                    LP_NUM_THREADS='4', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                    MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1'))
            log.close()
            (target/'PID').write_text(str(proc.pid)+'\n')
            started = time.monotonic()
        while proc.poll() is None and time.monotonic()-started < 180:
            time.sleep(1)
        check = inspect(target, 'pair')
        check.update(host='ugrp-sim-azure', elapsed_wall_s=time.monotonic()-started)
        write(target/'initial-check.json', check)
        result['initial_check'] = check
        if not check['healthy'] and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(2)
        if proc.poll() is None:
            (target/'STOP_REQUEST').write_text('FINITE_BATCH_CAP\n')
            os.killpg(proc.pid, signal.SIGINT)
        try:
            code = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
        (target/'EXIT').write_text(str(code)+'\n')
        result.update(evaluate(target/'raw', limits), exit_code=code)
        result.pop('curve', None)
        result['release_ack'] = json.loads((target/'raw/release-ack.json').read_text())
    except Exception as exc:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        result.update(status='HOST_ERROR', failure=repr(exc), whole_episode_completed=False)
        (target/'EXIT').write_text(str(proc.returncode if proc is not None else 74)+'\n')
    write(target/'summary.json', result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    plan = json.loads((ROOT/PLAN).read_text())
    items = commands(plan, a.expected_source_sha)
    if not a.execute:
        print(json.dumps(items))
        return 0
    if (os.uname().nodename != 'ugrp-sim-azure' or ROOT.name != a.expected_source_sha
            or not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs')
            or os.getpriority(os.PRIO_PROCESS, 0) != 0):
        raise ValueError('Azure immutable source + persistent output + nice0 required')
    a.output.mkdir(parents=True)
    (ROOT/'outputs').mkdir(exist_ok=True)
    lease = Path.home()/'ugrp-sim/leases'/a.output.parent.name
    lease.touch()
    stopped = threading.Event()
    def heartbeat():
        while not stopped.wait(30):
            lease.touch()
    threading.Thread(target=heartbeat, daemon=True).start()
    deadline = time.monotonic()+5400
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(execute, item, a.output, a.expected_source_sha,
                deadline, plan['eval_only_limits']) for item in items]
            runs = [future.result() for future in concurrent.futures.as_completed(futures)]
        counts = {option: dict(n=sum(r['option'] == option for r in runs),
            completed=sum(r['option'] == option and r.get('whole_episode_completed', False) for r in runs))
            for option in ('off', 'issued_open_v1')}
        write(a.output.parent/'summary.json', dict(schema='ugrp.s3_release_ack.summary.v1',
            source_sha=a.expected_source_sha, runs=sorted(runs, key=lambda r: r['name']), counts=counts))
    finally:
        stopped.set()
        lease.touch()  # Retain until verified retrieval/archive; caller releases it.
    return int(any(r['status'] == 'HOST_ERROR' for r in runs))


if __name__ == '__main__':
    raise SystemExit(main())
