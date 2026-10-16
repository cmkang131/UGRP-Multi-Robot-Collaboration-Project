"""s2v39 sequential start/full DEV admissions, no research pooling."""
import copy
from pathlib import Path
from harness import zone_s2_realism_contract_v131 as previous
from harness.python_source_closure import source_closure

ROOT=previous.ROOT;old=previous.old
PLAN='experiments/2026-10-06-s2-realism/landmarks-physical-registration.json'
IDS={'start':'zone-s2-realism-v132','full':'zone-s2-realism-v133'}
VERSIONS={'start':'7.25.0','full':'7.26.0'}


def bundle(sha,mode,*,sensor_landmarks='off',start_proof=None):
    if mode not in IDS:raise ValueError('start or full required')
    if sensor_landmarks not in ('off','floor_zones_doors_v1'):raise ValueError('unknown sensor_landmarks')
    plan=old.hp.base.read(ROOT/PLAN)
    b=previous.bundle(sha)
    if mode=='start':
        raw=Path(plan['start_template']['path'])
        if old.hp.base.sha(raw)!=plan['start_template']['sha256']:raise ValueError('start template changed')
        plant=old.hp.base.read(raw)
        for k in ('task','options','motion_model','pulse_calibration','extrinsic_calibration','floor_appearance'):
            b[k]=copy.deepcopy(plant[k])
    b['options']=copy.deepcopy(plan['options'][mode]);b['options']['sensor_landmarks']=sensor_landmarks
    b.update(schema='ugrp.s2_realism_bundle.v'+IDS[mode].rsplit('v',1)[1],execution_bundle_id=IDS[mode],workflow_version=VERSIONS[mode],
        source_sha=sha,mode=mode,stage_probe='start' if mode=='start' else 'place',
        case_cap_s=30. if mode=='start' else b['case_cap_s'],start_proof=start_proof,
        result_condition='S2_DEV_landmarks_'+mode,transport='solo',research_result=False,pool_with_previous_s2=False)
    if mode=='start':
        b.update(preregistered_run=True,registration_kind='s2-dev-start',
            user_authorization='2026-10-08-s2-landmark-start')
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['harness/zone_s2_landmarks_contract.py','scripts/run_s2_landmarks_dev.py']))
    paths.update([PLAN,'configs/simulation_workflows.d/s2_landmarks_v132_v133.json',
        'experiments/2026-10-06-s2-realism/landmarks-result.json','experiments/2026-10-06-s2-realism/landmarks-criteria.json'])
    b['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256',None);b['bundle_sha256']=old.hp.base.digest(b)
    return b


def require_execution(b):
    from harness.idle_robot_contacts_contract import validate
    validate(b);mode=b['mode'];plan=old.hp.base.read(ROOT/PLAN)
    if b['execution_bundle_id']!=IDS[mode] or b['options']!=plan['options'][mode]:raise ValueError('exact registered landmark options required')
    if b['task']['seed']!=({'start':1052,'full':1051}[mode]) or b['task']['pickup_slot']!='P1-2':raise ValueError('registered seed/slot only')
    replay=old.hp.base.read(ROOT/'experiments/2026-10-06-s2-realism/landmarks-result.json')
    if not replay['physical_start_admitted']:raise ValueError('offline admission failed')
    if mode=='full':
        proof=b.get('start_proof') or {};p=Path(proof.get('path',''))
        if not p.is_file() or old.hp.base.sha(p)!=proof.get('sha256'):raise ValueError('immutable physical start proof required')
        q=old.hp.base.read(p)
        if (q.get('execution_bundle_id')!=IDS['start'] or q.get('source_sha')!=b['source_sha'] or
                q.get('options')!=plan['options']['start'] or q.get('start_within_25cm') is not True or
                q.get('status')!='STAGE_REACHED_UNQUALIFIED'):raise ValueError('physical start gate failed')
    for p,digest in b['source_sha256'].items():
        if old.hp.base.sha(ROOT/p)!=digest:raise ValueError('source changed: '+p)
