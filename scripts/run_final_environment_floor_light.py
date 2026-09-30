"""Standard-management v87 floor_light_v1 DRAFT check runner; --execute is explicit.

P01 reset and unloaded calibration acquisition are executable. P03 chain
admission is refused until measured calibration AND a v3 pair adapter exist.
Never turn an environment/model registry entry into a chain success claim.
"""
from __future__ import annotations

import errno
import json
from pathlib import Path
import shutil
import subprocess
import sys

from harness import zone_final_environment_floor_light as env
from scripts.run_final_environment_checks import RESET_CAP_S, check_source, run_case, parser, write


def main(argv=None):
    args = parser().parse_args(argv)
    reg = env.registry()
    selected = [reg['checks']['p03']['map_id']] if args.check == 'p03' else list(reg['maps'])
    bundles = [env.bundle(mid, check=args.check) for mid in selected]
    plan = {'execution_bundle_id': env.BUNDLE_ID, 'status': 'DRAFT_UNSEALED',
            'render_profile': reg['render_profile'], 'workflow_version': reg['workflow_version'],
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
        if args.calibration is None or args.calibration_sha256 is None:
            raise ValueError('MEASURED_V3_CALIBRATION_REQUIRED; see PHYSICS_HANDOFF.md')
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
    from sim.final_environment_floor_light import PhysicsBackend
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
