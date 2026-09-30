"""Managed DRAFT v88 pair execution and teacher calibration acquisition.

Without --execute this only prints a plan. Physics/model workers are lazy and
require committed source, an owned host lock and 10 GiB free before starting.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from harness import zone_final_pair_contract as contract
from harness.zone_final_pair_calibration import schedule
from harness.zone_final_pair_clearance import require_collection_clearance
from scripts.run_final_environment_checks import write, check_source


def checkpoint_record(runtime_record, checkpoint):
    """Local sequence receipts only, never a physical/GT success decision."""
    if not runtime_record or not runtime_record.get('pair'):
        return {'status': 'NOT_REACHED', 'checkpoint': checkpoint, 'robots': {}}
    session = runtime_record['pair'][0]
    wanted = session['plan']['checkpoint_segments'].get(checkpoint)
    rows = {}
    for rid, robot in session['robots'].items():
        events = robot['events']
        openings = [e for e in events if e['event'] == 'checkpoint_open' and e['seg']+1 == wanted]
        # state transitions carry explicit seg through the frozen logger.
        lifted = [e for e in events if e['event'] == 'state' and e.get('state') == 'wait_carry'
                  and e.get('seg') == wanted]
        rows[rid] = {'opened': openings, 'relift_sequence_receipts': lifted}
    reached = set(rows) == set(contract.ROBOTS) and all(r['opened'] and r['relift_sequence_receipts'] for r in rows.values())
    return {'status': 'SEQUENCE_OBSERVED_UNQUALIFIED' if reached else 'NOT_REACHED',
            'checkpoint': checkpoint, 'segment': wanted, 'robots': rows, 'physical_success': None}


def run_case(bundle, out, *, seed, backend_factory, runtime_factory=None, calibration=None, calibration_sha=None):
    require_collection_clearance(bundle)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'bundle.json', bundle)
    collection = bundle['check'].startswith('calibration-')
    cap = 370. if collection else 120.
    if bundle['case']['sim_cap_s'] != cap or bundle['timing'] != contract.execution_timing(bundle['check']):
        raise ValueError('v88 case cap/timing differs from registered acquisition or student protocol')
    events = schedule(bundle['check']) if collection else []
    write(out / 'inputs/schedule.json', events)
    backend = runtime = None
    result = {'check': bundle['check'], 'case': bundle['case'], 'status': 'HOST_ERROR',
              'protocol_complete': False, 'physical_success': None, 'research_result': False,
              'student_control': not collection, 'reset_sim_cap_s': 5., 'check_sim_cap_s': cap,
              'timing': bundle['timing'],
              'loadavg_start': list(os.getloadavg()), 'failure': None}
    try:
        backend = backend_factory(bundle, out, seed=seed)
        reset = backend.reset(contract.RESET_CAP_S)
        if not 0 <= reset <= contract.RESET_CAP_S+1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        start = backend.now
        backend.set_deadline(start+cap)
        result['reset_sim_s'] = reset
        if not collection:
            if runtime_factory is None:
                from harness.zone_final_pair_runtime import Runtime
                runtime_factory = Runtime
            static, _, _ = contract.resolve(bundle['map_id'])
            runtime = runtime_factory(static, calibration, calibration_sha, seed=seed)
            runtime.initial_commands(start, backend.commands)
        event_i = 0
        steps = round(cap/contract.TICK_S)
        frame_stride = round(contract.COLLECTION_FRAME_S/contract.TICK_S)
        for i in range(steps+1):
            elapsed = i*contract.TICK_S
            # Raw labels have no return channel into either command selector.
            backend.eval_sample()
            if runtime is not None or i % frame_stride == 0:
                frames = backend.capture()
                if runtime is not None:
                    runtime.on_frames(backend.now, frames)
            if i == steps:
                break
            while event_i < len(events) and events[event_i]['t'] <= elapsed+1e-8:
                e = events[event_i]
                backend.issue(e['robot_id'], e['action'])
                event_i += 1
            if runtime is not None:
                for rid, action in runtime.step(backend.now):
                    backend.issue(rid, action)
                    runtime.on_command(rid, backend.now, action)
                for rid, action in runtime.arm_step(backend.now):
                    backend.issue(rid, action)
                    runtime.on_command(rid, backend.now, action)
            backend.advance_to(start+(i+1)*contract.TICK_S)
        if event_i != len(events) or abs(backend.now-start-cap) > 1e-7:
            raise RuntimeError('INCOMPLETE_BOUNDED_PROTOCOL')
        result.update(protocol_complete=True, status='COLLECTED_UNQUALIFIED', check_sim_s=backend.now-start)
    except Exception as exc:
        result.update(status='HOST_ERROR', failure={'type': type(exc).__name__, 'message': str(exc),
            'class': 'ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'})
    finally:
        if runtime is not None:
            try:
                record = runtime.record()
                write(out / 'student_record.json', record)
                if bundle['check'] == 'p03':
                    result['checkpoint'] = checkpoint_record(record, bundle['case']['checkpoint'])
            except Exception as exc:
                result.update(status='HOST_ERROR', record_error=str(exc))
        for owner in (runtime, backend):
            if owner is not None:
                try:
                    owner.close()
                except Exception as exc:
                    result.update(status='HOST_ERROR', cleanup_error=str(exc))
        result['loadavg_end'] = list(os.getloadavg())
        write(out / 'result.json', result)
        write(out / 'artifacts.sha256.json', {str(p.relative_to(out)): contract.base.sha(p)
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
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    cases = contract.cases(args.check, args.map_id)
    bundles = [{**contract.bundle(c['map_id'], args.check), 'case': c,
                'source_sha': args.expected_source_sha} for c in cases]
    blocked = []
    for bundle in bundles:
        if bundle['clearance_preflight'] is not None and not bundle['clearance_preflight']['admitted']:
            blocked.append('FULL_PATH_CLEARANCE_REJECTED: ' + bundle['clearance_preflight']['reason'])
    if args.check in ('p03', 'carry'):
        try:
            for c in cases:
                contract.measured_calibration(args.calibration, args.calibration_sha256, c['map_id'])
        except (ValueError, OSError, KeyError) as exc:
            blocked.append(str(exc))
    plan = {'execution_bundle_id': contract.BUNDLE_ID, 'status': 'DRAFT_UNSEALED', 'check': args.check,
        'execution_started': False, 'cases': cases, 'denominator': len(cases), 'runnable': not blocked,
        'blocked_on': blocked, 'source_sha': args.expected_source_sha, 'seed': args.seed,
        'bundles_sha256': [contract.base.digest(b) for b in bundles], 'physical_success': None}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if blocked:
        raise ValueError('; '.join(blocked))
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
    write(args.output/'plan.json', plan)
    if args.calibration:
        shutil.copyfile(args.calibration, args.output/'measured_calibration.json')
    results = []
    for bundle in bundles:
        results.append(run_case(bundle, args.output/bundle['case']['id'], seed=args.seed,
            backend_factory=PhysicsBackend, calibration=args.calibration, calibration_sha=args.calibration_sha256))
        if results[-1]['status'] == 'HOST_ERROR':
            break
    unattempted = [c['id'] for c in cases[len(results):]]
    unchanged = all({**contract.bundle(b['map_id'], args.check), 'case': b['case'],
                     'source_sha': args.expected_source_sha} == b for b in bundles)
    failed = bool(unattempted) or not unchanged or any(r['status'] == 'HOST_ERROR' for r in results)
    write(args.output/'result.json', {'status': 'HOST_ERROR' if failed else 'COLLECTED_UNQUALIFIED',
        'cases': results, 'unattempted': unattempted, 'denominator': len(cases),
        'source_unchanged': unchanged, 'physical_success': None, 'research_result': False})
    return int(failed)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
