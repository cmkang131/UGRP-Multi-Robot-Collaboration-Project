"""Wait for matched final A/B models, then run registered validation5 only.

No wall deadline, model selection or final40 access. Children retain their
own seed, provenance, native input and global40-world admission checks.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from act16w_runtime import require_gcp2, frozen_source

B = Path('/home/ugrp/ugrp-sim')
ROOT = Path(__file__).resolve().parents[1]
PY = B.parent/'ugrp-rl1b-act-env/bin/python'
ACT = B/'src/3f99d58c5ada0862e669ef4065c0ba957f1b4547'
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    for key in ('training-root', 'dataset-root', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('explicit validation-only opt-in required')
    host = require_gcp2(training=True)
    source = frozen_source(ROOT)
    args.out.mkdir(parents=True, exist_ok=False)
    lease = B/'leases/act16w-validation-pipeline.json'
    report = dict(status='WAIT_A_B', complete=False, source_sha=source, host=host,
                  started_utc=datetime.now(timezone.utc).isoformat(), wall_cap=None,
                  model_selection=False, final_evaluation_accessed=False)
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-validation-pipeline', pid=os.getpid(),
                       start=report['started_utc'], expected_end='A/B10000 then finite validation5; no wall cap',
                       concurrency=0), stream)
    stopping = {'requested': False}
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.update(requested=True))
    children = []
    try:
        while True:
            if stopping['requested']:
                raise InterruptedError('supervisor stop')
            summaries = {arm: read(args.training_root/f'{arm}-main/summary.json')
                         for arm in ('A', 'B')}
            if any(row['status'] not in ('running', 'complete') for row in summaries.values()):
                raise ValueError('A/B training failed; no evaluation admitted')
            if all(row['complete'] for row in summaries.values()):
                break
            report['training_steps'] = {arm: row['steps_completed'] for arm, row in summaries.items()}
            write(args.out/'summary.json', report)
            time.sleep(5)
        for arm, row in summaries.items():
            if row['steps_completed'] != 10000 or not row['readback_verified']:
                raise ValueError('fixed final/readback model required '+arm)
        same = ('source_sha', 'dataset_manifest_sha256', 'seed', 'batch_size', 'chunk',
                'period_s', 'schedule_steps', 'done_loss', 'lerobot_act_sha256')
        if any(summaries['A'][key] != summaries['B'][key] for key in same):
            raise ValueError('unmatched A/B training configuration')
        starts = read(B/'runs/act16w-resume2-start-instance-audit-r2/summary.json')
        if starts['status'] != 'complete' or starts['N'] != 40 or not all(
                row['exact_native_start_match'] for row in starts['rows']):
            raise ValueError('native same-kind metric qualification incomplete')
        protocol = ROOT/'experiments/2026-10-16-act16w/resume2/comparison-protocol-v2.json'
        report.update(status='VALIDATION_A_B', checkpoints={
            arm: str(Path(row['last_checkpoint'])/'actor') for arm, row in summaries.items()})
        for arm, row in summaries.items():
            checkpoint = Path(row['last_checkpoint'])/'actor'
            native = [ROOT/'scripts/act16w_eval_batch.py', '--enabled', '--checkpoint', checkpoint,
                '--references-root', B/'runs/act16w-resume2-record-references',
                '--groups', B/'runs/act16w-resume2-record-groups/model-groups.json',
                '--protocol', protocol, '--capacity-receipt', B/'runs/act16w-capacity-receipt.json',
                '--out', args.out/(arm+'-native'), '--split', 'validation', '--name', arm+'-validation-r1',
                '--max-worlds', '5', '--speed-gate-override',
                'Explicit MJWarp batch study; latency>6 is recorded, no latency pass claim. '
                'AGENTS permits a recorded operational override; user removed wall caps. '
                'Native physics/camera and finite90SIM task definition stay unchanged.']
            offline = [ROOT/'scripts/audit_act16w_validation.py', '--enabled', '--act-source', ACT,
                '--dataset', args.dataset_root/'dataset', '--checkpoint', checkpoint,
                '--protocol', protocol, '--out', args.out/(arm+'-teacher-forced')]
            for kind, command in (('native', native), ('teacher-forced', offline)):
                name = arm+'-'+kind
                argv = [str(PY), '-u', *map(str, command)]
                log = (args.out/(name+'.log')).open('x')
                child = subprocess.Popen(argv, cwd=Q, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
                         'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'})
                children.append(dict(name=name, proc=child, log=log))
                write(args.out/(name+'-launch.json'), dict(pid=child.pid, argv=argv, source_sha=source))
        while any(child['proc'].poll() is None for child in children):
            if stopping['requested']:
                raise InterruptedError('supervisor stop during validation')
            report['active_children'] = [dict(name=c['name'], pid=c['proc'].pid)
                                         for c in children if c['proc'].poll() is None]
            write(args.out/'summary.json', report)
            time.sleep(2)
        if any(child['proc'].returncode for child in children):
            raise RuntimeError('validation child failed; inspect immutable logs')
        results = {name: read(args.out/name/'summary.json')
                   for name in (c['name'] for c in children)}
        if not all(row['complete'] for row in results.values()):
            raise ValueError('validation coverage incomplete')
        report.update(status='VALIDATION_A_B_COMPLETE', complete=True,
                      next='post-action alignment + video review, then select history for C; final40 remains unopened')
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error, InterruptedError) else 'HOST_ERROR',
                      complete=False, error=repr(error))
        raise
    finally:
        for child in children:
            if child['proc'].poll() is None:
                os.killpg(child['proc'].pid, signal.SIGINT)
                try:
                    child['proc'].wait(timeout=90)
                except subprocess.TimeoutExpired:
                    os.killpg(child['proc'].pid, signal.SIGKILL)
                    child['proc'].wait()
            child['log'].close()
        report['ended_utc'] = datetime.now(timezone.utc).isoformat()
        write(args.out/'summary.json', report)
        if lease.exists() and read(lease).get('pid') == os.getpid():
            lease.unlink()


if __name__ == '__main__':
    main()
