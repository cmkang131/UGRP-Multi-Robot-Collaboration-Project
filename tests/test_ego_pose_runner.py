import copy
import json
from types import SimpleNamespace
from scripts import run_ego_pose_continuity as m
from scripts.launch_ego_pose_azure import measured_terminal
from scripts.ego_pose_archive_transport import remaining_run_bytes


def test_reservations_include_unstarted_groups_and_partial_active_siblings(tmp_path):
    peak=768*2**20
    queued=tmp_path/'egojump-63003-12345678-r1';queued.mkdir()
    active=tmp_path/'egojump-63002-12345678-r1';(active/'data').mkdir(parents=True)
    jobs=[]
    for i in range(3):
        p=active/'data'/str(i);p.mkdir();(p/'trace').write_bytes(b'x'*100)
        jobs.append(dict(root=str(p),status='RUNNING'))
    jobs[0].update(status='RECORDED',exit_code=0)
    status=active/'data/batch-status.json';status.write_text(json.dumps(jobs))
    assert remaining_run_bytes(tmp_path)['bytes']==5*peak-200
    # A partial metadata write must reserve the full group, never silently omit it.
    status.write_text('[')
    assert remaining_run_bytes(tmp_path)['bytes']==6*peak
    (queued/'EXIT').write_text('0\n')
    assert remaining_run_bytes(tmp_path)['bytes']==3*peak


def test_physical_failure_is_retained_but_host_and_supervisor_errors_block_batch():
    row=dict(status='PHYSICAL_FAILURE',score={'samples':305})
    assert measured_terminal(row)
    assert measured_terminal(dict(row,status='RECORDED'))
    assert not measured_terminal(dict(row,status='HOST_ERROR'))
    assert not measured_terminal(dict(row,scoring_error='missing truth'))
    assert not measured_terminal(dict(row,interrupted_reason='INITIAL_CHECK_ABNORMAL'))
    assert not measured_terminal(dict(status='PHYSICAL_FAILURE'))


def test_pair_bundles_only_differ_in_pose_options(monkeypatch):
    calls=[]
    def baseline(seed,condition,source):
        calls.append((seed,condition,source))
        return dict(seed=seed,source=source,physics={'unchanged':True},options={
            'rgb_reconfirmation':condition,'covariance_inflation':condition})
    monkeypatch.setattr(m,'_base',lambda:SimpleNamespace(bundle=baseline))
    bundles=[m.bundle(63001,k,'a'*40) for k in m.CONDITIONS]
    assert calls==[(63001,'off','a'*40)]*3
    for b in bundles:
        assert b['options']['rgb_reconfirmation']=='off'
        assert b['options']['covariance_inflation']=='off'
        del b['execution_bundle_id']
        for k in ('pose_continuity','pose_reporting','stationary_update','correction_gate','correction_limit'):
            del b['options'][k]
    assert all(b==bundles[0] for b in bundles)


def test_early_check_uses_physical_movement_and_records_turn_only_failure(tmp_path):
    (tmp_path/'eval_only').mkdir()
    truth=[dict(t=t,robot_xyz_m=[0,0,0],robot_yaw_rad=t/20) for t in range(31)]
    own=[dict(t=t,stage='explore',command={'turn':.35}) for t in range(31)]
    (tmp_path/'own-controller.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in own))
    (tmp_path/'eval_only/trajectory.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in truth))
    r=m.initial_check(tmp_path,180,'')
    assert not r['healthy'] and r['issues']==['rotation_or_hold_only']
    assert r['yaw_motion_rad']>0 and r['xyz_displacement_m']==0
    truth[-1]['robot_xyz_m'][0]=.05;own[-1]['command']={'forward':.3};own[-1]['stage']='approach'
    (tmp_path/'own-controller.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in own))
    (tmp_path/'eval_only/trajectory.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in truth))
    assert m.initial_check(tmp_path,240,'')['healthy']
