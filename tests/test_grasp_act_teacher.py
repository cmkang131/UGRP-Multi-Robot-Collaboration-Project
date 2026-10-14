import math
from sim.grasp_act_teacher import GraspTeacher, local
from scripts.zone_teacher import FOLDED
from harness.grasp_act_contract import command


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


def test_stop_command_stops_wheels_without_cancelling_arm():
    from scripts.run_grasp_act_teacher import apply
    from types import SimpleNamespace
    calls=[];port=SimpleNamespace(stop=lambda:calls.append('stop'),apply=lambda *a:calls.append(a))
    c={'t':0.,'drive':[0.,0.,0.],'duration_s':0.,'pwm':{str(k):v for k,v in FOLDED.items()}}
    apply(port,c,0.,c)
    assert calls==['stop']
