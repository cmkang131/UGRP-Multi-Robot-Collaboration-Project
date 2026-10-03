"""Managed v92 loaded teacher collection; v91 loop and SIM-slot admission.

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
from harness import zone_final_pair_loaded as loaded
from harness.zone_final_pair_loaded_schedule import schedule, CAP_S
from harness.zone_final_pair_loaded_clearance import require_collection_clearance, rejection_message
from scripts.run_final_environment_checks import write, check_source


def run_case(bundle, out, *, seed, backend_factory, host_snapshot=None):
    loaded.require_seed(bundle, seed)
    preflight = require_collection_clearance(bundle)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'bundle.json', bundle)
    cap = CAP_S
    if bundle['case']['sim_cap_s'] != cap or bundle['timing'] != loaded.timing():
        raise ValueError('v92 case cap/timing differs from registered acquisition')
    events = schedule(bundle['check'])
    write(out / 'inputs/schedule.json', events)
    if contract.base.sha(out / 'inputs/schedule.json') != bundle['schedule']['sha256']:
        raise ValueError('v92 written schedule hash mismatch')
    write(out / 'inputs/measurement_design.json', bundle['measurement'])
    backend = None
    result = {'check': bundle['check'], 'case': bundle['case'], 'status': 'HOST_ERROR',
              'protocol_complete': False, 'physical_success': None, 'research_result': False,
              'student_control': False, 'reset_sim_cap_s': 5., 'check_sim_cap_s': cap,
              **loaded.record(bundle),
              'timing': bundle['timing'],
              'clearance_preflight': preflight,
              'loadavg_start': list(os.getloadavg()), 'failure': None}
    if host_snapshot is not None:
        result['host_start'] = host_snapshot()
    try:
        backend = backend_factory(bundle, out, seed=seed)
        reset = backend.reset(contract.RESET_CAP_S)
        if not 0 <= reset <= contract.RESET_CAP_S+1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        start = backend.now
        backend.set_deadline(start+cap)
        result['reset_sim_s'] = reset
        event_i = 0
        steps = round(cap/contract.TICK_S)
        frame_stride = round(contract.COLLECTION_FRAME_S/contract.TICK_S)
        for i in range(steps+1):
            elapsed = i*contract.TICK_S
            # Raw labels have no return channel into the fixed teacher schedule.
            backend.eval_sample()
            if i % frame_stride == 0:
                backend.capture()
            if i == steps:
                break
            while event_i < len(events) and events[event_i]['t'] <= elapsed+1e-8:
                e = events[event_i]
                backend.issue(e['robot_id'], e['action'])
                event_i += 1
            backend.advance_to(start+(i+1)*contract.TICK_S)
        if event_i != len(events) or abs(backend.now-start-cap) > 1e-7:
            raise RuntimeError('INCOMPLETE_BOUNDED_PROTOCOL')
        result.update(protocol_complete=True, status='COLLECTED_UNQUALIFIED', check_sim_s=backend.now-start)
    except Exception as exc:
        result.update(status='HOST_ERROR', failure={'type': type(exc).__name__, 'message': str(exc),
            'class': 'ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'})
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception as exc:
                result.update(status='HOST_ERROR', cleanup_error=str(exc))
        result['loadavg_end'] = list(os.getloadavg())
        if host_snapshot is not None:
            result['host_end'] = host_snapshot()
        failed = result['status'] == 'HOST_ERROR'
        result['collection_data_status'] = 'PARTIAL_INVALID_HOST_ERROR' if failed else 'UNQUALIFIED'
        result['partial_data_retained'] = failed
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
    p.add_argument('--sim-slot', help='owned sim-* slot under a non-timing SIM coordinator; omitted uses exclusive physics lock')
    p.add_argument('--calibration', type=Path)
    p.add_argument('--calibration-sha256')
    p.add_argument('--seed', type=int, default=911)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if not loaded.selected(args.check, args.map_id):
        raise ValueError('v92 requires loaded training collection on the two-door map')
    if args.calibration is not None or args.calibration_sha256 is not None:
        raise ValueError('v92 teacher collection does not consume a fitted calibration')
    cases = loaded.cases(args.check, args.map_id)
    bundles = [{**loaded.bundle(c['map_id'], args.check), 'case': c,
                'source_sha': args.expected_source_sha} for c in cases]
    blocked = []
    for bundle in bundles:
        loaded.require_seed(bundle, args.seed)
        if bundle['clearance_preflight'] is not None and not bundle['clearance_preflight']['admitted']:
            blocked.append(rejection_message(bundle['clearance_preflight']))
    from scripts.agent_lock import DEFAULT_ROOT, status
    from scripts.agent_sim_slots import require_sim_slot, sim_snapshot, sim_holders
    snapshot = lambda: sim_snapshot(DEFAULT_ROOT)
    plan = {'execution_bundle_id': bundles[0]['execution_bundle_id'], 'status': 'DRAFT_UNSEALED', 'check': args.check,
        **loaded.record(bundles[0]),
        'execution_started': False, 'cases': cases, 'denominator': len(cases), 'runnable': not blocked,
        'blocked_on': blocked, 'source_sha': args.expected_source_sha, 'seed': args.seed,
        'bundles_sha256': [contract.base.digest(b) for b in bundles], 'physical_success': None,
        'clearance_preflight': [b['clearance_preflight'] for b in bundles]}
    plan.update(lock_mode='sim_slot' if args.sim_slot else 'exclusive', sim_slot=args.sim_slot,
                host_start=snapshot())
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
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    if args.sim_slot:
        require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner=args.lock_owner, branch=branch)
    else:
        held = status(DEFAULT_ROOT)
        if (not held or not held['pid_alive'] or held['owner'] != args.lock_owner
                or held['branch'] != branch or sim_holders(DEFAULT_ROOT)):
            raise ValueError('live owned host lock for this branch required')
    from sim.final_pair_loaded import PhysicsBackend
    args.output.mkdir(parents=True)
    plan.update(execution_started=True, host_start=snapshot())
    write(args.output/'plan.json', plan)
    results = []
    for bundle in bundles:
        results.append(run_case(bundle, args.output/bundle['case']['id'], seed=args.seed,
            backend_factory=PhysicsBackend, host_snapshot=snapshot))
        if results[-1]['status'] == 'HOST_ERROR':
            break
    unattempted = [c['id'] for c in cases[len(results):]]
    unchanged = all({**loaded.bundle(b['map_id'], args.check), 'case': b['case'],
                     'source_sha': args.expected_source_sha} == b for b in bundles)
    failed = bool(unattempted) or not unchanged or any(r['status'] == 'HOST_ERROR' for r in results)
    write(args.output/'result.json', {'status': 'HOST_ERROR' if failed else 'COLLECTED_UNQUALIFIED',
        **loaded.record(bundles[0]),
        'cases': results, 'unattempted': unattempted, 'denominator': len(cases),
        'host_start': plan['host_start'], 'host_end': snapshot(),
        'lock_mode': plan['lock_mode'], 'sim_slot': args.sim_slot,
        'source_unchanged': unchanged, 'physical_success': None, 'research_result': False})
    return int(failed)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
