"""Finite host-only comparison; no teacher changes, training or model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def speed(source, out):
    # Same frozen source/plan/command and thread settings as the 2026-10-14
    # c1f02ac0 n4 benchmark. 30 SIM seconds and concurrency 16 are user requested.
    plan = source / 'experiments/2026-10-14-e2e18-grasp-rootcause/teacher-gate-plan.json'
    env = {**os.environ, 'MUJOCO_GL': 'osmesa', **{k: '1' for k in
           ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'LP_NUM_THREADS')}}
    jobs = []
    rows = []
    started = time.time()
    try:
        for index in range(16):
            target = out / f'episode-{index:03d}'
            target.mkdir()
            command = [str(source / '.venv-sim/bin/python'), '-m', 'scripts.sim_cli',
                       'workflow', 'run', 'grasp-act-teacher', '--', '--plan', str(plan),
                       '--episode', str(index), '--out', str(target / 'raw'),
                       '--cap-s', '30', '--teacher-profile', 'visible_only', '--probe']
            log = (target / 'log.txt').open('w')
            child = subprocess.Popen(command, cwd=source, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            write(target / 'PROCESS.json', {'pid': child.pid, 'command': command})
            jobs.append((index, target, child, log))
        for index, target, child, log in jobs:
            code = child.wait()
            log.close()
            result_path = target / 'raw/result.json'
            result = json.loads(result_path.read_text()) if result_path.exists() else {}
            row = {'index': index, 'exit': code, 'status': result.get('status', 'HOST_ERROR'),
                   'sim_s': result.get('sim_s'), 'wall_s': result.get('wall_s'),
                   'wall_per_sim': result.get('wall_per_sim'),
                   'cap_end': result.get('status') == 'complete' and code == 0,
                   'raw': str(target / 'raw'),
                   'result_sha256': hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path.exists() else None}
            rows.append(row)
            print(json.dumps(row), flush=True)
    finally:
        # Only children launched by this probe are ours to stop.
        import signal
        for _, _, child, log in jobs:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                child.wait()
            log.close()
    complete = [r for r in rows if r['exit'] == 0 and r['status'] == 'complete']
    samples = [r['wall_per_sim'] for r in complete if r['wall_per_sim'] is not None]
    # Existing GCP speed threshold, documented in AGENTS.md/docs/gcp_simulation.md;
    # 3.5 is warning-only, >6.0 or incomplete/HOST_ERROR blocks admission.
    summary = {'host': 'gcp2', 'project': 'ugrp-sim-b-1014', 'research_result': False,
               'source_sha': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
               'plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest(), 'concurrency': 16,
               'completed': len(complete), 'planned': 16, 'cap_end': sum(r['cap_end'] for r in rows),
               'wall_s_batch': time.time() - started, 'rows': rows,
               'median_wall_per_sim': statistics.median(samples) if samples else None,
               'max_wall_per_sim': max(samples) if samples else None,
               'loadavg_at_end': os.getloadavg()}
    summary['admitted'] = len(complete) == 16 and len(samples) == 16 and summary['median_wall_per_sim'] <= 6.0
    summary['warning'] = bool(samples and summary['median_wall_per_sim'] > 3.5)
    write(out / 'summary.json', summary)
    gates = [('frozen_plan', 16), ('launched', len(jobs)), ('complete_exit_0', len(complete)),
             ('reached_30_sim_s', sum(r.get('sim_s', 0) >= 30 for r in complete)),
             ('result_and_speed_recorded', len(samples))]
    prior = 16
    funnel = []
    for gate, passed in gates:
        funnel.append({'gate': gate, 'cumulative_pass': passed, 'rejected': prior - passed})
        prior = passed
    write(out / 'funnel.json', {'unit': 'host_probe_episode', 'gates': funnel,
          'not_a_teacher_success_gate': True, 'raw': str(out),
          'reproduce': f'python3 host_probe.py --source {source} --out NEW_OUTPUT',
          'rejections': [{'category': 'HOST_ERROR', 'blocking_object': 'not_applicable_host_setup',
                          'minimum_gap_m': None, 'reason': 'child_exit_or_missing_complete_result', 'index': r['index']}
                         for r in rows if r not in complete]})
    manifest = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.rglob('*')) if p.is_file()}
    write(out / 'SHA256.json', manifest)
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != 'Linux':
        raise RuntimeError('Run on the authorized GCP host only')
    source = args.source.resolve()
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no']):
        raise RuntimeError('Source must be committed and unchanged')
    args.out.mkdir(parents=True, exist_ok=False)
    write(args.out / 'admission.json', {'loadavg': os.getloadavg(), 'source': str(source),
                                      'platform': platform.platform(), 'python': platform.python_version()})
    speed(source, args.out.resolve())


if __name__ == '__main__':
    main()
