"""Managed v96 student candidate.

MEASURED_SIM (default): plan-only until an approved v92 measured calibration
and a runnable bundle. DEV_PILOT (``--admission dev-pilot``): one exact
registered calibration sha256 (c0 = 0); every result is FUNCTIONAL_DEV with
its own cohort and can never be promoted to confirmatory/MEASURED_SIM evidence.
"""
from __future__ import annotations

import argparse
import errno
import json
from pathlib import Path
import shutil
import subprocess
import sys

from harness import zone_pair_highpose_contract as contract
from harness.zone_pair_highpose_runtime import Runtime
from harness import zone_pair_highpose_timing as time_budget
from harness import zone_pair_highpose_starts as starts
from scripts.run_final_environment_checks import write, check_source


def checkpoint_record(runtime_record, checkpoint):
    """Actual carried-prefix stop/reobserve receipts; never teleport/regrasp."""
    if not runtime_record or not runtime_record.get('pair'):
        return {'status': 'NOT_REACHED', 'checkpoint': checkpoint, 'robots': {}}
    session = runtime_record['pair'][0]
    wanted = session['plan']['checkpoint_segments'].get(checkpoint)
    rows = {}
    for rid, robot in session['robots'].items():
        events = robot['events']
        stopped = [e for e in events if e['event'] == 'checkpoint_high_stop' and e['seg'] == wanted]
        observed = [e for e in events if e['event'] == 'checkpoint_high_reobserved' and e['seg'] == wanted]
        # Every preceding leg must have started under a carry GO. A receipt
        # name alone cannot stand in for carrying the route from the dock.
        carried = {e.get('seg') for e in events if e['event'] == 'state' and e.get('state') == 'carry'}
        rows[rid] = {'high_stop': stopped, 'high_reobserved': observed,
                     'carried_prefix': wanted is not None and set(range(wanted)) <= carried}
    reached = (set(rows) == set(contract.ROBOTS)
               and all(r['high_stop'] and r['high_reobserved'] and r['carried_prefix'] for r in rows.values()))
    return {'status': 'SEQUENCE_OBSERVED_UNQUALIFIED' if reached else 'NOT_REACHED',
            'checkpoint': checkpoint, 'segment': wanted, 'robots': rows,
            'physical_success': None, 'cohort_role': 'FUNCTIONAL_DEV_REPLAY', 'confirmation_sample': False}


def time_case(case, check):
    return case['checkpoint'] if check == 'p03' else 'carry_full_route'


def run_case(bundle, out, *, seed, backend_factory, runtime_factory=Runtime,
             calibration=None, calibration_sha=None):
    # Check even a direct caller before creating output/backend/provider.
    starts.require_dev_seed(seed)
    mode = bundle.get('admission_mode', contract.MEASURED_SIM)
    cal = contract.calibration_for(mode, calibration, calibration_sha, bundle['map_id'])
    contract.require_runnable(bundle)
    time_budget.require_feasible(contract.resolve(bundle['map_id'])[0], time_case(bundle['case'], bundle['check']),
                                 bundle['check'], calibration=cal)
    expected = {**contract.bundle(bundle['map_id'], bundle['check'], mode),
                'source_sha': bundle['source_sha'], 'case': bundle['case']}
    if (contract.base.digest(bundle) != contract.base.digest(expected)
            or bundle['case'] not in contract.cases(bundle['check'], bundle['map_id'])):
        raise ValueError('v96 bundle/case mismatch')
    return student_run_case(bundle, out, seed=seed, backend_factory=backend_factory,
        runtime_factory=runtime_factory, calibration=calibration, calibration_sha=calibration_sha)


def student_run_case(bundle, out, *, seed, backend_factory, runtime_factory=Runtime,
                     calibration=None, calibration_sha=None):
    """Student-only copy of scripts/run_final_pair_v3.run_case with the v96 cap.

    The parent hard-codes the v88 120 SIM s student cap. v96 uses the
    coordinator's a-priori amendment (contract.CASE_CAP_S = 300 per case).
    Loop, clock, eval_sample/capture order and records are otherwise the
    parent's; no collection branch (v96 has no calibration checks).
    """
    import os
    out = Path(out)
    cap = contract.CASE_CAP_S
    if (bundle['check'] not in contract.CHECKS or bundle['case']['sim_cap_s'] != cap
            or bundle['timing'] != contract.execution_timing(bundle['check'])):
        raise ValueError('v96 case cap/timing differs from the registered student protocol')
    out.mkdir(parents=True, exist_ok=False)
    write(out/'bundle.json', bundle)
    write(out/'inputs/schedule.json', [])
    backend = runtime = None
    labels = ({k: bundle[k] for k in contract.DEV_PILOT_LABELS}
              if bundle.get('admission_mode') == contract.DEV_PILOT else {})
    result = {**labels, 'check': bundle['check'], 'case': bundle['case'], 'status': 'HOST_ERROR',
              'protocol_complete': False, 'physical_success': None, 'research_result': False,
              'student_control': True, 'reset_sim_cap_s': contract.RESET_CAP_S, 'check_sim_cap_s': cap,
              'timing': bundle['timing'], 'clearance_preflight': None,
              'loadavg_start': list(os.getloadavg()), 'failure': None}
    try:
        backend = backend_factory(bundle, out, seed=seed)
        reset = backend.reset(contract.RESET_CAP_S)
        if not 0 <= reset <= contract.RESET_CAP_S+1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        start = backend.now
        backend.set_deadline(start+cap)
        result['reset_sim_s'] = reset
        static, _, _ = contract.resolve(bundle['map_id'])
        runtime = runtime_factory(static, calibration, calibration_sha, seed=seed)
        runtime.initial_commands(start, backend.commands)
        steps = round(cap/contract.TICK_S)
        for i in range(steps+1):
            # Raw labels have no return channel into the command selector.
            backend.eval_sample()
            runtime.on_frames(backend.now, backend.capture())
            if i == steps:
                break
            for rid, action in runtime.step(backend.now):
                backend.issue(rid, action)
                runtime.on_command(rid, backend.now, action)
            for rid, action in runtime.arm_step(backend.now):
                backend.issue(rid, action)
                runtime.on_command(rid, backend.now, action)
            backend.advance_to(start+(i+1)*contract.TICK_S)
        if abs(backend.now-start-cap) > 1e-7:
            raise RuntimeError('INCOMPLETE_BOUNDED_PROTOCOL')
        result.update(protocol_complete=True, status='COLLECTED_UNQUALIFIED', check_sim_s=backend.now-start)
    except Exception as exc:
        result.update(status='HOST_ERROR', failure={'type': type(exc).__name__, 'message': str(exc),
            'class': 'ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'})
    finally:
        if runtime is not None:
            try:
                record = runtime.record()
                write(out/'student_record.json', record)
                if bundle['check'] == 'p03':
                    result['checkpoint'] = {**checkpoint_record(record, bundle['case']['checkpoint']), **labels}
            except Exception as exc:
                result.update(status='HOST_ERROR', record_error=str(exc))
        for owner in (runtime, backend):
            if owner is not None:
                try:
                    owner.close()
                except Exception as exc:
                    result.update(status='HOST_ERROR', cleanup_error=str(exc))
        result['loadavg_end'] = list(os.getloadavg())
        write(out/'result.json', result)
        write(out/'artifacts.sha256.json', {str(p.relative_to(out)): contract.base.sha(p)
            for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'})
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', choices=contract.CHECKS, required=True)
    p.add_argument('--map-id', choices=contract.registry()['maps'])
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--lock-owner', choices=('codex', 'claude', 'kiro'))
    p.add_argument('--calibration', type=Path)
    p.add_argument('--calibration-sha256')
    p.add_argument('--seed', type=int, default=911)
    p.add_argument('--admission', choices=('measured-sim', 'dev-pilot'), default='measured-sim',
                   help='dev-pilot: exact registered sha256 only; FUNCTIONAL_DEV, never promotable')
    return p


def admission_mode(args):
    return contract.DEV_PILOT if args.admission == 'dev-pilot' else contract.MEASURED_SIM


def plan(args):
    starts.require_dev_seed(args.seed)
    starts.registration()
    cases = contract.cases(args.check, args.map_id)
    mode = admission_mode(args)
    bundles = [{**contract.bundle(c['map_id'], args.check, mode), 'case': c,
                'source_sha': args.expected_source_sha} for c in cases]
    blocked = []
    try:
        for c in cases:
            contract.calibration_for(mode, args.calibration, args.calibration_sha256, c['map_id'])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        blocked.append(str(exc))
    try:
        for b in bundles:
            contract.require_runnable(b)
    except ValueError as exc:
        blocked.append(str(exc))
    lower_bounds = [row for c in cases for row in time_budget.bounds(contract.resolve(c['map_id'])[0], args.check)
                    if row['case'] == time_case(c, args.check)]
    blocked.extend('TIME_LOWER_BOUND_EXCEEDS_CASE_CAP: '+r['map_id']+'/'+r['case'] for r in lower_bounds if not r['feasible'])
    value = {'time_lower_bounds': lower_bounds, 'cohort_role': 'FUNCTIONAL_DEV_REPLAY',
        'confirmation_sample': False, 'admission_mode': mode,
        **(contract.DEV_PILOT_LABELS if mode == contract.DEV_PILOT else {}), 'execution_bundle_id': contract.BUNDLE_ID, 'status': 'DRAFT_UNSEALED',
        'check': args.check, 'execution_started': False, 'cases': cases, 'denominator': len(cases),
        'runnable': not blocked, 'blocked_on': blocked,
        'precondition': contract.DEV_PILOT_PRECONDITION if mode == contract.DEV_PILOT else contract.PRECONDITION,
        'calibration_sha256': args.calibration_sha256, 'source_sha': args.expected_source_sha,
        'seed': args.seed, 'bundles_sha256': [contract.base.digest(b) for b in bundles],
        'physical_success': None, 'research_result': False}
    return value, bundles


def main(argv=None):
    args = parser().parse_args(argv)
    admission, bundles = plan(args)
    if not args.execute:
        print(json.dumps(admission, ensure_ascii=False, indent=2))
        return 0
    if not admission['runnable']:
        raise ValueError('; '.join(admission['blocked_on']))
    check_source(args.expected_source_sha)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        cwd=contract.ROOT, text=True).strip()).parent
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary/'outputs').resolve()):
        raise ValueError('raw output must be absolute under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    from scripts.agent_lock import DEFAULT_ROOT, status
    held = status(DEFAULT_ROOT)
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    if not held or not held['pid_alive'] or held['owner'] != args.lock_owner or held['branch'] != branch:
        raise ValueError('live owned host lock for this branch required')
    from sim.final_pair_v3 import PhysicsBackend
    args.output.mkdir(parents=True)
    write(args.output/'plan.json', admission)
    shutil.copyfile(args.calibration, args.output/('dev_pilot_calibration.json' if admission_mode(args) == contract.DEV_PILOT
                                                   else 'measured_calibration.json'))
    results = []
    for bundle in bundles:
        results.append(run_case(bundle, args.output/bundle['case']['id'], seed=args.seed,
            backend_factory=PhysicsBackend, calibration=args.calibration, calibration_sha=args.calibration_sha256))
        if results[-1]['status'] == 'HOST_ERROR':
            break
    unattempted = [c['id'] for c in admission['cases'][len(results):]]
    unchanged = all({**contract.bundle(b['map_id'], args.check), 'case': b['case'],
                     'source_sha': args.expected_source_sha} == b for b in bundles)
    failed = bool(unattempted) or not unchanged or any(r['status'] == 'HOST_ERROR' for r in results)
    labels = contract.DEV_PILOT_LABELS if admission_mode(args) == contract.DEV_PILOT else {}
    write(args.output/'result.json', {**labels, 'status': 'HOST_ERROR' if failed else 'COLLECTED_UNQUALIFIED',
        'cases': results, 'unattempted': unattempted, 'denominator': len(admission['cases']),
        'source_unchanged': unchanged, 'physical_success': None, 'research_result': False})
    return int(failed)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
