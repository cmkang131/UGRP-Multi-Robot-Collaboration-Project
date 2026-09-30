"""Standard-management v84 DRAFT check runner; --execute is explicit.

P01 reset and unloaded calibration acquisition are executable. P03 chain
admission is refused until measured calibration AND a v3 pair adapter exist.
Never turn an environment/model registry entry into a chain success claim.
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

from harness import zone_final_environment as env

ROBOTS = ('r1', 'r2', 'r3')
RESET_CAP_S = 5.


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def check_source(expected):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=env.ROOT, text=True).strip()
    if expected != head:
        raise ValueError('expected source SHA differs from HEAD')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=env.ROOT, text=True).strip():
        raise ValueError('source is dirty; commit and freeze before SIM')
    return head


def run_case(bundle, out, *, seed, backend_factory):
    """The physics owner is injected; this entire schedule is fake-testable.

    eval_sample() writes privately and returns nothing to this scheduler. The
    calibration schedule is fixed before construction; no evaluation changes
    an action, a phase, a prior or an estimate.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'bundle.json', bundle)
    check = bundle['check']
    if check not in ('p01', 'calibration') or not bundle['runnable']:
        raise ValueError('check is not admitted for SIM')
    cap = float(bundle['caps']['per_case_sim_cap_s'])
    expected = 30. if check == 'p01' else 120.
    if cap != expected:
        raise ValueError('SIM cap differs from registered check')
    protocol = env.read(env.ROOT / 'configs/final_environment_measurement_v1.json')
    events = protocol['events'] if check == 'calibration' else []
    backend = None
    result = {'map_id': bundle['map_id'], 'check': check, 'status': 'HOST_ERROR',
              'physical_success': None, 'research_result': False, 'protocol_complete': False,
              'reset_sim_cap_s': RESET_CAP_S, 'check_sim_cap_s': cap,
              'reset_sim_s': None, 'check_sim_s': None, 'loadavg_start': list(os.getloadavg()),
              'model_calls': 0, 'student_control': False, 'failure': None}
    try:
        backend = backend_factory(bundle, out, seed=seed)
        result['reset_sim_s'] = backend.reset(RESET_CAP_S)
        if not 0 <= result['reset_sim_s'] <= RESET_CAP_S + 1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        start = backend.now
        backend.set_deadline(start + cap)
        # Initial samples are saved even if the first camera call fails.
        backend.eval_sample()
        backend.capture()
        event_i, next_frame = 0, .2 if check == 'calibration' else 5.
        steps = int(round(cap / .05))
        for i in range(steps):
            elapsed = i * .05
            while event_i < len(events) and events[event_i]['t'] <= elapsed + 1e-9:
                for action in events[event_i]['actions']:
                    backend.issue(protocol['robot_id'], action)
                event_i += 1
            backend.advance_to(start + (i + 1) * .05)
            backend.eval_sample()
            elapsed = (i + 1) * .05
            if elapsed >= next_frame - 1e-9:
                backend.capture()
                next_frame += .2 if check == 'calibration' else 5.
        if event_i != len(events):
            raise RuntimeError('measurement events exceed SIM cap')
        result.update(status='COLLECTED_UNQUALIFIED', protocol_complete=True,
                      check_sim_s=backend.now - start)
        if abs(result['check_sim_s'] - cap) > 1e-7:
            raise RuntimeError('SIM cap was not reached exactly')
    except Exception as error:
        result.update(status='HOST_ERROR', protocol_complete=False,
                      failure={'type': type(error).__name__, 'message': str(error),
                               'class': 'ENOSPC' if getattr(error, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'})
        if backend is not None:
            result['observed_sim_s'] = backend.now
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception as error:
                result.update(status='HOST_ERROR', protocol_complete=False,
                              cleanup_error={'type': type(error).__name__, 'message': str(error)})
        result['loadavg_end'] = list(os.getloadavg())
        write(out / 'result.json', result)
        write(out / 'artifacts.sha256.json', {str(p.relative_to(out)): env.sha(p)
                                            for p in sorted(out.rglob('*')) if p.is_file()
                                            and p.name != 'artifacts.sha256.json'})
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', choices=('p01', 'calibration', 'p03'), required=True)
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
    reg = env.registry()
    selected = [reg['checks']['p03']['map_id']] if args.check == 'p03' else list(reg['maps'])
    bundles = [env.bundle(mid, check=args.check) for mid in selected]
    plan = {'execution_bundle_id': env.BUNDLE_ID, 'status': 'DRAFT_UNSEALED',
            'execution_started': False, 'expected_source_sha': args.expected_source_sha,
            'check': args.check, 'seed': args.seed, 'caps': reg['checks'][args.check],
            'reset_per_case_sim_cap_s': RESET_CAP_S,
            'bundles': {b['map_id']: env.digest(b) for b in bundles},
            'runnable': all(b['runnable'] for b in bundles),
            'blocked_on': bundles[0]['blocked_on']}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    # All admissions precede output creation, physics import and worker spawn.
    check_source(args.expected_source_sha)
    if args.check == 'p03':
        for mid in selected:
            env.measured_calibration(args.calibration, args.calibration_sha256, mid)
        raise ValueError('FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED; existing host refuses v3 pair; see PHYSICS_HANDOFF.md')
    if not args.output.is_absolute():
        raise ValueError('raw output must be an absolute path under primary outputs')
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                          cwd=env.ROOT, text=True).strip()).parent
    if not args.output.resolve().is_relative_to((primary / 'outputs').resolve()):
        raise ValueError('raw output must be under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10 * 1024 ** 3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    from scripts.agent_lock import DEFAULT_ROOT, status
    held = status(DEFAULT_ROOT)
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=env.ROOT, text=True).strip()
    if not held or not held['pid_alive'] or held['owner'] != args.lock_owner or held['branch'] != branch:
        raise ValueError('live owned host lock for this branch required')
    from sim.final_environment_checks import PhysicsBackend
    args.output.mkdir(parents=True)
    write(args.output / 'plan.json', plan)
    results = []
    for bundle in bundles:
        results.append(run_case(bundle, args.output / bundle['map_id'], seed=args.seed,
                                backend_factory=PhysicsBackend))
        # A host error may leave graphics/physics unusable: preserve unattempted
        # cases in the denominator rather than constructing another world.
        if results[-1]['status'] == 'HOST_ERROR':
            break
    unattempted = [b['map_id'] for b in bundles[len(results):]]
    unchanged = all(env.bundle(b['map_id'], check=args.check) == b for b in bundles)
    write(args.output / 'result.json', {'status': 'COLLECTED_UNQUALIFIED' if unchanged and not unattempted
                                      and all(r['protocol_complete'] for r in results) else 'HOST_ERROR',
                                      'cases': results, 'unattempted': unattempted, 'denominator': 3,
                                      'source_unchanged': unchanged, 'physical_success': None})
    return int(bool(unattempted) or not unchanged or any(not r['protocol_complete'] for r in results))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
