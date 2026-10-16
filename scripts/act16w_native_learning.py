"""Finite native-only dataset/training/validation stages, without wall caps.

The operator reviews each completed physical stage before the next invocation.
No final evaluation, automatic retries or fallback controller is launched here.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from act16w_runtime import ACT_SHA, frozen_source, require_gcp2, sha256

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
ACT = B/'src'/ACT_SHA
PY = B.parent/'ugrp-rl1b-act-env/bin/python'
PROTOCOL = ROOT/'experiments/2026-10-16-act16w/resume3/protocol.json'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--stage', choices=('dataset', 'train', 'validate'), required=True)
    for key in ('native-gate', 'out', 'references'):
        p.add_argument('--'+key, type=Path, required=True)
    for key in ('records', 'review', 'dataset-root', 'checkpoint', 'capacity', 'curriculum-starts'):
        p.add_argument('--'+key, type=Path)
    p.add_argument('--arm', choices=('A', 'B', 'C', 'D1'))
    p.add_argument('--history', choices=('off', 'wheel_pulse_train_mean'))
    a = p.parse_args()
    if not a.enabled:
        p.error('explicit native stage opt-in required')
    host, source = require_gcp2(training=True), frozen_source(ROOT)
    gate = read(a.native_gate)
    if (gate.get('contact_profile') != 'warp_native_contact_v1' or not gate.get('passed')
            or gate.get('N') != 40 or gate.get('n', 0) < 38
            or gate.get('training_rgb') is not False or gate.get('input_audit_violations') != 0):
        raise ValueError('completed independent camera-off native40 gate required')
    for row in gate['raw_results']+gate['runtime_profiles']:
        if sha256(row['path']) != row['sha256']:
            raise ValueError('native gate raw evidence changed')
    protocol = read(PROTOCOL)
    if a.stage == 'dataset':
        if not a.records or not a.review:
            p.error('recorded40 and inspected review receipt required')
        record = read(a.records/'summary.json'); review = read(a.review)
        if (not record.get('complete') or not record.get('gate_passed')
                or review.get('approved') is not True
                or review.get('gate_recount_sha256') != sha256(a.native_gate)
                or review.get('record_summary_sha256') != sha256(a.records/'summary.json')):
            raise ValueError('review must bind this native gate and completed recording40')
    elif not a.dataset_root:
        p.error('native dataset required')
    else:
        manifest = read(a.dataset_root/'dataset/manifest.json')
        if (not manifest.get('complete') or manifest.get('contact_profile') != 'warp_native_contact_v1'
                or manifest.get('native_gate', {}).get('sha256') != sha256(a.native_gate)):
            raise ValueError('native dataset/gate provenance mismatch')
    if a.stage == 'train' and (a.arm is None or a.history is None):
        p.error('explicit arm/history required')
    if a.stage == 'train' and ((a.arm == 'A' and (a.history != 'off' or a.curriculum_starts))
            or (a.arm == 'B' and (a.history != 'wheel_pulse_train_mean' or a.curriculum_starts))
            or (a.arm in ('C', 'D1') and not a.curriculum_starts)):
        p.error('registered A/B history and separate C/D1 curriculum required')
    if a.stage == 'validate' and (not a.checkpoint or not a.capacity or not a.arm or not a.records):
        p.error('checkpoint/capacity/arm/completed record groups required')
    a.out.mkdir(parents=True, exist_ok=False)
    lease = B/'leases'/('act16w-native-learning-'+a.stage+('-'+a.arm if a.arm else '')+'.json')
    report = dict(status='running', complete=False, source_sha=source, host=host,
        stage=a.stage, arm=a.arm, contact_profile='warp_native_contact_v1', wall_cap=None,
        started_utc=datetime.now(timezone.utc).isoformat(), final40_accessed=False)
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-native-learning', pid=os.getpid(), start=report['started_utc'],
            expected_end='finite optimizer10000 or registered validation8; no wall cap', concurrency=0), stream)
    children, stop = [], {'requested': False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(requested=True))
    def run(name, arguments, *, env=None):
        if stop['requested']:
            raise InterruptedError('supervisor stop before '+name)
        argv = [str(PY), '-u', *map(str, arguments)]
        with (a.out/(name+'.log')).open('x') as log:
            child = subprocess.Popen(argv, cwd=Q, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, env={**os.environ,
                    'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1',
                    'OPENBLAS_NUM_THREADS': '1', 'MUJOCO_GL': 'osmesa', **(env or {})})
            children.append(child)
            write(a.out/(name+'-launch.json'), dict(pid=child.pid, argv=argv, source_sha=source))
            while child.poll() is None:
                if stop['requested']:
                    raise InterruptedError('supervisor stop during '+name)
                report.update(active_child=dict(name=name, pid=child.pid))
                write(a.out/'summary.json', report); time.sleep(2)
            if child.returncode:
                raise RuntimeError(name+' failed; preserve log, diagnose before retry')
    try:
        if a.stage == 'dataset':
            selection = a.out/'selection.json'
            write(selection, dict(selected_indices=list(range(40)), selected_seeds=protocol['record_seeds'],
                reason='all40 preregistered native recording starts; no compatibility/outcome exclusions'))
            records = a.out/'records'
            run('dataset', [ROOT/'scripts/act16w_dataset.py', '--enabled', '--root', records,
                '--batch', a.records, '--selection', selection, '--protocol', PROTOCOL,
                '--act-source', ACT, '--native-gate', a.native_gate])
            report.update(dataset_root=str(records))
        else:
            admission = a.out/'admission'
            run('admit', [ROOT/'scripts/act16w_admit_dataset.py', '--approve-reviewed-records',
                '--dataset-root', a.dataset_root, '--record-plans', a.references/'plans.json',
                '--out', admission, '--native-gate', a.native_gate])
            if a.stage == 'train':
                common = [ROOT/'scripts/train_act16w.py', '--act-source', ACT, '--dataset',
                    a.dataset_root/'dataset', '--admission', admission/'training-admission.json',
                    '--schedule-steps', '10000', '--seed', '20261015',
                    '--history-causal-split-v1', a.history]
                if a.curriculum_starts:
                    common += ['--curriculum-starts-v1', a.curriculum_starts]
                smoke = a.out/'smoke'; main = a.out/'main'
                run('smoke', [*common, '--output', smoke, '--stage', 'smoke', '--steps', '300'])
                saved = read(smoke/'summary.json')
                if not saved['complete'] or not saved['readback_verified']:
                    raise ValueError('completed smoke/readback required')
                run('main', [*common, '--output', main, '--stage', 'main', '--steps', '10000',
                    '--smoke-summary', smoke/'summary.json', '--resume', saved['last_checkpoint']])
                final = read(main/'summary.json')
                if not final['complete'] or not final['readback_verified'] or final['steps_completed'] != 10000:
                    raise ValueError('complete registered training/readback required')
                report.update(checkpoint=str(Path(final['last_checkpoint'])/'actor'), steps=10000)
            else:
                native = {'UGRP_ACT16W_NATIVE_GATE': str(a.native_gate)}
                run('validation', [ROOT/'scripts/act16w_eval_batch.py', '--enabled', '--checkpoint',
                    a.checkpoint, '--references-root', a.references, '--groups',
                    a.records/'exact-groups/model-groups.json', '--protocol', PROTOCOL,
                    '--capacity-receipt', a.capacity, '--out', a.out/'validation', '--split', 'validation',
                    '--name', 'native-'+a.arm+'-'+a.out.name, '--max-worlds', '8',
                    '--speed-gate-override', 'Native MJWarp ACT study; record world latency separately from aggregate throughput; fixed90SIM task, no wall cap.'], env=native)
                run('teacher-forced', [ROOT/'scripts/audit_act16w_validation.py', '--enabled',
                    '--act-source', ACT, '--dataset', a.dataset_root/'dataset', '--checkpoint',
                    a.checkpoint, '--protocol', PROTOCOL, '--out', a.out/'teacher-forced'])
                result = read(a.out/'validation/summary.json')
                if not result['complete'] or result['N'] != 8:
                    raise ValueError('all registered validation8 required')
                report.update(n=result['n'], N=result['N'])
        report.update(status='complete', complete=True)
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error, InterruptedError) else 'HOST_ERROR',
                      complete=False, error=repr(error))
        raise
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM); child.wait()
        report['ended_utc'] = datetime.now(timezone.utc).isoformat()
        write(a.out/'summary.json', report)
        if read(lease).get('pid') == os.getpid():
            lease.unlink()


if __name__ == '__main__':
    main()
