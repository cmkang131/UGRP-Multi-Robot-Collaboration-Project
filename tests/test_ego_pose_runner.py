import copy
import json
from scripts import run_ego_pose_continuity as m


def test_pair_bundles_only_differ_in_pose_options():
    bundles=[m.bundle(63001,k,'a'*40) for k in m.CONDITIONS]
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
