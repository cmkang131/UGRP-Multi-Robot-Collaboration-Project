"""One immutable warp8 batch, isolated gcp3; no model keys or cloud CLI."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path('/home/ugrp/ugrp-sim')
OPS = ROOT / 'ops-reviews/warp8'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def main():
    signal.signal(signal.SIGINT, signal.default_int_handler)
    p = argparse.ArgumentParser()
    p.add_argument('--source-sha', required=True)
    p.add_argument('--tag', required=True)
    p.add_argument('--flow', choices=['beampair', 'release'], required=True)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--indices', required=True)
    p.add_argument('--references', type=Path)
    p.add_argument('--rejection-table', type=Path, default=OPS / 'prior-rejection_table.json')
    p.add_argument('--export', action='store_true')
    p.add_argument('--memcheck', action='store_true')
    a = p.parse_args()
    assert '/' not in a.tag and a.tag not in ('.', '..')
    src = ROOT / 'src' / a.source_sha
    assert subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip() == a.source_sha
    table = a.rejection_table
    assert table.is_absolute() and table.is_file()
    cases = json.loads(a.cases.read_text())
    indices = [int(i) for i in a.indices.split(',')]
    assert len(indices) == len(set(indices)), 'duplicate worlds are throughput only, not a gate'
    assert all(0 <= i < len(cases) for i in indices)
    out = ROOT / 'runs/warp8' / a.tag
    assert not out.exists() and not out.with_suffix('.command.json').exists()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(ROOT / 'ugrp' / ('.venv-sim' if a.export else '.venv-warp') / 'bin/python'),
           str(src / 'scripts/run_warp_flow_teacher.py'), '--flow', a.flow,
           '--adapter-source', str(ROOT / 'src' / ('835ccef26aa84b08cc8f7e256fd0f43aa1583ef9'
                if a.flow == 'beampair' else '8e81b7d96c0c73171635348c90631462adfe1eb0')),
           '--cases', str(a.cases), '--indices', a.indices,
           '--cap-s', '60' if a.flow == 'beampair' else '180', '--out', str(out),
           '--vm-hourly-usd', '1.096', '--gcp3-isolated-v1',
           '--placement-graspable-filter-v1', '--world-model-parameters-v1',
           '--native-sleep-policy-compat-v1', '--batch-per-world-speed-v1',
           '--rejection-table', str(table)]
    if a.flow == 'beampair':
        cmd += ['--teacher-source', str(ROOT / 'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247')]
    if a.export:
        cmd += ['--export-compiled-only']
    else:
        assert a.references is not None and a.references.is_file()
        cmd += ['--per-world-model-references-v1', str(a.references)]
    if a.memcheck:
        # Only a CUDA700 seed identified by a preceding gate may use this.
        assert len(indices) == 1 and not a.export
        cmd = ['/usr/local/cuda/bin/compute-sanitizer', '--tool', 'memcheck',
               '--error-exitcode', '86', '--print-limit', '20', '--log-file',
               str(out.with_suffix('.memcheck.log')), *cmd]
    env = {k: v for k, v in os.environ.items() if not k.startswith('CUDA_MPS_')}
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MUJOCO_GL='osmesa',
               PYTHONFAULTHANDLER='1', PYTHONUNBUFFERED='1')
    started = dt.datetime.now(dt.timezone.utc)
    # Resource cleanup deadline only. Planning/task limits remain computation/SIM.
    deadline = dt.datetime.fromisoformat(json.loads((OPS / 'host-start.json').read_text())['cleanup_deadline'])
    with out.with_suffix('.log').open('w') as log:
        child = subprocess.Popen(cmd, cwd=src, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        write(ROOT / 'leases' / ('warp8-' + a.tag + '.json'), dict(task='warp8', pid=os.getpid(), pids=[child.pid],
              started_at=started.isoformat(), expected_end=deadline.isoformat(),
              source_sha=a.source_sha, stage=a.tag, concurrency=len(indices), gpu_shared=False))
        write(out.with_suffix('.command.json'), dict(command=cmd, host='gcp3', project='ugrp-sim-c-1016',
              source_sha=a.source_sha, planned_world_N=len(indices),
              case_seeds=[cases[i]['plan']['seed'] for i in indices],
              cases_sha256=hashlib.sha256(a.cases.read_bytes()).hexdigest(),
              rejection_table=str(table), rejection_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
              driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              start_utc=started.isoformat(), export_only=a.export,
              price_scope='1.096USD/h inherited estimate, not billing'))
        try:
            with out.with_suffix('.resources.jsonl').open('w') as resources:
                while child.poll() is None:
                    now = dt.datetime.now(dt.timezone.utc)
                    gpu = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu',
                        '--format=csv,noheader,nounits'], capture_output=True, text=True)
                    resources.write(json.dumps(dict(utc=now.isoformat(), gpu=gpu.stdout.strip(),
                        load=os.getloadavg(), disk_free_bytes=__import__('shutil').disk_usage(ROOT).free)) + '\n')
                    resources.flush()
                    if now >= deadline:
                        assert str(out).encode() in Path(f'/proc/{child.pid}/cmdline').read_bytes().split(b'\0')
                        write(out.with_suffix('.supervisor-stop.json'), dict(status='HOST_ERROR',
                            reason_category='HOST_RESOURCE_DEADLINE', blocked_object='host:gcp3',
                            min_gap_m=None, task_cap_end=False, utc=now.isoformat()))
                        child.send_signal(signal.SIGINT)
                        break
                    time.sleep(10)
            code = child.wait()
        except BaseException:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
                child.wait()
            raise
    write(out.with_suffix('.receipt.json'), dict(exit_code=code, pid=child.pid,
          end_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
          status='exited' if code == 0 else 'HOST_ERROR', raw_summary_preserved=True,
          physical_outcome='summary/raw results; native exit is not physical failure'))
    print(json.dumps(dict(tag=a.tag, exit_code=code, out=str(out))), flush=True)
    return int(code != 0)


if __name__ == '__main__':
    raise SystemExit(main())
