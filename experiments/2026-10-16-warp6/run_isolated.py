"""Finite R3 reproduction, one CUDA process at a time, no MPS or cloud keys."""
import argparse
import datetime
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess

ROOT = Path('/home/ugrp/ugrp-sim')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def main():
    # nohup/non-interactive background shells may inherit SIGINT=SIG_IGN.
    # Restore normal Python interruption before spawning the owned child.
    signal.signal(signal.SIGINT,signal.default_int_handler)
    p = argparse.ArgumentParser()
    p.add_argument('--source-sha', required=True)
    p.add_argument('--round', required=True)
    p.add_argument('--job', choices=['beampair', 'release-s1', 'release-s3'], required=True)
    p.add_argument('--memcheck', action='store_true')
    p.add_argument('--debug', action='store_true')
    p.add_argument('--trace', action='store_true')
    p.add_argument('--verify', action='store_true')
    p.add_argument('--diagnostic-ticks',type=int)
    a = p.parse_args()
    src = ROOT / 'src' / a.source_sha
    jobs = {'beampair': ('beampair', '0,1,2,3', 60),
            'release-s1': ('release', '0,1,3,4,5,7', 180),
            'release-s3': ('release', '2,6', 180)}
    flow, indices, cap = jobs[a.job]
    out = ROOT / 'runs/warp6' / (a.round + '-' + a.job)
    if out.exists() or out.with_suffix('.receipt.json').exists():
        raise RuntimeError('immutable output already exists')
    cmd = [str(ROOT / 'ugrp/.venv-warp/bin/python'),
           str(src / 'scripts/run_warp_flow_teacher.py'), '--flow', flow,
           '--adapter-source', str(ROOT / 'src' / (
               '835ccef26aa84b08cc8f7e256fd0f43aa1583ef9' if flow == 'beampair'
               else '8e81b7d96c0c73171635348c90631462adfe1eb0')),
           '--cases', str(ROOT / 'ops-reviews/warp4' / (flow + '-short-cases.json')),
           '--indices', indices, '--cap-s', str(cap), '--vm-hourly-usd', '1.096',
           '--gcp3-isolated-v1', '--placement-graspable-filter-v1',
           '--world-model-parameters-v1', '--native-sleep-policy-compat-v1',
           '--per-world-model-references-v1',
           str(ROOT / 'runs/warp4' / (a.job + '-references-d236') / 'per-world-references.json'),
           '--out', str(out)]
    if flow == 'beampair':
        cmd += ['--teacher-source', str(ROOT / 'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247')]
    if a.debug:
        cmd += ['--warp-debug-v1']
    if a.trace:
        cmd += ['--warp-workspace-trace-v1']
    if a.verify:
        cmd += ['--warp-verify-cuda-v1']
    if a.diagnostic_ticks is not None:
        cmd += ['--diagnostic-ticks',str(a.diagnostic_ticks)]
    if a.memcheck:
        cmd = ['/usr/local/cuda/bin/compute-sanitizer', '--tool', 'memcheck',
               '--error-exitcode', '86', '--print-limit', '20', '--log-file',
               str(out.with_suffix('.memcheck.log')), *cmd]
    env = {k: v for k, v in os.environ.items() if not k.startswith('CUDA_MPS_')}
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MUJOCO_GL='osmesa',
               PYTHONFAULTHANDLER='1', PYTHONUNBUFFERED='1')
    started = datetime.datetime.now(datetime.timezone.utc)
    source_sha=subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()
    with out.with_suffix('.log').open('w') as log:
        child = subprocess.Popen(cmd, cwd=src, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT,start_new_session=True)
        write(ROOT / 'leases/warp6.json', dict(task='warp6', pid=os.getpid(),
              pids=[child.pid], started_at=started.isoformat(),
              expected_end=(started + datetime.timedelta(hours=7)).isoformat(),
              source_sha=source_sha, stage=a.round + ' ' + a.job,
              concurrency=len(indices.split(',')), gpu_shared=False))
        write(out.with_suffix('.command.json'), dict(command=cmd, host='gcp3',
              source_sha=source_sha, planned_world_N=len(indices.split(',')),
              driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              start_utc=started.isoformat(), price_scope='1.096USD/h inherited estimate, not billing'))
        code = child.wait()
    write(out.with_suffix('.receipt.json'), dict(exit_code=code, pid=child.pid,
          end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
          status='exited' if code == 0 else 'HOST_ERROR',
          raw_summary_preserved=True, physical_outcome='read raw/result.json; native exit is not physical failure'))
    print(json.dumps(dict(job=a.job, exit_code=code, out=str(out))), flush=True)
    return 0 if code==0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
