"""Remote (bench VM) batch launcher: N identical v199/12th-A runs at once, 60 SIM s each.
No leases/archive helpers: originals stay on this temporary VM disk (deleted after bench)."""
import json, os, subprocess, sys, time, threading, resource, hashlib
from pathlib import Path
prefix, mode, n, sha = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
base = Path.home()/'ugrp-sim'; src = base/'src'/sha
receipt = base/'relays/vmbench/a.json'
batch = base/'runs'/f'{prefix}-{mode}-batch'; batch.mkdir(parents=True)
names = [f'{prefix}-solo'] if mode == 'solo' else [f'{prefix}-c{i}' for i in range(1, n+1)]
assert subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip() == sha
def cmd(root):
    return ['.venv-sim/bin/python', '-m', 'scripts.sim_cli', 'workflow', 'run', 'e2e-stall-budget-v199', '--timeout', '3600', '--',
        '--expected-source-sha', sha, '--output', str(root/'raw'), '--seed', '61001', '--driver-profile', 'study_gemma4_31b_v1',
        '--relay-receipt', str(receipt), '--e2e-live', '--event-driven-llm', '--compact-prompt', '--setdown-only-when-relook', 'on_v1',
        '--decider', 'off', '--exploration-progress', 'frontier_progress_v1', '--pose-fix', 'innovation', '--path-follow', 'rpp_v1',
        '--dev-light', '--stall-bundle', '--mapping-budget', 'case_cap_v1', '--stall-odometry', 'rgb_pulse_gate_v1',
        '--stall-recovery', 'backup_replan_v1', '--stall-noise', 'amcl_alpha_v1', '--wall-cap-s', '3500', '--measure-sim-s', '60', '--execute']
env = {**os.environ, 'MUJOCO_GL': 'osmesa', 'OMP_NUM_THREADS': '1', 'LP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
def stat():
    v = [int(x) for x in open('/proc/stat').readline().split()[1:]]
    return sum(v), v[3] + v[4]
lease = base/'leases'/batch.name; lease.parent.mkdir(exist_ok=True); lease.touch()
procs = {}; t0 = time.time()
(batch/'START.json').write_text(json.dumps(dict(prefix=prefix, mode=mode, names=names, sha=sha, start_unix=t0, loadavg=os.getloadavg(),
    mem_available_kib=int(next(l.split()[1] for l in open('/proc/meminfo') if l.startswith('MemAvailable:'))))) + '\n')
for name in names:
    root = base/'runs'/name; root.mkdir()
    meta = {'class': 'dev', 'pr': None, 'branch': 'claude/vm-bench', 'sha': sha, 'batch': f'{prefix}-{mode}', 'seed': 61001,
            'measurement_sim_s': 60, 'note': 'Azure VM size benchmark, temporary VM; originals deleted with VM', 'started_unix': time.time()}
    (root/'RUN_META.json').write_text(json.dumps(meta, indent=2) + '\n')
    (root/'COMMAND').write_text(json.dumps(cmd(root)) + '\n'); (root/'LOADAVG').write_text(str(os.getloadavg()) + '\n')
    log = (root/'log.txt').open('x')
    procs[name] = (subprocess.Popen(cmd(root), cwd=src, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT), time.time(), root)
samples = []; done = {}
prev = stat()
while len(done) < len(procs):
    time.sleep(5); lease.touch()
    cur = stat(); tot, idle = cur[0]-prev[0], cur[1]-prev[1]; prev = cur
    row = dict(unix=time.time(), loadavg=os.getloadavg(), cpu_busy_frac=(1-idle/tot) if tot else None, progress={})
    for name, (p, started, root) in procs.items():
        try:
            pr = json.loads((root/'raw/e2e-progress.json').read_text())
            row['progress'][name] = {k: pr[k] for k in ('t', 'now', 'sim_s', 'wall_s') if k in pr}
        except Exception:
            pass
        if name not in done and p.poll() is not None:
            done[name] = dict(rc=p.returncode, wall_s=time.time()-started)
            (root/'EXIT').write_text(json.dumps(done[name]) + '\n')
    samples.append(row)
    with (batch/'samples.jsonl').open('a') as f: f.write(json.dumps(row) + '\n')
lease.unlink(missing_ok=True)
ru = resource.getrusage(resource.RUSAGE_CHILDREN)
(batch/'END.json').write_text(json.dumps(dict(end_unix=time.time(), wall_s=time.time()-t0, runs=done,
    children_cpu_s=ru.ru_utime+ru.ru_stime, children_maxrss_kib=ru.ru_maxrss)) + '\n')
