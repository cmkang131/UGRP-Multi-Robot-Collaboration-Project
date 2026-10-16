import hashlib
import pytest
from harness.grasp_act_admission import recording_admission,CRITERIA
from harness.grasp_act_start_sync import GraspStartSync


def test_recording_rejects_wrong_code_plan_profile_and_unqualified_gate(tmp_path):
    plan=tmp_path/'plan.json';plan.write_text('{}')
    gate={'n':38,'N':40,'qualified':True,'source_sha':'abc','teacher_profile':'visible_only',
        'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'object_kind':'long_beam','criteria':CRITERIA,
        'self_pose_source':'issued','rows':[{'status':'complete','exit':0,'physical_success':i<38,'source_sha':'abc','teacher_profile':'visible_only'} for i in range(40)]}
    assert recording_admission(gate,source_sha='abc',teacher_profile='visible_only',gate_plan=plan)['qualified']
    for field,value in [('source_sha','wrong'),('teacher_profile','observable_v2'),('qualified',False),('plan_sha256','bad')]:
        bad={**gate,field:value}
        with pytest.raises(ValueError):recording_admission(bad,source_sha='abc',teacher_profile='visible_only',gate_plan=plan)


def test_start_sync_uses_ack_and_injected_delay_only():
    sync=GraspStartSync(('r1','r2'),{'r1':0.,'r2':1.5})
    assert not any(sync.tick({'r1':True,'r2':False},0.).values())
    assert not any(sync.tick({'r1':True,'r2':True},.1).values())
    assert sync.tick({'r1':True,'r2':True},.2)=={'r1':True,'r2':False}
    assert sync.tick({'r1':True,'r2':True},1.6)=={'r1':True,'r2':True}
    assert {e['event'] for e in sync.events}=={'GO','ACK','START'}
    with pytest.raises(ValueError):sync.tick({'r1':True,'r2':True,'gt_visible':True},2.)


def test_local_handoff_plan_range_and_recorded_jitter():
    from scripts.make_grasp_act_handoff_plan import handoff_plan
    p=handoff_plan(count=3,seed=100000,split='train')
    for episode in p['episodes']:
        import math
        spawns=episode['spawns']
        assert all(math.dist(spawns[a][:2],spawns[b][:2])>=.37
                   for a in episode['roles'] for b in spawns if a!=b)
        for row in episode['handoff_distribution'].values():
            assert .3<=row['accepted_distance_m']<=.8 and len(row['xy_error_m'])==2
