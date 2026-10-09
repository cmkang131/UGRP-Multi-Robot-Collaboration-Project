"""v137 fixed v136 settings with default-off staging/final approach separation."""
import copy,json
from pathlib import Path
from harness import zone_s2_goal_heading_contract as old
from harness.python_source_closure import source_closure
ROOT=old.ROOT
PLAN=ROOT/'experiments/2026-10-06-s2-realism/staged-approach-registration.json'
BUNDLE_ID='zone-s2-realism-v137'
VERSION='7.30.0'

def bundle(sha,seed,*,look_before_move='off',final_approach='off',proofs=None):
    plan=json.loads(PLAN.read_text())
    if seed not in [*plan['seeds'],plan['regression_seed']]:raise ValueError('unregistered seed')
    if final_approach not in ('off','staging_rgb_monitor_v1'):raise ValueError('unknown final_approach')
    b=copy.deepcopy(old.bundle(sha,seed,look_before_move=look_before_move))
    b['options']['final_approach']=final_approach
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=VERSION,schema='ugrp.s2_realism_bundle.v137',
        result_condition='S2_DEV_staged_final_approach',goal_heading_bugfix='nav2_stateful_v1',
        dev_preregistration=dict(plan=str(PLAN.relative_to(ROOT)),seed=seed,
            user_authorization='2026-10-08 s2v50 same1054/1055, conditional1053'))
    b['task']['seed']=seed
    table=Path(plan['calibrations'][str(seed)]['path'])
    if old.old.original_contract.old.hp.base.sha(table)!=plan['calibrations'][str(seed)]['sha256']:raise ValueError('calibration changed')
    b['bias_calibration']=json.loads(table.read_text());b['regression_proofs']=proofs
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['harness/zone_s2_staged_approach_contract.py','scripts/run_s2_staged_approach.py']))
    paths.update([str(PLAN.relative_to(ROOT)),'configs/simulation_workflows.d/s2_staged_approach_v137.json'])
    b['source_sha256']={p:old.old.original_contract.old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256');b['bundle_sha256']=old.old.original_contract.old.hp.base.digest(b)
    return b

def require_execution(b):
    if b!=bundle(b['source_sha'],b['task']['seed'],look_before_move='rgb_sweep_v1',final_approach='staging_rgb_monitor_v1',proofs=b['regression_proofs']):
        raise ValueError('exact registered option required')
    from harness.idle_robot_contacts_contract import validate
    validate(b)
    if b['task']['seed']==json.loads(PLAN.read_text())['regression_seed']:
        proof=b['regression_proofs'] or []
        if len(proof)!=2:raise ValueError('two successful v137 DEV proofs required')
        seeds=[]
        for p in proof:
            raw=Path(p['path']);r=json.loads(raw.read_text());sha=old.old.original_contract.old.hp.base.sha(raw)
            if sha!=p['sha256'] or r['source_sha']!=b['source_sha']:raise ValueError('proof source mismatch')
            if not all(r['evaluation'].get(k) for k in ('success','lifted','inside','stable')) or r['peer_contact_points'] or r['look']['unconfirmed_lateral_issued']:
                raise ValueError('regression requires two successful contact-free runs')
            seeds.append(r['seed'])
        if sorted(seeds)!=[1054,1055]:raise ValueError('wrong proof seeds')
