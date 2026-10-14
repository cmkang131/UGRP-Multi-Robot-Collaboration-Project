import math
from sim.grasp_act_teacher import GraspTeacher, local
from scripts.zone_teacher import FOLDED
from harness.grasp_act_contract_v4 import command


def truth(pose):
    return {'robots':{'r1':{'pose':pose}},'beam':{'pose':[1.,0.,0.],
            'ends':{'teal':[.73,0.,.024],'blue':[1.27,0.,.024]}},'contacts':{'r1':[0.,0.]}}


def test_teacher_uses_v3_station_not_old_v2_radius():
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True;t.phase='align'
    x=truth([.527,0.,0.])  # .73-.203
    for now in (0,.1,.2,.4):
        a,done=t.step(x,now,permit_pick=False);command(a);assert not done
    assert t.phase=='ready'
    assert t.outcome is None


def test_teacher_corrects_sideways_with_existing_native_primitive():
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True;t.phase='align'
    a,done=t.step(truth([.527,-.04,0.]),0)
    assert a['drive'][1]>0 and a['duration_s']==.15 and not done


def test_pregrasp_near_wall_can_shorten_without_changing_assigned_end():
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-1.05,5.4,-3.15,1.45));t.started=True
    x={'robots':{'r1':{'pose':[.42,-1.58,-2.84]}},
       'beam':{'pose':[-.163,-2.038,.096],'ends':{'teal':[-.432,-2.064,.024]}}}
    t.step(x,0.,permit_pick=False)
    assert t.staging_distance==.203 and t.path
    assert t.end=='teal' and t.outcome is None


def test_no_contact_or_no_lift_never_success():
    for contacts,z in (([1.,1.],.024),([0.,0.],.1)):
        t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True
        t.phase='verify';t.initial_end_z=.024
        x=truth([.527,0.,0.]);x['contacts']['r1']=contacts;x['beam']['ends']['teal'][2]=z
        for now in (0.,1.,2.,5.1):
            _,done=t.step(x,now);assert not done
        assert t.outcome=='no_bilateral_end_lift'


def test_arm_schedule_uses_pad_ik_and_never_changes_base_or_cargo():
    import copy
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True;t.phase='ready'
    x=truth([.527,0.,0.]);before=copy.deepcopy(x)
    t.step(x,0)
    assert x==before and t.phase=='pick'
    assert t.arm.events and t.arm.commanded[1]==1500


def test_scene_keeps_real_scenario_inventory_without_world():
    from scripts.make_grasp_act_plan import prepare
    from sim.grasp_act_scene import make_scene,colors,COLOR_PROFILE
    import xml.etree.ElementTree as ET
    plan=prepare(count=1)['episodes'][0];scene=make_scene(plan)
    assert len(scene.cargo)==3 and len(scene.config['setup_only']['objects'])==4
    assert scene.config['robot_model']=='masterpi_v3'
    xml='<mujoco><worldbody><geom name="cargo_beam_1__band_neg" rgba="0 0 0 1" size=".018 .02 .001"/><geom name="cargo_beam_1__band_pos" rgba="0 0 0 1" size=".018 .02 .001"/></worldbody></mujoco>'
    assert colors(xml,'off')==xml
    before=ET.fromstring(xml);after=ET.fromstring(colors(xml,COLOR_PROFILE))
    for x,y in zip(before.iter(),after.iter()):
        assert x.tag==y.tag and {k:v for k,v in x.attrib.items() if k!='rgba'}=={k:v for k,v in y.attrib.items() if k!='rgba'}


def test_teacher_batch_does_not_count_interrupted_or_host_error_as_physical_trials():
    from scripts.run_grasp_act_batch import summarize
    rows=[{'status':'complete','physical_success':True,'joint_held':True,'exit':0,
           'teachers':{r:{'outcome':'success'} for r in ('r1','r2')}},
          {'status':'complete','physical_success':False,'exit':0,
           'teachers':{'r1':{'outcome':'phase_timeout'},'r2':{'outcome':'episode_timeout'}}},
          {'status':'interrupted','exit':130}, {'status':'HOST_ERROR','exit':1}]
    result=summarize(rows,20)
    assert (result['n'],result['N'],result['planned_N'],result['started_N'])==(1,2,20,4)
    assert result['robots']['r1']=={'n':1,'N':2}
    assert result['interrupted']==1 and result['host_errors']==1
    assert result['failure_reasons']=={'phase_timeout':1,'episode_timeout':1}


def test_failed_route_cached_until_next_replan(monkeypatch):
    import sim.grasp_act_teacher as module
    calls=[]
    monkeypatch.setattr(module,'plan_path',lambda *a,**k:calls.append(a) or None)
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True
    for now in (0.,.1,.2,.9,1.):t.step(truth([-.5,0.,0.]),now)
    assert len(calls)==2 and t.no_path_calls==2


def test_coarse_tracking_hands_to_alignment_before_stiction_stop_band():
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True
    a,done=t.step(truth([.527,-.035,0.]),0)
    assert t.phase=='align' and a['drive'][1]>.08 and not done


def test_stop_command_stops_wheels_without_cancelling_arm():
    from scripts.run_grasp_act_teacher import apply
    from types import SimpleNamespace
    calls=[];port=SimpleNamespace(stop=lambda:calls.append('stop'),apply=lambda *a:calls.append(a))
    c={'t':0.,'drive':[0.,0.,0.],'duration_s':0.,'pwm':{str(k):v for k,v in FOLDED.items()}}
    apply(port,c,0.,c)
    assert calls==['stop']


def test_opt_in_integral_resolves_measured_71033_residual_with_bounded_commands():
    # Saved failure: ground grip x=211.147 mm, target x=203 mm.
    baseline=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3))
    candidate=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3),profile='pi_geometry_v1')
    x=truth([.73-.21114696038361666,-.0001696830990068482,0.])
    for t in (baseline,candidate):t.started=True;t.phase='align'
    old=[];new=[]
    for k in range(100):
        a,_=baseline.step(x,k*.1);b,done=candidate.step(x,k*.1)
        old.append(a['drive'][0]);new.append(b['drive'][0]);command(b)
        assert not done
    assert max(old)-min(old)<1e-12
    assert new[-1]>new[0]*2
    assert all(abs(v)<=lim for v,lim in zip(candidate.align_integral,(.025,.025,.03)))
    assert candidate.ik_rejections>0 and candidate.phase=='align'


def test_low_cargo_radius_does_not_shrink_walls_unknown_objects_or_peers(monkeypatch):
    import sim.grasp_act_teacher as module
    captured=[]
    monkeypatch.setattr(module,'plan_path',lambda *a,**k:captured.append((a,k)) or [])
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3),rects=[(0,2,.5,.1,0)],profile='pi_geometry_v1')
    t.folded_ready=True;x=truth([-.5,0,0]);x['robots']['r2']={'pose':[2,2,0]}
    x['objects']={'low':{'xy':[1,1],'radius':.02,'top_z_bound_m':.08},'unknown':{'xy':[2,1],'radius':.02}}
    t._route(x,(.527,0),0,0)
    args,kw=captured[0];assert kw['radius']==.13
    assert args[2]==(-2.96,2.96,-2.96,2.96)
    assert abs(kw['rects'][0][2]+kw['radius']-(.5+.17))<1e-12
    assert abs(args[3][0][2]+kw['radius']-.34)<1e-12
    assert abs(args[3][1][2]-(.02+.005))<1e-12
    assert abs(args[3][2][2]+kw['radius']-(.02+.02+.17))<1e-12
    t.folded_ready=False;t._route(x,(.527,0),0,1.)
    assert captured[-1][1]['radius']==.17


def test_hidden_target_does_not_select_scan_or_translation():
    from copy import deepcopy
    a=truth([-.5,0,0]);b=deepcopy(a);b['beam']['ends']['teal']=[-5.,3.,.024]
    for x in (a,b):x['visibility']={'r1':{'visible_probes':0,'objects':[],'peers':[]}}
    commands=[]
    for x in (a,b):
        t=GraspTeacher('r1','teal',FOLDED,bounds=(-6,6,-6,6),profile='observable_v2');t.started=True
        c,_=t.step(x,1.);commands.append(c)
        assert c['drive'][:2]==[0.,0.] and not t.observed_objects
    assert commands[0]==commands[1]


def test_gaze_uses_real_pwm_and_brings_near_end_into_vertical_view():
    import numpy as np
    from sim.grasp_act_gaze import gaze_pose,camera_extrinsics
    for target in ((.203,0,.033),(.5,.2,.033),(1.7,-.3,.033)):
        p=gaze_pose(target,FOLDED);o,axes=camera_extrinsics(p)
        v=np.array(axes)@(np.array(target)-o)
        assert v[2]>0 and abs(v[1]/v[2])<.3
        assert all(500<=x<=2500 for x in p.values())


def test_ready_robot_realigns_after_search_turn_instead_of_blind_pick():
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-6,6,-6,6),profile='observable_v2')
    t.started=True;t.phase='ready';x=truth([.527,0,0]);x['visibility']={'r1':{'visible_probes':0}}
    t.step(x,1.,permit_pick=True)
    c,done=t.step(x,5.,permit_pick=True)
    assert t.phase=='align' and c['drive'][2] and not t.arm.events and not done
