import pytest
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_contract import MEMORY_S
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from scripts.zone_teacher import FOLDED

def band(n=15,x=.203):
    return {'id':'band_teal','kind':'band','xyz':[x,0.,.0326],'yaw':0.,'visible_n':n,'probe_N':15}

def test_visibility_threshold_memory_and_default_self_pose_boundary():
    m=VisibleWorld('r1','teal');assert m.observe([band(4)],0.)['beam'] is None
    a=m.observe([band()],.1);assert a['beam']['ends']['teal']==pytest.approx([.203,0,.024])
    assert a['robots']['r1']['pose']==[0.,0.,0.]
    with pytest.raises(ValueError,match='GT self'):m.observe([], .2,comparison_pose=[10,10,0])
    m.issue({'wheels':[.35]*4,'duration_s':[.1]*4})
    b=m.observe([], .2);assert b['robots']['r1']['pose'][0]>0
    assert b['beam']['ends']==a['beam']['ends']
    assert m.observe([], .2+MEMORY_S)['beam'] is None

def test_lost_target_gaze_is_independent_of_hidden_current_self_pose():
    commands=[]
    for fake_pose in ([0.,0.,0.],[9.,-8.,2.]):
        m=VisibleWorld('r1','teal');seen=m.observe([band(x=.6)],0.)
        t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20));t.started=True;t.skill_started=0.
        t._observe(seen,0.)
        lost=m.observe([], .1);lost['robots']['r1']['pose']=fake_pose
        commands.append(t._observe(lost,.1))
    assert commands[0]==commands[1]

def test_ready_is_revoked_on_drift_and_done_never_reads_contact_truth():
    m=VisibleWorld('r1','teal');t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20))
    t.started=True;t.skill_started=0.;t.phase='ready'
    x=m.observe([band(x=.1718)],1.)
    assert not t.prepare_signal(x,1.) and t.phase=='align' and t.ready_revocations==1
    t.phase='pick';t.arm.tick=lambda now:True
    a,done=t.step({'robots':{'r1':{'pose':[0,0,0]}},'objects':{},'walls':[]},2.)
    assert done and t.command_complete and t.outcome is None
