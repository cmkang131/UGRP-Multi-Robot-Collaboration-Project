import hashlib
import pytest
from harness.grasp_act_admission import recording_admission,CRITERIA
from harness.grasp_act_start_sync import GraspStartSync

HOST={'schema':'ugrp.grasp_act.host.v1','provider':'gcp','project_id':'ugrp-act-train-1014',
      'instance':'test','machine_type':'test-16','zone':'test-zone','cpu_count':16}

def test_recording_rejects_wrong_code_plan_profile_and_unqualified_gate(tmp_path):
    plan=tmp_path/'plan.json';plan.write_text('{}')
    gate={'n':38,'N':40,'qualified':True,'source_sha':'abc','teacher_profile':'visible_only',
        'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'object_kind':'long_beam','criteria':CRITERIA,
        'execution_host':HOST,'self_pose_source':'issued','rows':[{'status':'complete','exit':0,'physical_success':i<38,'source_sha':'abc','teacher_profile':'visible_only','execution_host':HOST} for i in range(40)]}
    assert recording_admission(gate,source_sha='abc',teacher_profile='visible_only',gate_plan=plan,execution_host=HOST)['qualified']
    for field,value in [('source_sha','wrong'),('teacher_profile','observable_v2'),('qualified',False),('plan_sha256','bad')]:
        bad={**gate,field:value}
        with pytest.raises(ValueError):recording_admission(bad,source_sha='abc',teacher_profile='visible_only',gate_plan=plan,execution_host=HOST)
    for host in ({**HOST,'provider':'azure'},{**HOST,'machine_type':'other'},None):
        with pytest.raises(ValueError,match='machine'):
            recording_admission(gate,source_sha='abc',teacher_profile='visible_only',gate_plan=plan,execution_host=host)
    gate['rows'][0]['execution_host']={**HOST,'instance':'other'}
    with pytest.raises(ValueError,match='machine'):
        recording_admission(gate,source_sha='abc',teacher_profile='visible_only',gate_plan=plan,execution_host=HOST)


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


def test_recording_mode_checks_bind_all_pairs_to_one_machine():
    from harness.grasp_act_admission import recording_mode_equivalence
    import copy
    original=[{'index':i,'status':'complete','exit':0,'physical_success':True,'execution_host':HOST,
               'source_sha':'abc','teacher_profile':'visible_only','action_contract':'v5',
               'self_pose_source':'issued','episode_plan_sha256':str(i)} for i in range(3)]
    recorded=[{**copy.deepcopy(r),'observation_sampling':{'rgb_size':[640,480],'rgb_hz':10}} for r in original]
    assert recording_mode_equivalence(original,recorded)['execution_host']==HOST
    recorded[1]['execution_host']['machine_type']='different'
    with pytest.raises(ValueError,match='machine'):recording_mode_equivalence(original,recorded)
