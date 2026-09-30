"""Floor-light workflow successor: opt-in calibration-motion-v2, no student."""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from harness import final_environment_measurement_v2 as env
from scripts.run_final_environment_checks import check_source, write


def run_case(bundle, out, *, seed, backend_factory):
    plan = bundle['measurement']
    env.validate(plan)
    if bundle['execution_bundle_id'] != env.BUNDLE_ID or bundle['check'] != env.CHECK:
        raise ValueError('wrong measurement bundle')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'bundle.json', bundle)
    backend = None
    result = {'status': 'HOST_ERROR', 'protocol_complete': False, 'physical_success': None,
              'research_result': False, 'student_control': False, 'model_calls': 0,
              'map_id': plan['map_id'], 'robot_id': 'r1', 'check': env.CHECK,
              'loadavg_start': list(os.getloadavg()), 'reset_sim_s': None, 'check_sim_s': None,
              'total_including_reset_cap_s': plan['total_including_reset_cap_s']}
    try:
        backend = backend_factory(bundle, out, seed=seed)
        reset = backend.reset(plan['reset_cap_s'])
        result['reset_sim_s'] = reset
        if not 0 <= reset <= plan['reset_cap_s'] or abs(backend.now - reset) > 1e-7:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED_OR_INVALID_CLOCK')
        start = backend.now
        backend.set_deadline(start + plan['sim_cap_s'])
        # Evaluation returns no observations. The only feedback is a private
        # physics-owner abort, which terminates the entire diagnostic collection.
        backend.eval_sample()
        backend.capture()
        quantum = plan['control_period_s']
        next_frame = plan['camera_period_s']
        for i in range(round(plan['sim_cap_s'] / quantum)):
            backend.issue('r1', env.action_at(plan, i))
            backend.advance_to(start + (i + 1) * quantum)
            backend.eval_sample()
            elapsed = backend.now - start
            if abs(elapsed - (i + 1) * quantum) > 1e-7:
                raise RuntimeError('INEXACT_SAMPLE_CLOCK')
            if elapsed >= next_frame - 1e-8:
                backend.capture()
                next_frame += plan['camera_period_s']
        result['check_sim_s'] = backend.now - start
        if (abs(result['check_sim_s'] - plan['sim_cap_s']) > 1e-7
                or backend.now > plan['total_including_reset_cap_s'] + 1e-7):
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
        write(out / 'result.json', result)
        write(out / 'artifacts.sha256.json', {str(p.relative_to(out)): env.sha(p)
                                            for p in sorted(out.rglob('*')) if p.is_file()
                                            and p.name != 'artifacts.sha256.json'})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', required=True, choices=(env.CHECK, 'p01', 'calibration', 'p03'))
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--lock-owner', choices=('claude', 'codex', 'kiro'))
    parser.add_argument('--seed', type=int, default=911)
    parser.add_argument('--calibration', type=Path)
    parser.add_argument('--calibration-sha256')
    args = parser.parse_args(argv)
    if args.check != env.CHECK:
        # Historical checks keep their v87 bundle, schedule and admissions.
        from scripts.run_final_environment_floor_light import main as legacy_main
        return legacy_main(argv)
    bundle = env.bundle()
    plan = {'execution_bundle_id': env.BUNDLE_ID, 'workflow_id': env.WORKFLOW_ID,
            'workflow_version': env.WORKFLOW_VERSION, 'status': 'DRAFT_UNSEALED',
            'execution_started': False, 'runnable': True, 'physical_ready': False,
            'expected_source_sha': args.expected_source_sha, 'check': env.CHECK,
            'bundle_sha256': env.digest(bundle), 'caps': bundle['caps'],
            'measurement_sha256': bundle['measurement_sha256'],
            'clearance_preflight': bundle['clearance_preflight'], 'seed': args.seed}
    if not args.execute:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0
    check_source(args.expected_source_sha)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                          cwd=env.ROOT, text=True).strip()).parent
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary / 'outputs').resolve()):
        raise ValueError('raw output must be an absolute path under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10 * 1024 ** 3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    from scripts.agent_lock import DEFAULT_ROOT, status
    held = status(DEFAULT_ROOT)
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=env.ROOT, text=True).strip()
    if not held or not held['pid_alive'] or held['owner'] != args.lock_owner or held['branch'] != branch:
        raise ValueError('live owned host lock for this branch required')
    from sim.final_environment_measurement_v2 import PhysicsBackend
    args.output.mkdir(parents=True)
    write(args.output / 'plan.json', plan)
    result = run_case(bundle, args.output / env.MAP_ID, seed=args.seed, backend_factory=PhysicsBackend)
    # Include untracked/dirty source as well as the bundle closure in the final
    # freeze check. A changed source or missing file cannot become completion.
    try:
        check_source(args.expected_source_sha)
        unchanged = env.bundle() == bundle
    except (OSError, ValueError):
        unchanged = False
    complete = result['protocol_complete'] and unchanged
    write(args.output / 'result.json', {'status': 'COLLECTED_UNQUALIFIED' if complete else 'HOST_ERROR',
                                      'cases': [result], 'denominator': 1, 'source_unchanged': unchanged,
                                      'physical_success': None, 'model_calls': 0})
    return int(not complete)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
