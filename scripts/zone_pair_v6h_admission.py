"""Admission for the sealed 60+12 v6h chain plan; never creates a seal.

The DRAFT builder is only a preview. After coordinator promotion, compare the
entire sealed plan AND generated worker cases with current pinned inputs. The
old six-case dev runtime cannot consume these teacher-staged chain cases.
"""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import zone_pair_v6_contract as contract
from scripts.zone_pair_authorization import digest, registration_payload, validate_authorization


def builder():
    return importlib.import_module('experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h')


def plan_args(plan):
    """Exact driver options; auxiliary seed selection comes from the sealed runs."""
    from scripts.run_pair_stage_probes import parser
    op = plan['confirmatory_plan']['operation']
    args = parser().parse_args([])
    args.stage = [op['stage']]
    args.policies = [op['policy']]
    args.sources = op['sources']
    args.seeds = args.nominal_seeds = [plan['confirmatory_plan']['primary_seed']]
    args.env_placements = contract.ROOT / plan['placements']['path']
    for key in ('render_profile', 'chain_stop_leg', 'pf_track', 'contact_track', 'workers', 'omp_threads', 'case_timeout_s'):
        setattr(args, key, op[key])
    return args


def cases_for_plan(plan):
    """Convert all sealed placements/priors to the ACTUAL stage worker inputs."""
    from scripts.run_pair_stage_probes import envelope_cases
    args = plan_args(plan)
    cases = []
    for run in plan['runs']:
        args.seeds = args.nominal_seeds = [run['seed']]
        generated = envelope_cases('chain', args, run['pair_policy'], None, placements=[run['placement']])
        if len(generated) != 1:
            raise ValueError('sealed placement must produce exactly one case')
        case = generated[0]
        case.update(registration_run_id=run['id'], render_profile=args.render_profile,
                    chain_stop_leg=args.chain_stop_leg, pf_track=args.pf_track, contact_track=args.contact_track)
        cases.append(case)
    # JSON normalization matches saved seals/worker files (tuples in static route inputs).
    return json.loads(json.dumps(cases, allow_nan=False))


def validate_plan(plan):
    if contract.CURRENT_REVISION != 'v6h':
        raise ValueError('v6h is pending seal; CURRENT_REVISION has not been promoted')
    if plan.get('registration_revision') != 'v6h' or plan.get('sealed') is not True:
        raise ValueError('v6h requires a sealed confirmatory plan')
    validate_authorization(plan)
    if plan.get('status') not in ('DRAFT', 'REGISTERED'):
        raise ValueError('sealed v6h status must be DRAFT or REGISTERED')
    expected = builder().build()
    if digest(plan.get('v6_contract')) != digest(expected['v6_contract']):
        raise ValueError('sealed v6h source contract/hash mismatch')
    expected.update(sealed=True, status=plan['status'], runnable=plan['status'] == 'REGISTERED',
                    execution_authorization=plan.get('execution_authorization'),
                    registration_sha256=plan.get('registration_sha256'))
    if digest(plan) != digest(expected):
        raise ValueError('sealed v6h plan/config/placements/cases mismatch')
    return plan


def load_config(args):
    plan = validate_plan(json.loads(args.prereg.read_text()))
    if args.output.exists():
        raise ValueError('output must be new')
    run_id = getattr(args, 'run_id', None)
    case = next((c for c in plan['cases'] if c['registration_run_id'] == run_id), None)
    if run_id is not None and case is None:
        raise ValueError('run-id is not preregistered')
    if getattr(args, 'pair_policy', None) not in (None, 'b-v6h1'):
        raise ValueError('pair policy does not match sealed v6h plan')
    if args.execute:
        if plan['status'] != 'REGISTERED':
            raise ValueError('v6h DRAFT is prepare-only')
        if run_id is None:
            raise ValueError('registered execution requires one authorized --run-id')
        validate_authorization(plan, execute=True, expected_source_sha=args.expected_source_sha, run_id=run_id)
    return plan, copy.deepcopy(case)


def prepare_cases(args):
    plan, selected = load_config(args)
    expected = plan_args(plan)
    # Compare every parser-controlled worker option, including default values.
    # These are I/O/admission fields, not condition overrides.
    envelope = {'prereg', 'output', 'execute', 'run_id', 'expected_source_sha', 'lock_owner', 'worker_case', 'worker_out'}
    for key, value in vars(expected).items():
        if key in envelope:
            continue
        actual = getattr(args, key)
        if key == 'env_placements' and actual is not None:
            actual, value = actual.resolve(), value.resolve()
        if actual != value:
            raise ValueError(f'sealed v6h option mismatch: {key}')
    return plan, [selected] if selected is not None else copy.deepcopy(plan['cases'])


def authorize_execution(args, plan):
    """Use the existing per-run coordinator envelope/live GitHub/source checks."""
    from scripts import agent_lock
    from scripts.run_pair_stage_probes import primary_root, git
    from scripts.zone_pair_authorization import verify_github_authorization, verify_source
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to(primary_root() / 'outputs'):
        raise ValueError('physical raw output must be absolute under primary checkout outputs/')
    held = agent_lock.status(primary_root() / 'outputs/agent-locks')
    if (not held or not held['pid_alive'] or held['owner'] != args.lock_owner
            or held['branch'] != git('branch', '--show-current') or held['branch'] == 'main'):
        raise ValueError('live agent_lock matching owner and task branch required')
    raw = args.prereg.read_bytes()
    if json.loads(raw) != plan:
        raise ValueError('prereg changed during preparation')
    verify_source(contract.ROOT, args.prereg, plan, args.expected_source_sha)
    receipt = verify_github_authorization(plan, args.expected_source_sha, args.run_id)
    if args.prereg.read_bytes() != raw:
        raise ValueError('prereg changed during GitHub approval lookup')
    verify_source(contract.ROOT, args.prereg, plan, args.expected_source_sha)
    return {'prereg': str(args.prereg.resolve()), 'registration_sha256': plan['registration_sha256'],
            'run_id': args.run_id, 'expected_source_sha': args.expected_source_sha,
            'lock_owner': args.lock_owner, 'github_authorization': receipt}


def validate_worker_case(case, out):
    """Recheck sealed content and source BEFORE a worker imports MuJoCo."""
    receipt = case['registration']
    args = SimpleNamespace(prereg=Path(receipt['prereg']), output=Path(out), execute=True,
                           run_id=receipt['run_id'], expected_source_sha=receipt['expected_source_sha'],
                           lock_owner=receipt['lock_owner'])
    plan = validate_plan(json.loads(args.prereg.read_text()))
    frozen = next((c for c in plan['cases'] if c['registration_run_id'] == args.run_id), None)
    if (receipt['registration_sha256'] != plan['registration_sha256'] or
            digest({k: v for k, v in case.items() if k != 'registration'}) != digest(frozen)):
        raise ValueError('worker case differs from sealed v6h plan')
    if plan['status'] != 'REGISTERED':
        raise ValueError('v6h DRAFT is prepare-only')
    authorize_execution(args, plan)
