"""Managed v101 unloaded gain/lag calibration acquisition (one registered run per invocation); no student.

Without --execute this only prints a plan. Physics workers are lazy and require committed source, 10 GiB free and an
owned non-timing --sim-slot (or the exclusive physics lock). SIM-time only: no wall-time or speed claim is made; each
result records the load average and the concurrent holders.
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

from harness import final_environment_gain_calibration_v101 as env
from scripts.run_final_environment_checks import check_source, write


def run_case(bundle, out, *, seed, backend_factory, host_snapshot=None):
    plan = bundle['measurement']
    env.validate(plan)
    run = env.run_row(plan, bundle['run_id'])
    if bundle['execution_bundle_id'] != env.BUNDLE_ID or bundle['check'] != env.CHECK or seed != run['seed']:
        raise ValueError('wrong gain calibration bundle or seed')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'bundle.json', bundle)
    backend = None
    result = {'status': 'HOST_ERROR', 'protocol_complete': False, 'physical_success': None,
              'research_result': False, 'student_control': False, 'model_calls': 0,
              'map_id': plan['map_id'], 'robot_id': 'r1', 'check': env.CHECK, 'run_id': run['id'],
              'role': run['role'], 'seed': seed, 'spawn_xy_yaw': run['spawn_xy_yaw'],
              'loadavg_start': list(os.getloadavg()), 'reset_sim_s': None, 'check_sim_s': None,
              'total_including_reset_cap_s': run['total_including_reset_cap_s']}
    if host_snapshot is not None:
        result['host_start'] = host_snapshot()
    try:
        backend = backend_factory(bundle, out, seed=seed)
        reset = backend.reset(plan['reset_cap_s'])
        result['reset_sim_s'] = reset
        if not 0 <= reset <= plan['reset_cap_s'] or abs(backend.now - reset) > 1e-7:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED_OR_INVALID_CLOCK')
        start = backend.now
        backend.set_deadline(start + run['sim_cap_s'])
        # Evaluation returns no observation; the only feedback is a private physics-owner abort.
        backend.eval_sample()
        quantum, half = plan['control_period_s'], plan['eval_pose_period_s']
        for i in range(round(run['sim_cap_s'] / quantum)):
            backend.issue('r1', env.action_at(run, i, plan))
            for j in (1, 2):
                backend.advance_to(start + i * quantum + j * half)
                backend.eval_sample()
            if abs(backend.now - start - (i + 1) * quantum) > 1e-7:
                raise RuntimeError('INEXACT_SAMPLE_CLOCK')
        result['check_sim_s'] = backend.now - start
        if (abs(result['check_sim_s'] - run['sim_cap_s']) > 1e-7
                or backend.now > run['total_including_reset_cap_s'] + 1e-7):
            raise RuntimeError('TOTAL_SIM_CAP_EXCEEDED')
        result.update(status='COLLECTED_UNQUALIFIED', protocol_complete=True)
    except Exception as error:
        result['failure'] = {'type': type(error).__name__, 'message': str(error),
                             'class': 'ENOSPC' if getattr(error, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'}
        if backend is not None:
            result['observed_sim_s'] = backend.now
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception as error:
                result.update(status='HOST_ERROR', protocol_complete=False, cleanup_error=str(error))
        result['loadavg_end'] = list(os.getloadavg())
        if host_snapshot is not None:
            result['host_end'] = host_snapshot()
        write(out / 'result.json', result)
        write(out / 'artifacts.sha256.json', {str(p.relative_to(out)): env.sha(p)
                                            for p in sorted(out.rglob('*')) if p.is_file()
                                            and p.name != 'artifacts.sha256.json'})
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', required=True, choices=(env.CHECK,))
    p.add_argument('--run-id', required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--lock-owner', choices=('claude', 'codex', 'kiro'))
    p.add_argument('--sim-slot', help='owned sim-* slot under a non-timing SIM coordinator; omitted uses the exclusive lock')
    p.add_argument('--seed', type=int, required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    bundle = env.bundle(args.run_id)
    from scripts.agent_lock import DEFAULT_ROOT, status
    from scripts.agent_sim_slots import require_sim_slot, sim_holders, sim_snapshot
    snapshot = lambda: sim_snapshot(DEFAULT_ROOT)
    plan = {'execution_bundle_id': env.BUNDLE_ID, 'workflow_id': env.WORKFLOW_ID,
            'workflow_version': env.WORKFLOW_VERSION, 'status': 'DRAFT_UNSEALED', 'execution_started': False,
            'runnable': bundle['runnable'], 'physical_ready': False, 'expected_source_sha': args.expected_source_sha,
            'check': env.CHECK, 'run_id': args.run_id, 'bundle_sha256': env.digest(bundle), 'caps': bundle['caps'],
            'measurement_sha256': bundle['measurement_sha256'], 'clearance_preflight': bundle['clearance_preflight'],
            'seed': args.seed, 'lock_mode': 'sim_slot' if args.sim_slot else 'exclusive', 'sim_slot': args.sim_slot,
            'host_start': snapshot()}
    if not args.execute:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0
    if not bundle['runnable']:
        raise ValueError('PREFLIGHT_CLEARANCE_REJECTED')
    check_source(args.expected_source_sha)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                          cwd=env.ROOT, text=True).strip()).parent
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary / 'outputs').resolve()):
        raise ValueError('raw output must be an absolute path under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10 * 1024 ** 3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=env.ROOT, text=True).strip()
    if args.sim_slot:
        require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner=args.lock_owner, branch=branch)
    else:
        held = status(DEFAULT_ROOT)
        if (not held or not held['pid_alive'] or held['owner'] != args.lock_owner
                or held['branch'] != branch or sim_holders(DEFAULT_ROOT)):
            raise ValueError('live owned host lock for this branch required')
    from sim.final_environment_gain_calibration_v101 import PhysicsBackend
    args.output.mkdir(parents=True)
    plan.update(execution_started=True, host_start=snapshot())
    write(args.output / 'plan.json', plan)
    result = run_case(bundle, args.output / bundle['run_id'], seed=args.seed, backend_factory=PhysicsBackend,
                      host_snapshot=snapshot)
    # The final freeze check includes untracked/dirty source and the bundle closure.
    try:
        check_source(args.expected_source_sha)
        unchanged = env.bundle(args.run_id) == bundle
    except (OSError, ValueError):
        unchanged = False
    complete = result['protocol_complete'] and unchanged
    write(args.output / 'result.json', {'status': 'COLLECTED_UNQUALIFIED' if complete else 'HOST_ERROR',
                                      'cases': [result], 'denominator': 1, 'source_unchanged': unchanged,
                                      'lock_mode': plan['lock_mode'], 'sim_slot': args.sim_slot,
                                      'host_start': plan['host_start'], 'host_end': snapshot(),
                                      'physical_success': None, 'research_result': False, 'model_calls': 0})
    return int(not complete)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
