"""One seed1051 S2 DEV: stiff look-ahead + adopted slip and recovery fix."""
import copy
from pathlib import Path
from harness import zone_s2_realism_contract_v129 as previous
from harness.python_source_closure import source_closure
from harness.zone_solo_cyan_look_ahead import validate
old,ROOT=previous.old,previous.ROOT
BUNDLE_ID='zone-s2-realism-v130'
WORKFLOW_VERSION='7.23.0'
TABLE='configs/calibration/s2_camera_look_ahead_v1.json'
STIFF='configs/calibration/s2_camera_stiff_target_v1.json'
PLAN='experiments/2026-10-06-s2-realism/registration-v130.json'


def bundle(sha,*,carry_pose='off',servo_stiffness='off',camera_pitch='off'):
    options=copy.deepcopy(previous.NEW_OPTIONS)
    value=previous.bundle(sha,seed=1051,pickup_slot='P1-2',stage_probe='place',**options)
    value.update(schema='ugrp.s2_realism_bundle.v130',execution_bundle_id=BUNDLE_ID,workflow_version=WORKFLOW_VERSION,
        result_condition='S2_DEV_stiff_look_ahead_seed1051',user_decision='2026-10-08 look ahead single box; controlled load-wall ablation',
        motion_calibration='unchanged v122; no load compensation fitted from ablation',pool_with_previous_s2=False)
    value['options'].update(carry_pose=carry_pose,servo_stiffness=servo_stiffness,camera_pitch=camera_pitch)
    value['look_ahead_calibration']=old.hp.base.read(ROOT/TABLE)
    value['stiff_camera_table']=old.hp.base.read(ROOT/STIFF)
    paths=set(value['source_sha256'])|set(source_closure(ROOT,['harness/zone_s2_realism_contract_v130.py','scripts/run_s2_look_ahead.py']))
    paths.update([TABLE,STIFF,PLAN,'configs/simulation_workflows.d/s2_realism_v130.json'])
    value['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    value.pop('bundle_sha256',None);value['bundle_sha256']=old.hp.base.digest(value)
    return value


def require_execution(value):
    from harness.idle_robot_contacts_contract import validate as validate_idle
    validate_idle(value)
    plan=old.hp.base.read(ROOT/PLAN)
    if value['execution_bundle_id']!=BUNDLE_ID or value['task']!=plan['task'] or value['stage_probe']!='place':raise ValueError('one registered S2 DEV only')
    if value['options']!=plan['options']:raise ValueError('explicit registered look-ahead options required')
    validate(value['look_ahead_calibration'])
    if old.hp.base.sha(ROOT/TABLE)!=plan['look_ahead_table_sha256']:raise ValueError('camera table changed')
    if value['stiff_camera_table']!=old.hp.base.read(ROOT/STIFF):raise ValueError('stiff camera table changed')
    for path,digest in value['source_sha256'].items():
        if old.hp.base.sha(ROOT/path)!=digest:raise ValueError('source changed: '+path)
