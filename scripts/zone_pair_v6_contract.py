"""Prepare-only v6 registration, separate from immutable v5h execution records."""
import copy
import hashlib
import json
from pathlib import Path

from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID, POLICIES

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT/'experiments/2026-09-28-zone-pair-v6/prereg_v6.json'
V5H = ROOT/'experiments/2026-09-27-zone-pair-dev/prereg_v5h.json'


def contract():
    from scripts.zone_pair_grasp_contract import SOURCE_PATHS
    from scripts.zone_pair_dev_contract import scene_contract
    paths = (*SOURCE_PATHS,*scene_contract()['source_sha256'],
             'harness/zone_study_integration.py','harness/zone_pair_v6_policy.py','harness/zone_pair_relative.py',
             'harness/zone_pair_global.py','harness/owncam_recovery_v6.py',
             'harness/owncam_observability_v6.py','scripts/zone_pair_v6_contract.py')
    return {'execution_bundle_id':EXECUTION_BUNDLE_ID,'policy_flags':{
        k:vars(v) for k,v in POLICIES.items()},
        'qualification':'offline development; uncalibrated bounds; no physical inheritance',
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}


def load_config(args):
    p=json.loads(args.prereg.read_text());old=json.loads(V5H.read_text())
    if args.execute:
        raise ValueError('v6 DRAFT is prepare-only: execution source and approval are null')
    if (p.get('registration_version')!=6 or p.get('status')!='DRAFT'
            or p.get('execution_source_sha') is not None or p.get('execution_authorization') is not None
            or p.get('approval') is not None or p.get('runnable') is not False):
        raise ValueError('v6 draft contract changed')
    for key in ('schema','labels','research_result','environment','inputs','criteria','planned_setdown',
                'limits','safety_coverage','timing','stage_rules','contact_profile_contract'):
        if p.get(key)!=old[key]:
            raise ValueError(f'v6 comparison must preserve v5h {key}')
    if p.get('v6_contract')!=contract():
        raise ValueError('v6 source contract/hash mismatch')
    from scripts.zone_pair_dev_contract import scene_contract
    if p.get('scene_contract')!=scene_contract():
        raise ValueError('v6 scene contract/hash mismatch')
    if ('grasp_contract' in p or p.get('baseline_registration')!={
            'path':str(V5H.relative_to(ROOT)), 'sha256':hashlib.sha256(V5H.read_bytes()).hexdigest()}):
        raise ValueError('v6 must reference the frozen v5h baseline, not inherit its source contract')
    rows=p['runs']
    if len(rows)!=6 or len({r['id'] for r in rows})!=6 or len({r['seed'] for r in rows})!=2:
        raise ValueError('v6 requires two matched seeds times three conditions')
    for seed in {r['seed'] for r in rows}:
        group=[r for r in rows if r['seed']==seed]
        if {r['pair_policy'] for r in group}!=set(POLICIES):
            raise ValueError('v6 ablation missing')
        for key in ('setup_beam_xyyaw','coarse_order_sheet','intervention'):
            if any(r[key]!=group[0][key] for r in group):
                raise ValueError('v6 matched seed configuration differs')
    case=next((r for r in rows if r['id']==args.run_id),None)
    if case is None:
        raise ValueError('run-id is not preregistered')
    if getattr(args,'pair_policy',None) not in (None,case['pair_policy']):
        raise ValueError('pair policy does not match registered case')
    if args.output.exists():
        raise ValueError('output must be new')
    return p,copy.deepcopy(case)
