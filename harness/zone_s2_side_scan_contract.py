"""Explicit s2v48 side-scan diagnostic admission; old v133 stays immutable."""
import copy
import json
from pathlib import Path
from harness.python_source_closure import source_closure
from scripts.run_s2_v133_reproduction import baseline,original_contract

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'experiments/2026-10-06-s2-realism/look-before-move-registration.json'
BUNDLE_ID='zone-s2-realism-v134'
VERSION='7.27.0'


def bundle(sha,*,side_scan='off'):
    if side_scan not in ('off','side_scan_v1'):raise ValueError('unknown side_scan')
    plan=json.loads(PLAN.read_text());b=copy.deepcopy(baseline())
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=VERSION,source_sha=sha,
        schema='ugrp.s2_realism_bundle.v134',mode='side_scan',stage_probe='side_scan',case_cap_s=45.,
        result_condition='S2_DEV_side_scan_diagnostic',physical_success=None,transport='solo',
        user_authorization='2026-10-08 s2v48 one 1054 side-scan before replay; 15 minute wall cap',
        admission='dev-pilot',registration_kind='s2-dev-side-scan',preregistered_run=False,
        dev_preregistration=dict(plan=str(PLAN.relative_to(ROOT)),seed=1054,runs=1,
            exception='user s2v48 authorizes diagnostic before replay; not a research cohort'))
    b['task']['seed']=1054
    b['options'].update(side_scan=side_scan,forward_scale='forward_scale_v1',likelihood_tempering='pr_likelihood_half_v1')
    table=Path(plan['calibration']['1054']['path'])
    if original_contract.old.hp.base.sha(table)!=plan['calibration']['1054']['sha256']:raise ValueError('fixed calibration changed')
    b['bias_calibration']=json.loads(table.read_text())
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['harness/zone_s2_side_scan_contract.py','scripts/run_s2_side_scan.py']))
    paths.update([str(PLAN.relative_to(ROOT)),'configs/simulation_workflows.d/s2_side_scan_v134.json'])
    b['source_sha256']={p:original_contract.old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256',None);b['bundle_sha256']=original_contract.old.hp.base.digest(b)
    return b


def require_execution(b):
    if b!=bundle(b['source_sha'],side_scan='side_scan_v1'):raise ValueError('exact side-scan preregistration required')
    from harness.idle_robot_contacts_contract import validate
    validate(b)
