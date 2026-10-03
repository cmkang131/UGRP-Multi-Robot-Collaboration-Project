"""Managed v93 student candidate. Plan-only until v92 measured calibration."""
from __future__ import annotations

import argparse
import errno
import json
from pathlib import Path
import shutil
import subprocess
import sys

from harness import zone_pair_highpose_contract as contract
from harness.zone_final_pair_binding import bind
from harness.zone_pair_highpose_runtime import Runtime
from scripts import run_final_pair_v3 as previous
from scripts.run_final_environment_checks import write, check_source


def run_case(bundle, out, *, seed, backend_factory, runtime_factory=Runtime,
             calibration=None, calibration_sha=None):
    # Check even a direct caller before creating output/backend/provider.
    contract.measured_calibration(calibration, calibration_sha, bundle['map_id'])
    expected = {**contract.bundle(bundle['map_id'], bundle['check']),
                'source_sha': bundle['source_sha'], 'case': bundle['case']}
    if (contract.base.digest(bundle) != contract.base.digest(expected)
            or bundle['case'] not in contract.cases(bundle['check'], bundle['map_id'])):
        raise ValueError('v93 bundle/case mismatch')
    run = bind(previous.run_case, contract=contract)
    return run(bundle, out, seed=seed, backend_factory=backend_factory,
               runtime_factory=runtime_factory, calibration=calibration, calibration_sha=calibration_sha)


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


def plan(args):
    cases = contract.cases(args.check, args.map_id)
    bundles = [{**contract.bundle(c['map_id'], args.check), 'case': c,
                'source_sha': args.expected_source_sha} for c in cases]
    blocked = []
    try:
        for c in cases:
            contract.measured_calibration(args.calibration, args.calibration_sha256, c['map_id'])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        blocked.append(str(exc))
    value = {'execution_bundle_id': contract.BUNDLE_ID, 'status': 'DRAFT_UNSEALED',
        'check': args.check, 'execution_started': False, 'cases': cases, 'denominator': len(cases),
        'runnable': not blocked, 'blocked_on': blocked, 'precondition': contract.PRECONDITION,
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
    shutil.copyfile(args.calibration, args.output/'measured_calibration.json')
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
    write(args.output/'result.json', {'status': 'HOST_ERROR' if failed else 'COLLECTED_UNQUALIFIED',
        'cases': results, 'unattempted': unattempted, 'denominator': len(admission['cases']),
        'source_unchanged': unchanged, 'physical_success': None, 'research_result': False})
    return int(failed)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
