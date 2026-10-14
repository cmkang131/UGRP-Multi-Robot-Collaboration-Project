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


def test_coarse_tracking_hands_to_alignment_before_stiction_stop_band():
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True
    a,done=t.step(truth([.527,-.035,0.]),0)
    assert t.phase=='align' and a['drive'][1]>.08 and not done


def test_ik_boundary_stagnation_does_not_keep_constant_subthreshold_command():
    # Saved seed71003: within 3cm/0.06rad but ground IK has no solution.
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True;t.phase='align'
    x=truth([0.,0.,0.]);x['beam']['pose'][2]=-.0094
    x['beam']['ends']['teal']=[.2090742657,-.0139289398,.0238922446]
    first,_=t.step(x,0.,permit_pick=False)
    for k in range(1,101):last,done=t.step(x,k*.1,permit_pick=False);command(last)
    assert not done and t.phase=='align' and t.ik_rejections==101
    assert abs(last['drive'][1])>abs(first['drive'][1])
    assert all(abs(v)<=bound for v,bound in zip(t.align_integral,(.025,.025,.03)))
    # Once the whole descent is reachable, integral action is reset at rest.
    x['beam']['pose'][2]=0.;x['beam']['ends']['teal']=[.203,0.,.024]
    t.step(x,10.1,permit_pick=False)
    assert t.align_integral==[0.,0.,0.]


def test_intermediate_descent_ik_is_checked_before_ready(monkeypatch):
    import sim.grasp_act_teacher as module
    original=module.solve_grip_site_ik
    def blocked(target,**kwargs):
        if .05<target[2]<.08:raise ValueError('interior trajectory unreachable')
        return original(target,**kwargs)
    monkeypatch.setattr(module,'solve_grip_site_ik',blocked)
    t=GraspTeacher('r1','teal',FOLDED,bounds=(-3,3,-3,3));t.started=True;t.phase='align'
    for now in (0.,.1,.5):t.step(truth([.527,0.,0.]),now,permit_pick=False)
    assert t.phase=='align' and t.last_ik_error=='interior trajectory unreachable'


def test_stop_command_stops_wheels_without_cancelling_arm():
    from scripts.run_grasp_act_teacher import apply
    from types import SimpleNamespace
    calls=[];port=SimpleNamespace(stop=lambda:calls.append('stop'),apply=lambda *a:calls.append(a))
    c={'t':0.,'drive':[0.,0.,0.],'duration_s':0.,'pwm':{str(k):v for k,v in FOLDED.items()}}
    apply(port,c,0.,c)
    assert calls==['stop']


def test_resume_preserves_completed_failures_and_rejects_tampered_evidence(tmp_path):
    import json,hashlib,pytest
    from scripts.run_grasp_act_batch import resume_rows
    def write(path,value):path.write_text(json.dumps(value))
    prior=tmp_path/'prior';prior.mkdir();plan=tmp_path/'plan.json'
    write(plan,{'episodes':[{'seed':1},{'seed':2}]})
    write(prior/'RUN_META.json',{'sha':'fixed'})
    write(prior/'resource-admission.json',{'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()})
    write(prior/'speed-gate.json',{'admitted':True,'completed':16,'median_wall_per_sim':2.5})
    ep=prior/'episode-000';ep.mkdir();raw=ep/'raw';raw.mkdir()
    write(raw/'result.json',{'status':'complete','physical_success':False});write(raw/'plan.json',{'seed':1})
    write(raw/'manifest.json',{});(ep/'EXIT').write_text('0\n')
    row={'index':0,'raw':str(raw),'status':'complete','exit':0,'physical_success':False,
         'result_sha256':hashlib.sha256((raw/'result.json').read_bytes()).hexdigest()}
    write(prior/'teacher-gate.json',{'rows':[row,{'index':1,'status':'interrupted','exit':130}]})
    rows,_=resume_rows(prior,plan,'fixed',16,3.5)
    assert rows==[row] and rows[0]['physical_success'] is False
    with pytest.raises(ValueError,match='identical source'):resume_rows(prior,plan,'changed',16,3.5)
    write(prior/'teacher-gate.json',{'rows':[row,row]})
    with pytest.raises(ValueError,match='duplicate'):resume_rows(prior,plan,'fixed',16,3.5)
    write(prior/'teacher-gate.json',{'rows':[row]});write(raw/'result.json',{'physical_success':True})
    with pytest.raises(ValueError,match='hash mismatch'):resume_rows(prior,plan,'fixed',16,3.5)
