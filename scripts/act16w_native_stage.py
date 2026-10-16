"""Native cohort teacher gate/record dispatcher; noslip baseline ends first.

No automatic retries, training, h4/h5 or final40. Every requested seed stays
in the denominator. A failed gate waits for raw analysis and a committed fix.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from act16w_runtime import frozen_source, require_gcp2, sha256

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
T = B/'src/warp1-teacher-snapshot-6f057f7e'
WARP = B/'runs/simalt3/warp-env/bin/python'


def read(path):
    return json.loads(path.read_text()) if path.exists() else json.loads(subprocess.check_output(['zstd', '-dc', str(path)+'.zst']))


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(path)


def recount(out, references, groups, *, record=False):
    """Read completed original per-world results, never dispatcher totals."""
    plans = read(references/'plans.json')['episodes']
    rows, receipts, profiles = [], [], []
    for group, indices in groups:
        folder = out/f'group-{group:02d}'/'controller'
        profile = folder/'native-contact.json'
        if profile.exists():
            p = read(profile)
            if p['gpu_noslip'] != 0 or any(p['cpu_noslip']) or p['cpu_impratio'] != 5:
                raise ValueError('native profile runtime mismatch')
            profiles.append(dict(path=str(profile), sha256=sha256(profile)))
        for world, index in enumerate(indices):
            result = folder/f'world-{world:03d}'/'result.json'
            if not result.exists() and not result.with_suffix('.json.zst').exists():
                rows.append(dict(seed=plans[index]['seed'], kind=plans[index]['kind'], success=False,
                                 status='HOST_ERROR', reason='missing original result', raw=str(result)))
                continue
            value = read(result)
            original = result if result.exists() else result.with_suffix('.json.zst')
            receipts.append(dict(path=str(original), sha256=sha256(original)))
            audit = value.get('input_audit', {})
            violations = sum(audit.get(k, 1) for k in ('invisible_measurements', 'held_world_reads'))
            success = (value.get('status') == 'complete' and value.get('physical_success') is True
                       and not value.get('cap_end') and value.get('training_rgb') is False and violations == 0)
            rows.append(dict(seed=plans[index]['seed'], kind=plans[index]['kind'], success=success,
                status=value.get('status'), lift_success=value.get('lift_success', False),
                release_success=value.get('release_success', False), cap_end=value.get('cap_end', False),
                input_audit_violations=violations, input_audit=audit,
                reason='success' if success else value.get('reason') or value.get('teacher', {}).get('command_result') or 'teacher_physical_or_input_failure',
                raw=str(original)))
    n, N = sum(r['success'] for r in rows), len(rows)
    violations = sum(r.get('input_audit_violations', 1) for r in rows)
    complete = N == 40 and len(receipts) == 40 and len(profiles) == len(groups)
    passed = complete and n >= 38 and violations == 0
    kinds = {k: dict(n=sum(r['success'] for r in rows if r['kind'] == k),
                     N=sum(r['kind'] == k for r in rows)) for k in ('cyan', 'red', 'green', 'yellow')}
    eligible = list(rows); counts = [40, len(receipts)]
    for key in ('lift_success', 'release_success', 'success'):
        eligible = [r for r in eligible if r.get(key)]; counts.append(len(eligible))
    failures = [dict(seed=r['seed'], category='HOST_ERROR' if r['status'] == 'HOST_ERROR' else 'cap_end' if r.get('cap_end') else 'teacher_failure',
        reason=r['reason'], blocking_object='not_attributed_before_playback', minimum_gap_m=None,
        minimum_gap_status='not measured; no geometric cause attribution', raw=r['raw']) for r in rows if not r['success']]
    table = dict(funnel=[dict(gate=g, passed=n, rejected=counts[i-1]-n if i else 0)
        for i,(g,n) in enumerate(zip(('requested', 'raw_results', 'stable_lift', 'stable_release', 'success'), counts))],
        rejections=failures, reason_distribution=dict(Counter(r['reason'] for r in failures)), raw=str(out), reproduce=sys.argv)
    write(out/'rejection_table.json', table)
    return dict(status='PASS' if passed else 'FAIL' if complete else 'HOST_ERROR',
        n=n, N=N, complete=complete, passed=passed, kinds=kinds, rows=rows,
        contact_profile='warp_native_contact_v1', training_rgb=record,
        camera_off_gate=not record, input_audit_violations=violations,
        raw_results=receipts, runtime_profiles=profiles, rejection_table=str(out/'rejection_table.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--stage', choices=('gate', 'record'), required=True)
    for key in ('references', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--native-gate', type=Path)
    args = parser.parse_args()
    if not args.enabled or (args.stage == 'record' and not args.native_gate):
        parser.error('explicit native gate/record opt-in and record gate required')
    host = require_gcp2(training=True); source = frozen_source(ROOT)
    args.out.mkdir(parents=True, exist_ok=False)
    lease = B/'leases'/('act16w-native-'+args.stage+'.json')
    report = dict(status='WAIT_NOSLIP_BASELINE', complete=False, source_sha=source, host=host,
                  started_utc=datetime.now(timezone.utc).isoformat(), wall_cap=None,
                  contact_profile='warp_native_contact_v1', stage=args.stage, final40_accessed=False)
    write(args.out/'rejection_table.json', dict(funnel=[dict(gate='requested', passed=40, rejected=0)],
        rejections=[], raw=str(args.out), reproduce=sys.argv))
    write(args.out/'queue.json', dict(source_sha=source, contact_profile='warp_native_contact_v1',
        rejection_table=str(args.out/'rejection_table.json'), references=str(args.references),
        wall_cap=None, training_rgb=args.stage == 'record'))
    stop = {'requested': False}; running = {}; finished = []
    signal.signal(signal.SIGINT, lambda *_: stop.update(requested=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(requested=True))
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-native-'+args.stage, pid=os.getpid(),
                       start=report['started_utc'], expected_end='finite40, no wall cap', concurrency=0), stream)
    def publish():
        write(args.out/'summary.json', report)
        write(lease, dict(task='act16w-native-'+args.stage, pid=os.getpid(), start=report['started_utc'],
            expected_end='finite40, no wall cap', concurrency=sum(len(j['indices']) for j in running.values())))
    try:
        while True:
            if stop['requested']: raise InterruptedError('supervisor stop')
            baseline = read(args.baseline/'summary.json')
            if baseline['status'] not in ('WAIT_A_B', 'VALIDATION_A_B'):
                write(args.out/'noslip-baseline-boundary.json', dict(summary=baseline,
                    summary_sha256=sha256(args.baseline/'summary.json'), native_result_pooled=False))
                break
            publish(); time.sleep(5)
        subprocess.run([str(WARP), str(ROOT/'scripts/act16w_baseline_recount.py'),
            '--root', str(args.baseline), '--out', str(args.out/'noslip-baseline-recount.json')], check=True)
        if not read(args.references/'summary.json')['complete']:
            raise ValueError('all40 exact native references required')
        plans = read(args.references/'plans.json')['episodes']
        protocol = read(ROOT/'experiments/2026-10-16-act16w/resume3/protocol.json')
        if [p['seed'] for p in plans] != protocol[args.stage+'_seeds']:
            raise ValueError('native preregistered ordered40 seeds mismatch')
        inventory = read(args.references/'inventory.json')
        subprocess.run([str(WARP), str(ROOT/'scripts/act16w_native_groups.py'), '--enabled',
            '--references', str(args.references), '--out', str(args.out/'exact-groups')], check=True)
        groups = [(i, g['indices']) for i,g in enumerate(read(args.out/'exact-groups/model-groups.json')['groups'])]
        if sorted(x for _,indices in groups for x in indices) != list(range(40)):
            raise ValueError('model groups changed requested denominator')
        # Host is assigned exclusively. Never overlap remaining baseline children,
        # reference setup or an unrecognized lease with this 40-world submission.
        while True:
            foreign = [str(p) for p in lease.parent.glob('*.json') if p != lease]
            if not foreign:
                break
            if stop['requested']: raise InterruptedError('supervisor stop waiting leases')
            report.update(status='WAIT_EXISTING_LEASES', existing_leases=foreign)
            publish(); time.sleep(5)
        report.update(status='NATIVE_'+args.stage.upper(), groups=groups)
        for group, indices in groups:
            if stop['requested']: raise InterruptedError('supervisor stop before new group')
            folder = args.out/f'group-{group:02d}'; folder.mkdir()
            first = inventory[indices[0]]
            runner = ['--physics-backend', 'mjwarp_batch_v1', '--teacher-source', str(T),
                '--plan', str(args.references/'plans.json'), '--world-episodes', ','.join(map(str,indices)),
                '--nworld', str(len(indices)), '--cap-s', '90', '--vm-hourly-usd', '1.096',
                '--scene-v5-v1', '--numpy-teacher-v1', '--batch-sleep-v1', '--native-sleep-policy-compat-v1',
                '--compiled-reference-v1', first['actuator'], '--compiled-geometry-312-v1', first['geometry'],
                '--per-world-model-references-v1', str(args.references/'per-world-references.json'),
                '--out', str(folder/'controller')]
            command = [str(WARP), '-u', str(ROOT/'scripts/act16w_native_run.py'), '--enabled', '--mode',
                       'teacher' if args.stage == 'gate' else 'record']
            if args.stage == 'record':
                command += ['--native-gate', str(args.native_gate)]
                write(folder/'runner-args.json', runner)
                runner = ['--enabled', '--qualified-source', str(Q), '--teacher-source', str(T),
                    '--qualification', str(B/'runs/warp3/teacher-gate-qualification-r1.json'),
                    '--runner-args-json', str(folder/'runner-args.json'), '--stage', 'pilot', '--out', str(folder/'capture')]
            command += ['--', *runner]
            log = (folder/'run.log').open('x')
            proc = subprocess.Popen(command, cwd=Q, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ,
                'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                'MUJOCO_GL': 'osmesa', 'LP_NUM_THREADS': '1'})
            running[group] = dict(proc=proc, log=log, indices=indices, folder=folder)
            write(folder/'launch.json', dict(pid=proc.pid, argv=command, source_sha=source))
            publish()
        while running:
            for group, job in list(running.items()):
                if job['proc'].poll() is not None:
                    job['log'].close(); finished.append(dict(group=group, exit_code=job['proc'].returncode))
                    del running[group]
                else:
                    progress = job['folder']/'controller/progress.json'
                    if progress.exists() and not (job['folder']/'first30.json').exists():
                        p = read(progress); sim = min(p['ticks'])*.1
                        if sim >= 30:
                            write(job['folder']/'first30.json', dict(sim_s=sim, loop_wall_s=p['loop_wall_s'],
                                world_latency_wall_per_SIM=p['loop_wall_s']/sim,
                                aggregate_wall_per_world_SIM=p['loop_wall_s']/sim/len(job['indices'])))
            if stop['requested']: raise InterruptedError('supervisor stop during stage')
            report.update(active=[dict(group=g, pid=j['proc'].pid) for g,j in running.items()], finished=finished)
            publish(); time.sleep(2)
        result = recount(args.out, args.references, groups, record=args.stage == 'record')
        result.update(source_sha=source, host=host, completed_utc=datetime.now(timezone.utc).isoformat())
        write(args.out/'gate-recount.json', result)
        report.update(status='PASS_REQUIRES_RECORD_REVIEW' if result['passed'] else 'FAIL_REQUIRES_VIDEO_REVIEW',
            complete=result['complete'], n=result['n'], N=result['N'], gate_passed=result['passed'],
            input_audit_violations=result['input_audit_violations'], next='inspect native raw/review before next stage')
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error, InterruptedError) else 'HOST_ERROR',
                      complete=False, error=repr(error))
        raise
    finally:
        for job in running.values():
            if job['proc'].poll() is None:
                os.killpg(job['proc'].pid, signal.SIGINT)
                try: job['proc'].wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(job['proc'].pid, signal.SIGTERM); job['proc'].wait()
            job['log'].close()
        report.update(ended_utc=datetime.now(timezone.utc).isoformat(), vm_stop_attempted=False)
        publish()
        if read(lease).get('pid') == os.getpid(): lease.unlink()


if __name__ == '__main__':
    main()
