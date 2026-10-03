"""Managed DRAFT v99: one arm of the pair LLM viability test (Refs #219).

``--condition rule | no_comm | peer_nl`` is C-rule / C-llm-nocomm / C-llm-nl. Without ``--execute`` this only
prints a plan. This PR ships the STUB model path only: ``--live`` is refused here, and a real model call needs
the coordinator's separate approval and a live driver wired in a later change. Physics is lazy, requires
committed source, an owned SIM slot and 10 GiB free before it starts, and writes raw output under the primary
checkout's ``outputs/`` by absolute path.
"""
from __future__ import annotations

import argparse
import errno
import json
import shutil
import subprocess
import sys
from pathlib import Path

from harness import pair_llm_contract as contract
from scripts.run_final_environment_checks import check_source, write


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--condition', choices=contract.CONDITIONS, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--cap-s', type=float, default=contract.CAP_S,
                   help=f'per-case SIM cap (registered {contract.CAP_S:g}; a stub smoke uses <= {contract.SMOKE_MAX_S:g})')
    p.add_argument('--seed', type=int, default=911)
    p.add_argument('--live', action='store_true', help='refused in this PR: no real model call without approval')
    p.add_argument('--stub-policy', choices=('cooperative',), default='cooperative')
    p.add_argument('--synthetic-plumbing-calibration', action='store_true',
                   help='fabricated, plumbing-only calibration (the controller is blind; no carry result)')
    p.add_argument('--calibration', type=Path)
    p.add_argument('--calibration-sha256')
    p.add_argument('--sim-slot', help='SIM slot name (scripts.agent_sim_slots) held by --lock-owner')
    p.add_argument('--lock-owner', choices=('codex', 'claude', 'kiro'))
    return p


def primary_checkout():
    return Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                        cwd=contract.ROOT, text=True).strip()).parent


def main(argv=None):
    args = parser().parse_args(argv)
    if args.live:
        raise ValueError('live model calls are disabled in this change; the coordinator approves the first live '
                         'smoke separately')
    if not 0 < args.cap_s <= contract.CAP_S:
        raise ValueError(f'--cap-s must be in (0, {contract.CAP_S:g}]')
    if args.synthetic_plumbing_calibration == bool(args.calibration):
        raise ValueError('give exactly one of --synthetic-plumbing-calibration or --calibration')
    plan_bundle = contract.bundle(args.condition, kind='stub', source_sha=args.expected_source_sha,
                                  synthetic_calibration=args.synthetic_plumbing_calibration)
    plan = {'execution_bundle_id': contract.BUNDLE_ID, 'workflow_version': contract.WORKFLOW_VERSION,
            'status': 'DRAFT_UNSEALED', 'condition': args.condition, 'arm': contract.ARMS[args.condition],
            'execution_started': False, 'model_kind': 'stub' if args.condition != 'rule' else 'none',
            'cap_s': args.cap_s, 'seed': args.seed, 'source_sha': args.expected_source_sha,
            'bundle_sha256': contract.base.digest(plan_bundle),
            'synthetic_plumbing_calibration': args.synthetic_plumbing_calibration, 'research_result': False,
            'physical_success': None}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    from harness import zone_final_pair_contract as skill_layer
    if args.calibration:
        skill_layer.measured_calibration(args.calibration, args.calibration_sha256, plan_bundle['map_id'])
    check_source(args.expected_source_sha)
    primary = primary_checkout()
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary / 'outputs').resolve()):
        raise ValueError('raw output must be absolute under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10 * 1024 ** 3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    if not args.sim_slot or not args.lock_owner:
        raise ValueError('--sim-slot and --lock-owner are required to execute')
    from scripts.agent_lock import DEFAULT_ROOT
    from scripts.agent_sim_slots import require_sim_slot
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    snapshot = require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner=args.lock_owner, branch=branch)
    from harness.pair_llm_case import run_pair_case, stub_adapter
    from harness.pair_llm_stub import cooperative_model
    from sim.final_pair_v3 import PhysicsBackend
    args.output.mkdir(parents=True)
    calibration = None
    provider_factory = None
    if args.synthetic_plumbing_calibration:
        from harness import pair_llm_plumbing as plumbing
        calibration = plumbing.synthetic_calibration(args.output / 'calibration' / (plumbing.LABEL + '.json'))
        provider_factory = plumbing.blind_provider_factory
    else:
        calibration = {'path': args.calibration, 'sha256': args.calibration_sha256}
    bundle = contract.bundle(args.condition, kind='stub', calibration=calibration,
                             synthetic_calibration=args.synthetic_plumbing_calibration,
                             source_sha=args.expected_source_sha)
    write(args.output / 'plan.json', {**plan, 'bundle_sha256': contract.base.digest(bundle),
                                      'sim_slot': args.sim_slot, 'host_snapshot': snapshot})
    model = cooperative_model()
    result = run_pair_case(
        bundle, args.output / args.condition, condition=args.condition, seed=args.seed,
        backend_factory=PhysicsBackend, calibration=calibration['path'], calibration_sha=calibration['sha256'],
        provider_factory=provider_factory, cap_s=args.cap_s, kind='stub',
        adapter_factory=(lambda out: stub_adapter(model, out / 'llm' / 'ledger')) if args.condition != 'rule' else None,
        source_sha=args.expected_source_sha)
    write(args.output / 'result.json', {'status': result['status'], 'condition': args.condition,
                                        'case': result['metrics'], 'research_result': False,
                                        'physical_success': None})
    return int(result['status'] == 'HOST_ERROR')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
