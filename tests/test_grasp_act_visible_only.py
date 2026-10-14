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

def test_clear_partial_view_is_not_centered_behind_visible_peer():
    from sim.grasp_act_visible_gaze import gaze_pose
    target=[1.0810693133,-.2686130114,.0324922446]
    peer={'xy':[.360730357,-.086971132],'radius':.104888054,'top_z_bound_m':.159222021}
    # Saved 72009 at 9.7 s: five band probes visible around the peer. The
    # former centering command changed 3/4/6 and lost all probes next tick.
    assert gaze_pose(target,FOLDED,[peer],visible=True)==FOLDED

def test_dart_observer_remembers_sent_command_not_clean_label():
    t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20))
    value=t._continuous(0.,.05,0.,0.)
    assert any(value['wheels'])
    value.update(wheels=[0.]*4,duration_s=[0.]*4)
    t.remember_applied(value)
    from sim.grasp_act_teacher_v3 import propagate_owned
    assert propagate_owned([.4,0.,.033],t.last_command,.1)==[.4,0.,.033]

def test_ready_is_revoked_on_drift_and_done_never_reads_contact_truth():
    m=VisibleWorld('r1','teal');t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20))
    t.started=True;t.skill_started=0.;t.phase='ready'
    x=m.observe([band(x=.1718)],1.)
    assert not t.prepare_signal(x,1.) and t.phase=='align' and t.ready_revocations==1
    t.phase='pick';t.arm.tick=lambda now:True
    a,done=t.step({'robots':{'r1':{'pose':[0,0,0]}},'objects':{},'walls':[]},2.)
    assert done and t.command_complete and t.outcome is None

def test_readiness_uses_same_pose_frame_as_approach():
    # Recorded 73011: body-axis error 33.57 mm, actual stance error 27.63 mm.
    # Approach accepted it but the former wait predicate revoked it 81 times.
    m=VisibleWorld('r1','teal')
    b=band();b['xyz']=[.1955099284374026,-.03272090788920136,.03249224461642269]
    b['yaw']=-.030077768540272665
    w=m.observe([b],0.)
    t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20));t.phase='align'
    assert t.ready_geometry(w)
    for now in (0.,.1,.2,.4):value,ready=t._approach(w,now)
    assert ready and not any(value['wheels'])
    t.phase='ready';assert t.prepare_signal(w,.5) and not t.ready_revocations

def test_route_does_not_skip_peer_corner_or_turn_away_from_target():
    from sim.grasp_act_visible_route import segment_free,waypoint,drive
    from scripts.zone_teacher import PeerDisc
    peer=PeerDisc((0.,0.,.17));start=(-.301,0.)
    path=[start,(-.301,.05),(-.301,.10),(-.25,.20),(-.10,.31)]
    # Old pop(<12 cm) skips both first corner cells and cuts into the peer.
    assert not segment_free(start,path[3],[peer],[],.13)
    target=waypoint(start,path,[peer],[],.13)
    assert target==path[2] and segment_free(start,target,[peer],[],.13)
    action=drive((0.,0.,0.),(-.4,.1),(-.1,.1),(1.,0.))
    assert action['turn']==0. and action['left']>0. and action['forward']<0.

def test_observed_cargo_at_goal_does_not_launch_futile_astar(monkeypatch):
    from sim.grasp_act_visible_route import constraints,free
    m=VisibleWorld('r1','teal');w=m.observe([band(x=.8)],0.)
    w['objects']['can_1']={'xy':[.597,0.], 'radius':.0314,'top_z_bound_m':.0563}
    t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20));t.folded_ready=True
    import scripts.zone_teacher as zone
    monkeypatch.setattr(zone,'plan_path',lambda *a,**k:pytest.fail('occupied goal sent to A*'))
    value=t._route(w,(.597,0.),0.,0.)
    assert not any(value['wheels']) and t.blocked_goal_calls==1

def test_segment_check_allows_retreat_from_observed_beam_margin():
    from sim.grasp_act_visible_route import segment_free
    # 73009 replay: 148 mm from the visible end inside a 150 mm inflated
    # keepout. The base must be able to follow A*'s outward escape segment.
    assert segment_free((.148,0.),(.18,0.),[(0.,0.,.02)],[],.13)
    assert not segment_free((.148,0.),(.13,0.),[(0.,0.,.02)],[],.13)
    import json
    from pathlib import Path
    row=json.loads((Path(__file__).parent/'fixtures/grasp_act_replay09_margin.json').read_text())
    t=VisibleOnlyGraspTeacher(row['rid'],row['end'],row['pwm'],bounds=(-20,20,-20,20));t.folded_ready=True
    world=row['world'];pose,g,heading,goal=t._geometry(world)
    value=t._route(world,goal,heading,world['t'])
    assert t.path and any(value['wheels'])

def test_saved_gcp_ep0_keeps_unreached_nearest_corner():
    import json,math
    from pathlib import Path
    from sim.grasp_act_visible_route import constraints,segment_free,waypoint
    from harness.grasp_act_visible_world import command_delta
    # fdfca319 / seed 71000, sample 120: r1 held forever while r2 waited.
    # The 17.6 mm-away rounded start cell is the only safe next waypoint.
    row=json.loads((Path(__file__).parent/'fixtures/grasp_act_gcp_ep0_corner.json').read_text())
    w=row['world'];t=VisibleOnlyGraspTeacher(row['rid'],row['end'],row['pwm'],bounds=(-20,20,-20,20))
    t.folded_ready=True
    pose,g,heading,goal=t._geometry(w)
    value=t._route(w,goal,heading,w['t'])
    radius,discs,rects=constraints(w,row['rid'],True)
    assert math.dist(pose[:2],t.path[0])==pytest.approx(.0176297,abs=1e-6)
    assert segment_free(pose[:2],t.path[0],discs,rects,radius)
    assert all(not segment_free(pose[:2],p,discs,rects,radius) for p in t.path[1:])
    assert waypoint(pose[:2],t.path,discs,rects,radius)==t.path[0]
    assert t.blocked_goal_calls==t.no_path_calls==0
    dx,dy,_=command_delta(value,.1);co,si=math.cos(pose[2]),math.sin(pose[2])
    following=(pose[0]+co*dx-si*dy,pose[1]+si*dx+co*dy)
    assert math.dist(following,t.path[0])<math.dist(pose[:2],t.path[0])
    assert segment_free(pose[:2],following,discs,rects,radius)
    # The old 5 mm proximity band also discards the still-needed corner.
    corner=t.path[0];distance=math.dist(pose[:2],corner)
    near=tuple(c+(p-c)*.004/distance for p,c in zip(pose[:2],corner))
    assert all(not segment_free(near,p,discs,rects,radius) for p in t.path[1:])
    assert waypoint(near,t.path,discs,rects,radius)==corner


def stable_teacher():
    t=VisibleOnlyGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20),teacher_stability='align_relook_v1')
    t.phase='align';t.started=True;t.skill_started=0.
    return t

def test_saved_73011_tiny_mixed_pulses_become_bounded_forward_correction():
    import json
    from pathlib import Path
    row=json.loads((Path(__file__).parent/'fixtures/grasp_act_align73011.json').read_text())
    t=VisibleOnlyGraspTeacher('r2','teal',row['pwm'],bounds=(-20,20,-20,20),teacher_stability='align_relook_v1');t.phase='align'
    a,ready=t._approach(row['world'],row['world']['t'])
    assert not ready and a['wheels']==[.35]*4
    assert all(.04<=d<=.15 for d in a['duration_s'])

def test_alternating_alignment_errors_reset_into_relook():
    t=stable_teacher();t.ready_geometry=lambda w:False
    for k in range(5):
        b=band(x=.203+(.005 if k%2==0 else -.005))
        w=VisibleWorld('r1','teal').observe([b],k*.1)
        a,_=t._approach(w,k*.1)
    assert t.phase=='relook' and not any(a['wheels'])
    assert not any(t.align_integral)

def test_alignment_no_progress_has_three_second_deadline():
    t=stable_teacher();t.ready_geometry=lambda w:False
    w=VisibleWorld('r1','teal').observe([band(x=.210)],0.)
    for now in (0.,.1,2.9,3.):a,_=t._approach(w,now)
    assert t.phase=='relook' and not any(a['wheels'])
    assert t.events[-2]['alignment_recovery']=='no_visible_error_progress_3s'

def test_lateral_deadband_has_distinct_restart_threshold():
    t=stable_teacher();t.ready_geometry=lambda w:False
    chosen=[]
    for k,y in enumerate((.019,.016,.011,.016,.019)):
        b=band(x=.210);b['xyz'][1]=y
        w=VisibleWorld('r1','teal').observe([b],k*.1)
        t._approach(w,k*.1);chosen.append(t.align_active[1])
    assert chosen==[True,True,False,False,True]

def test_search_sweeps_pan_before_turning_and_ignores_hidden_target():
    from copy import deepcopy
    commands=[]
    for hidden in ((9.,8.,2.),(-9.,-8.,-2.)):
        t=stable_teacher();w=VisibleWorld('r1','teal').observe([],0.)
        w['beam']={'pose':list(hidden),'ends':{'teal':list(hidden)}}
        series=[]
        for k in range(60):series.append(t._observe(w,k*.1))
        assert all(not any(c['wheels']) for c in series)
        assert len(set(c['pwm']['6'] for c in series))>3
        commands.append(deepcopy(series))
    assert commands[0]==commands[1]

def test_input_audit_survives_result_writer_and_rejects_hidden_rows(tmp_path):
    import json
    from scripts.run_grasp_act_teacher import audit_visible_input,write
    report={'input_audit':{'measurement_rows':0,'invisible_measurements':0}}
    audit_visible_input(report['input_audit'],[band()])
    write(tmp_path/'result.json',report)
    assert json.loads((tmp_path/'result.json').read_text())['input_audit']['invisible_measurements']==0
    with pytest.raises(ValueError,match='invisible'):audit_visible_input(report['input_audit'],[band(4)])
    assert report['input_audit']['invisible_measurements']==1
