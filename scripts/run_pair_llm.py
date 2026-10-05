"""Managed DRAFT v100: one arm of the pair LLM viability test (Refs #219).

``--condition rule | no_comm | peer_nl`` is C-rule / C-llm-nocomm / C-llm-nl. Without ``--execute`` this only
prints a plan. The default model path is the STUB (plumbing only). ``--live`` sends real requests through the
study's own live driver (``harness.pair_llm_live``: ``MainStudySendLedger``, the audited local proxy checked
read-only, a durable token budget ledger) and requires an LLM condition, a case cap of at
most 900 SIM s, an explicit running proxy PID, budget ledger, cohort id and cohort token cap. A 429 / quota
answer stops the run as ``RATE_LIMIT``; nothing retries it. Physics is lazy, requires committed source, an owned
SIM slot and 10 GiB free before it starts, and writes raw output under the primary checkout's ``outputs/`` by
absolute path.
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
    p.add_argument('--live', action='store_true',
                   help='real model calls through the study live driver (LLM condition, cap <= 900 SIM s)')
    p.add_argument('--proxy-pid', type=int, help='PID of the already running local subscription proxy (read-only check)')
    p.add_argument('--budget-db', type=Path, help='absolute path of the main-study usage ledger (SQLite)')
    p.add_argument('--create-budget', action='store_true', help='create --budget-db (never created implicitly)')
    p.add_argument('--cohort-id')
    p.add_argument('--cohort-token-cap', type=int, help='explicit cap on charged provider tokens of the cohort')
    p.add_argument('--peer-token-measurements', type=Path,
                   help='JSON pairs of archived no_comm/peer_nl requests; recounted before peer_nl admission')
    p.add_argument('--unknown-usage-charge-tokens', type=int, default=12000,
                   help='tokens charged against the cap for a request whose usage is unknown')
    p.add_argument('--stub-policy', choices=('cooperative',), default='cooperative')
    p.add_argument('--synthetic-plumbing-calibration', action='store_true',
                   help='fabricated, plumbing-only calibration (the controller is blind; no carry result)')
    p.add_argument('--dev-single-arm', action='store_true',
                   help='dev-pilot no_comm only: run one LLM arm without the rule-first cohort order')
    p.add_argument('--admission', choices=('measured-sim', 'dev-pilot'), default='measured-sim',
                   help='dev-pilot: #363 exact registered calibration; FUNCTIONAL_DEV, never promotable')
    p.add_argument('--calibration', type=Path)
    p.add_argument('--calibration-sha256')
    p.add_argument('--sim-slot', help='SIM slot name (scripts.agent_sim_slots) held by --lock-owner')
    p.add_argument('--lock-owner', choices=('codex', 'claude', 'kiro'))
    return p


def check_live_args(args) -> None:
    """Every refusal of a live run that needs no file system or network."""
    from harness.pair_llm_live import LIVE_MAX_CAP_S
    if args.condition == 'rule':
        raise ValueError('--live needs an LLM condition (no_comm or peer_nl); the rule arm makes no model call')
    if not 0 < args.cap_s <= LIVE_MAX_CAP_S:
        raise ValueError(f'a live case is capped at {LIVE_MAX_CAP_S:g} SIM s (a longer one is a separate decision)')
    if not args.execute:
        return
    missing = [flag for flag, value in (('--proxy-pid', args.proxy_pid), ('--budget-db', args.budget_db),
                                        ('--cohort-id', args.cohort_id),
                                        ('--cohort-token-cap', args.cohort_token_cap)) if value is None]
    if missing:
        raise ValueError(f'--live --execute needs {", ".join(missing)}')
    if args.cohort_token_cap < 1 or args.unknown_usage_charge_tokens < 0:
        raise ValueError('--cohort-token-cap must be a positive int and --unknown-usage-charge-tokens >= 0')
    from harness.pair_llm_admission import check_cap
    check_cap(args.cohort_token_cap)
    if not args.budget_db.is_absolute():
        raise ValueError('--budget-db must be an absolute path under the primary checkout outputs/')


def primary_checkout():
    return Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                        cwd=contract.ROOT, text=True).strip()).parent


def main(argv=None):
    args = parser().parse_args(argv)
    from sim.final_pair_highpose_clock import record as host_clock_record
    if args.live:
        check_live_args(args)
    elif args.budget_db is not None:
        from harness.pair_llm_admission import check_cap
        check_cap(args.cohort_token_cap)
        if args.condition != "rule" or not args.cohort_id or not args.budget_db.is_absolute():
            raise ValueError("cohort rule needs --condition rule, --cohort-id and an absolute --budget-db")
    if not 0 < args.cap_s <= contract.CAP_S:
        raise ValueError(f'--cap-s must be in (0, {contract.CAP_S:g}]')
    if args.synthetic_plumbing_calibration == bool(args.calibration):
        raise ValueError('give exactly one of --synthetic-plumbing-calibration or --calibration')
    mode = contract.high_skill.DEV_PILOT if args.admission == 'dev-pilot' else contract.high_skill.MEASURED_SIM
    if mode == contract.high_skill.DEV_PILOT:
        from harness.zone_pair_highpose_starts import require_dev_seed
        require_dev_seed(args.seed)
    kind = 'live' if args.live else 'stub'
    plan_bundle = contract.bundle(args.condition, kind=kind, source_sha=args.expected_source_sha,
                                  synthetic_calibration=args.synthetic_plumbing_calibration, admission_mode=mode)
    plan = {'execution_bundle_id': contract.BUNDLE_ID, 'workflow_version': contract.WORKFLOW_VERSION,
            'status': 'DRAFT_UNSEALED', 'condition': args.condition, 'arm': contract.ARMS[args.condition],
            **contract.admission_record(mode, args.synthetic_plumbing_calibration), **contract.physics_profile(contract.physics_bundle(admission_mode=mode)),
            'execution_started': False,
            'host_clock': host_clock_record(), 'model_kind': kind if args.condition != 'rule' else 'none',
            'cap_s': args.cap_s, 'seed': args.seed, 'source_sha': args.expected_source_sha,
            'bundle_sha256': contract.base.digest(plan_bundle),
            'synthetic_plumbing_calibration': args.synthetic_plumbing_calibration, 'research_result': False,
            'physical_success': None}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    from harness import zone_pair_highpose_contract as skill_layer
    if args.calibration:
        skill_layer.calibration_for(mode, args.calibration, args.calibration_sha256, plan_bundle['map_id'])
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
    from sim.final_pair_highpose_clock import PhysicsBackend
    if args.live or args.budget_db is not None:
        budget_path = args.budget_db.resolve()
        if not budget_path.is_relative_to((primary / 'outputs').resolve()):
            raise ValueError('--budget-db must be under the primary checkout outputs/')
        if args.create_budget == budget_path.exists():
            raise ValueError('--create-budget must be given exactly when the budget ledger does not exist yet')
    args.output.mkdir(parents=True)
    calibration = None
    provider_factory = None
    if args.synthetic_plumbing_calibration:
        from harness import pair_llm_plumbing as plumbing
        calibration = plumbing.synthetic_calibration(args.output / 'calibration' / (plumbing.LABEL + '.json'))
        provider_factory = plumbing.blind_provider_factory
    else:
        calibration = {'path': args.calibration, 'sha256': args.calibration_sha256}
    bundle = contract.bundle(args.condition, kind=kind, calibration=calibration,
                             synthetic_calibration=args.synthetic_plumbing_calibration,
                             source_sha=args.expected_source_sha, admission_mode=mode)
    write(args.output / 'plan.json', {**plan, 'bundle_sha256': contract.base.digest(bundle),
                                      'sim_slot': args.sim_slot, 'host_snapshot': snapshot})
    if args.live:
        return run_live(args, plan, calibration, provider_factory, primary, budget_path)
    budget = None
    if args.budget_db is not None:
        if args.condition != 'rule':
            raise ValueError('only rule or --live cases belong to a measured cohort')
        from harness import pair_llm_admission as admission
        budget = cohort_budget(args, budget_path)
        admitted = admission.begin_case(budget, args.cohort_id, condition='rule', seed=args.seed,
                                        source_sha=args.expected_source_sha)
        write(args.output / 'admission.json', admitted)
    model = cooperative_model()
    result = run_pair_case(
        bundle, args.output / args.condition, condition=args.condition, seed=args.seed,
        backend_factory=PhysicsBackend, calibration=calibration['path'], calibration_sha=calibration['sha256'],
        provider_factory=provider_factory, cap_s=args.cap_s, kind='stub',
        adapter_factory=(lambda out: stub_adapter(model, out / 'llm' / 'ledger')) if args.condition != 'rule' else None,
        source_sha=args.expected_source_sha)
    if budget is not None:
        completion = admission.finish_case(budget, args.cohort_id, condition='rule', result=result)
        write(args.output / 'admission_completion.json', completion)
    write(args.output / 'result.json', {'status': result['status'], 'condition': args.condition,
                                        **contract.admission_record(mode, args.synthetic_plumbing_calibration), **contract.physics_profile(
                                            contract.physics_bundle(admission_mode=mode)),
                                        'case': result['metrics'], 'host_clock': result['host_clock'], 'research_result': False,
                                        'physical_success': None})
    return int(result['status'] == 'HOST_ERROR')


def cohort_budget(args, budget_path):
    from harness.pair_llm_admission import check_cap
    from harness.zone_main_budget import MainStudyBudget
    check_cap(args.cohort_token_cap)
    budget = MainStudyBudget.create(budget_path) if args.create_budget else MainStudyBudget(budget_path)
    registry_sha = contract.base.sha(contract.ROOT / contract.REGISTRY)
    budget.register_cohort(args.cohort_id, token_cap=args.cohort_token_cap,
                           unknown_usage_charge_tokens=args.unknown_usage_charge_tokens, prereg_sha256=registry_sha,
                           source={'code_sha': args.expected_source_sha, 'execution_bundle_id': contract.BUNDLE_ID,
                                   'note': 'live smoke of the pair LLM layer; no preregistration'})
    return budget


def run_live(args, plan, calibration, provider_factory, primary, budget_path) -> int:
    """One admitted live case, then the study's retry rule around that case."""
    from harness import pair_llm_live as live
    from sim.final_pair_highpose_clock import PhysicsBackend
    budget = cohort_budget(args, budget_path)
    measurement = (json.loads(args.peer_token_measurements.read_text())
                   if args.peer_token_measurements is not None else None)
    profile = contract.driver_profile()
    record, attempts = live.run_pair_live(
        args.output, condition=args.condition, seed=args.seed, cap_s=args.cap_s, profile=profile, budget=budget,
        cohort_id=args.cohort_id, backend_factory=PhysicsBackend, calibration=calibration['path'],
        calibration_sha=calibration['sha256'], provider_factory=provider_factory,
        synthetic_calibration=args.synthetic_plumbing_calibration, source_sha=args.expected_source_sha,
        proxy_pid=args.proxy_pid, peer_measurement=measurement, admission_mode=plan['admission_mode'],
        dev_single_arm=args.dev_single_arm)
    write(args.output / 'result.json', {
        'status': record['status'], 'condition': args.condition, 'failure': record.get('failure'),
        'failure_class': record.get('failure_class'), 'attempts': attempts, 'case': record['metrics'],
        'host_clock': record['host_clock'], **contract.admission_record(plan['admission_mode'], args.synthetic_plumbing_calibration),
        **contract.physics_profile(contract.physics_bundle(admission_mode=plan['admission_mode'])),
        'cohort_usage': budget.usage(args.cohort_id), 'research_result': False, 'physical_success': None,
        'note': 'live smoke: plumbing and connectivity only, not a carry or model-performance result'})
    return int(record['status'] == 'HOST_ERROR' or record.get('failure_class') is not None)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
