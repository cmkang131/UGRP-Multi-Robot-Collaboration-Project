import base64
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from harness.s4_grip_visual import TemporalGrip, GripMonitor, OPTION
from scripts.submit_s4_grip_batch import commands, submit_one
from scripts.run_s4_grip_dataset import cases, bundle


def frame(cargo='long_beam',shift=0):
    hsv=np.zeros((480,640,3),np.uint8)
    hsv[120:380,180+shift:420+shift]=(40 if cargo=='long_beam' else 90,200,200)
    return cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)


@pytest.mark.parametrize('cargo',['long_beam','cyan'])
def test_hold_loss_persistence_and_immutable_anchor(cargo):
    m=TemporalGrip(cargo)
    rows=[m.observe(frame(cargo),i*.1) for i in range(5)]
    assert [r['state'] for r in rows]==['unknown','unknown','held','held','held']
    empty=np.zeros((480,640,3),np.uint8)
    assert [m.observe(empty,t)['state'] for t in (.5,.6,.7)]==['held','held','grip_lost']
    assert m.observe(frame(cargo),.8)['state']=='grip_lost'


def test_translation_gap_blank_anchor_and_bad_frames():
    m=TemporalGrip('long_beam')
    for i in range(3):m.observe(frame(),i*.1)
    assert m.observe(frame(shift=120),.3)['state']=='held'
    assert m.observe(frame(shift=120),.5)['state']=='unknown'
    assert m.observe(frame(shift=120),.5)['state']=='unknown'
    assert m.observe(None,.6)['state']=='unknown'
    assert [m.observe(frame(shift=120),t)['state'] for t in (.7,.8,.9)]==['held','held','grip_lost']
    n=TemporalGrip('cyan')
    for i in range(3):q=n.observe(np.zeros((480,640,3),np.uint8),i*.1)
    assert q['state']=='unknown'
    assert n.observe(frame('cyan'),.3)['state']=='unknown'


def test_default_is_exact_legacy_and_new_mode_does_not_read_commands(monkeypatch):
    from harness import zone_pair_highpose_grip as legacy
    sentinel={'ok':False,'reason':'original'}
    monkeypatch.setattr(legacy,'relation',lambda image,commands:sentinel)
    assert GripMonitor().observe('bytes',0,{}) is sentinel
    image=base64.b64encode(cv2.imencode('.jpg',frame())[1]).decode()
    assert GripMonitor(mode=OPTION).observe(image,0,object())['state']=='unknown'


def test_batch_balanced_frozen_disjoint_splits_and_bundle_boundary():
    rows=commands('a'*40);assert len(rows)==6
    seeds={}
    for name,argv in rows:
        row,seq=cases(name);assert len(seq)==4 and '--execute' in argv
        for c in seq:seeds.setdefault((row['robot_id'],c['split']),[]).append((c['variant'],c['seed']))
    for key,seq in seeds.items():
        assert len(seq)==4
        assert sorted(s for v,s in seq if v=='hold')==sorted(s for v,s in seq if v=='loss')
    b=bundle('a'*40,'r3',42000)
    assert b['student_control'] is False and b['model_calls']==0 and not b['research_result']
    assert b['case']=='cyan' and b['execution_bundle_id'].endswith('v163')


def test_memory_refusal_retries_identical_command_only():
    seen=[];wait=[]
    def invoke(argv,**kwargs):
        seen.append((argv,kwargs['env']['LP_NUM_THREADS']))
        return SimpleNamespace(returncode=3 if len(seen)==1 else 1,stdout='',stderr='')
    r=submit_one('/runner','job',['python'],invoke=invoke,wait=wait.append)
    assert r['returncode']==1 and len(seen)==2 and seen[0]==seen[1] and wait==[30]


def test_contact_scoring_no_premature_credit_partial_or_missing_delay():
    from scripts.evaluate_s4_grip_dataset import score
    labels=[dict(sim_time=i*.1,label='held' if i<5 else 'partial' if i==5 else 'zero') for i in range(12)]
    def predictions(alarm):return [dict(sim_time=i*.1,state='grip_lost' if alarm is not None and i>=alarm else 'held') for i in range(12)]
    q=score(labels,predictions(8));assert q['detected'] and q['delay_frames']==2 and q['delay_sim_s']==.2
    q=score(labels,predictions(3));assert not q['detected'] and q['false_alarm'] and q['delay_frames'] is None
    q=score(labels,predictions(None));assert not q['detected'] and q['delay_sim_s'] is None
    with pytest.raises(ValueError):score(labels,predictions(8)[:-1])


def test_environment_fault_never_changes_commands_and_hold_is_unchanged():
    from sim.s4_grip_dataset import Perturbation
    def fake():
        m=SimpleNamespace(actuator_forcerange=np.array([[-18.,18.]]*6),body=lambda name:SimpleNamespace(id=0))
        w=SimpleNamespace(model=m,data=SimpleNamespace(xfrc_applied=np.zeros((1,6))),robot=lambda rid:SimpleNamespace(gripper_act={'r1':[0,1],'r2':[2,3],'r3':[4,5]}[rid]))
        rows=[]
        return SimpleNamespace(world=w,objects={'beam':dict(kind='long_beam',body_name='cargo_beam')},now=1.,_append=lambda *a:rows.append(a),commands={'r1':{1:1500},'r2':{1:1500}})
    for variant in ('hold','loss'):
        host=fake();p=Perturbation(host,'r1',dict(variant=variant,onset_s=2.,force_xy_n=[.5,-.3]))
        p.apply(1.9);assert np.all(host.world.model.actuator_forcerange[:,1]==18.)
        p.apply(2.);assert host.commands=={'r1':{1:1500},'r2':{1:1500}}
        assert host.world.model.actuator_forcerange[0,1]==pytest.approx(.018 if variant=='loss' else 18.)
        assert host.world.data.xfrc_applied[0,0]==(.5 if variant=='loss' else 0.)
        p.apply(2.6);assert not host.world.data.xfrc_applied.any()
