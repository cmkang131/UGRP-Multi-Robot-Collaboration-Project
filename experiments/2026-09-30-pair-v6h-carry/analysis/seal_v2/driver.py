"""Blinded b-v6h1 confirmatory driver (72 cases). Records raw only.

This driver NEVER reads or prints case outcomes: it only looks at whether a worker produced result.json
(finished) or not (HOST_ERROR / crash), plus wall-clock. Outcome fields stay inside the raw files.
Cases are executed with the same worker entry point the stage-probe driver uses
(python -m scripts.run_pair_stage_probes --worker-case ... --worker-out ...), 4 workers, OMP=1.
HOST_ERROR rule (PREREG_DRAFT sec.8): rerun once, same case (placement/seed), original record preserved.
"""
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

ROOT = Path('/Users/changmin/projects/ugrp-wt/v6h1-confirm')
sys.path.insert(0, str(ROOT))
from scripts import agent_lock  # noqa: E402
from scripts.run_pair_stage_probes import safe_name, write_json  # noqa: E402

OUT = Path(__file__).resolve().parent
PLAN = json.loads((OUT / 'plan.json').read_text())
BRANCH = 'claude/v6h1-confirm-run'
PURPOSE = 'v6h1 blinded confirmatory 72'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
STOP = threading.Event()
ACTIVE, ACTIVE_LOCK = set(), threading.Lock()
STATUS_LOCK = threading.Lock()


def git(*a):
    return subprocess.check_output(['git', *a], cwd=ROOT, text=True)


def battery():
    txt = subprocess.check_output(['pmset', '-g', 'batt'], text=True)
    rec = {'unix': time.time(), 'output': txt, 'ac_power': "'AC Power'" in txt}
    with (OUT / 'power_checks.jsonl').open('a') as f:
        f.write(json.dumps(rec) + '\n')
    if not rec['ac_power']:
        raise RuntimeError('BATTERY_POWER: stop requested')


def check_env():
    if git('rev-parse', 'HEAD').strip() != PLAN['source_sha']:
        raise RuntimeError('SOURCE_CHANGED')
    if git('status', '--porcelain').strip():
        raise RuntimeError('DIRTY_WORKTREE')
    if shutil.disk_usage(OUT).free < 10 * 2 ** 30:
        raise RuntimeError('LOW_DISK')
    battery()


def terminate(p):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            pass
        if sig == signal.SIGTERM:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
    p.wait()


def stop_children():
    STOP.set()
    with ACTIVE_LOCK:
        procs = list(ACTIVE)
    for p in procs:
        terminate(p)


def run_owned_worker(case, dest):
    """Returns (row_or_None, status_record). status uses ONLY exit code / file presence."""
    if STOP.is_set():
        raise RuntimeError('STOP_REQUESTED')
    dest.parent.mkdir(parents=True, exist_ok=True)
    casefile = dest.parent / (dest.name + '.case.json')
    write_json(casefile, case)
    env = {**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
    argv = [sys.executable, '-m', 'scripts.run_pair_stage_probes', '--worker-case', str(casefile), '--worker-out', str(dest)]
    t0, w0 = time.time(), time.monotonic()
    logp = dest.parent / (dest.name + '.log')
    with logp.open('w') as f:
        with ACTIVE_LOCK:
            if STOP.is_set():
                raise RuntimeError('STOP_REQUESTED')
            p = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
            ACTIVE.add(p)
        try:
            try:
                code = p.wait(timeout=PLAN['case_timeout_wall_s'])
            except subprocess.TimeoutExpired:
                terminate(p)
                code = 'WALL_TIMEOUT'
        finally:
            if p.poll() is None:
                terminate(p)
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            with ACTIVE_LOCK:
                ACTIVE.discard(p)
    rp = dest / 'result.json'
    finished = (code == 0) and rp.exists()
    status = {'case_id': case['case_id'], 'seed': case['seed'], 'cell': case['cell'], 'case_dir': str(dest),
              'start_unix': t0, 'wall_s': round(time.monotonic() - w0, 2), 'worker_exit': code}
    if finished:
        row = json.loads(rp.read_text())['row']
        status['status'] = 'finished'
        return row, status
    log_txt = logp.read_text(errors='replace') if logp.exists() else ''
    enospc = 'No space left on device' in log_txt or 'ENOSPC' in log_txt
    status['status'] = 'HOST_ERROR' if (code == 'WALL_TIMEOUT' or enospc) else 'crash'
    status['detail'] = 'ENOSPC' if enospc else (code if code == 'WALL_TIMEOUT' else f'worker_exit_{code}')
    row = {'case_id': case['case_id'], 'stage': case['stage'], 'source': case['source'], 'cell': case['cell'], 'seed': case['seed'],
           'category': f"HOST_ERROR:{status['detail']}", 'wall_s': status['wall_s'], 'stage_sim_s': None}
    return row, status


def append(path, obj):
    with STATUS_LOCK, path.open('a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def run_batch(cases, root, jsonl, attempt):
    pool = cf.ThreadPoolExecutor(max_workers=PLAN['workers'])
    pending = {pool.submit(run_owned_worker, c, root / safe_name(c['case_id'])): c for c in cases}
    results = {}
    done_n = 0
    try:
        while pending:
            check_env()
            done, _ = cf.wait(pending, timeout=15, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                c = pending.pop(fut)
                row, status = fut.result()
                status['attempt'] = attempt
                append(jsonl, row)
                append(OUT / 'case_status.jsonl', status)
                results[c['case_id']] = status['status']
                done_n += 1
                print(f'[attempt {attempt}] {done_n} done, status={status["status"]}', flush=True)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return results


def interrupted(sig, frame):
    raise KeyboardInterrupt(f'signal {sig}')


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
held, manifest, started = None, {}, time.monotonic()
try:
    check_env()
    print('WAITING_FOR_LOCK', flush=True)
    last_check = time.monotonic()
    while True:
        try:
            held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='claude', branch=BRANCH, purpose=PURPOSE,
                                      pid=os.getpid(), expected_minutes=150)
            break
        except RuntimeError:
            # Other agents re-acquire within ~1 s of a release; poll fast, run the env check every ~20 s.
            time.sleep(0.05)
            if time.monotonic() - last_check > 20:
                check_env()
                last_check = time.monotonic()
    started = time.monotonic()
    from sim.workflow_manager import environment_identity, source_fingerprint
    manifest = {'schema': 'v6h1-confirm-blinded.run.v1', 'state': 'running', 'source_sha': PLAN['source_sha'],
                'source_status_porcelain_at_start': git('status', '--porcelain'),
                'source_fingerprint': source_fingerprint(ROOT), 'environment': environment_identity(), 'lock': held,
                'driver_pid': os.getpid(), 'driver_sha256': sha(OUT / 'driver.py'), 'plan_sha256': sha(OUT / 'plan.json'),
                'loadavg_at_start': list(os.getloadavg()), 'workers': PLAN['workers'], 'omp_threads': 1, 'model_calls': 0,
                'weld': False, 'clock': 'SIM', 'render_profile': PLAN['render_profile'], 'start_unix': time.time(),
                'free_disk_gib_at_start': shutil.disk_usage(OUT).free / 2 ** 30}
    write_json(OUT / 'manifest.json', manifest)
    print('LOCK_ACQUIRED', os.getpid(), flush=True)
    first = run_batch(PLAN['cases'], OUT / 'cases', OUT / 'cases.jsonl', 1)
    bad = [c for c in PLAN['cases'] if first.get(c['case_id']) != 'finished']
    manifest['first_pass_not_finished'] = [c['case_id'] for c in bad]
    if bad and not STOP.is_set():
        print(f'RERUN_ONCE {len(bad)} HOST_ERROR/crash cases', flush=True)
        run_batch(bad, OUT / 'cases_rerun1', OUT / 'cases_rerun1.jsonl', 2)
    manifest['state'] = 'completed'
except BaseException as e:  # noqa: BLE001
    manifest.update(state='stopped', error=f'{type(e).__name__}: {e}')
    print(manifest['error'], flush=True)
    stop_children()
finally:
    manifest.update(end_unix=time.time(), wall_s=time.monotonic() - started, loadavg_at_end=list(os.getloadavg()))
    try:
        manifest['source_changed'] = git('rev-parse', 'HEAD').strip() != PLAN['source_sha'] or bool(git('status', '--porcelain').strip())
    except Exception as e:  # noqa: BLE001
        manifest['source_check_error'] = str(e)
    if held:
        current = agent_lock.status(agent_lock.DEFAULT_ROOT)
        if current and current['pid'] == os.getpid():
            agent_lock.release(agent_lock.DEFAULT_ROOT, owner='claude')
            manifest['lock_released'] = True
    manifest['free_disk_gib_at_end'] = shutil.disk_usage(OUT).free / 2 ** 30
    if manifest:
        write_json(OUT / 'manifest.json', manifest)
    print('DRIVER_FINISHED', manifest.get('state'), 'lock_released', manifest.get('lock_released'), flush=True)
