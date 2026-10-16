"""Explicit v135 solo DEV admission; frozen v133 source remains unchanged."""
import copy
import json
from pathlib import Path
from harness.python_source_closure import source_closure
from scripts.run_s2_v133_reproduction import baseline,original_contract

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'experiments/2026-10-06-s2-realism/look-before-move-full-registration.json'
BUNDLE_ID='zone-s2-realism-v135'
VERSION='7.28.0'

def bundle(sha,seed,*,look_before_move='off'):
    if look_before_move not in ('off','rgb_sweep_v1'):raise ValueError('unknown look_before_move')
    plan=json.loads(PLAN.read_text())
    if seed not in plan['seeds']:raise ValueError('unregistered seed')
    b=copy.deepcopy(baseline())
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=VERSION,source_sha=sha,
        schema='ugrp.s2_realism_bundle.v135',case_cap_s=plan['case_cap_s'],
        result_condition='S2_DEV_own_RGB_look_before_move',physical_success=None,
        dev_preregistration=dict(plan=str(PLAN.relative_to(ROOT)),seed=seed,
            user_authorization='2026-10-08 s2v48 same1054 and fresh1055 full DEV, own RGB only'))
    b['task']['seed']=seed
    b['options'].update(look_before_move=look_before_move,forward_scale='forward_scale_v1',likelihood_tempering='pr_likelihood_half_v1')
    table=Path(plan['calibrations'][str(seed)]['path'])
    if original_contract.old.hp.base.sha(table)!=plan['calibrations'][str(seed)]['sha256']:raise ValueError('fixed calibration changed')
    b['bias_calibration']=json.loads(table.read_text())
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['harness/zone_s2_look_before_move_contract.py','scripts/run_s2_look_before_move.py']))
    paths.update([str(PLAN.relative_to(ROOT)),'configs/simulation_workflows.d/s2_look_before_move_v135.json'])
    b['source_sha256']={p:original_contract.old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256',None);b['bundle_sha256']=original_contract.old.hp.base.digest(b)
    return b

def require_execution(b):
    if b!=bundle(b['source_sha'],b['task']['seed'],look_before_move='rgb_sweep_v1'):
        raise ValueError('exact registered solo DEV option required')
    from harness.idle_robot_contacts_contract import validate
    validate(b)
