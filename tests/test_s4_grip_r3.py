import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from harness.s4_grip_r3 import R3Grip,cyan_mask
from scripts.run_s4_grip_r3 import cases,PLAN
from scripts.submit_s4_grip_r3 import healthy,initial_checks,commands


def image(y1=220,y2=400):
    hsv=np.zeros((480,640,3),np.uint8);hsv[y1:y2,160:480]=(90,200,200)
    return cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)


def test_lens_noise_cannot_anchor_but_low_edge_roi_can():
    noise=image(14,36);assert not cyan_mask(noise).any()
    low=image(458,470)
    old=R3Grip();new=R3Grip('edge_roi')
    for i in range(3):a=old.observe(low,i*.1);b=new.observe(low,i*.1)
    assert a['state']=='unknown' and b['state']=='held'


@pytest.mark.parametrize('mode',['absence_vote','active_reobserve'])
def test_presence_vote_does_not_alarm_on_motion_and_waits_five_empty_frames(mode):
    m=R3Grip(mode)
    for i in range(3):m.observe(image(),i*.1)
    moved=image(380,465)
    assert all(m.observe(moved,t)['state']=='held' for t in (.3,.4,.5,.6))
    blank=np.zeros((480,640,3),np.uint8)
    assert [m.observe(blank,t)['state'] for t in (.7,.8,.9,1.,1.1)]==['held']*4+['grip_lost']


def test_bounded_reobserve_from_rgb_commands_only_and_no_late_reanchor():
    from harness.zone_final_pair_vision import grasp_postures
    from harness.visual_arm_v3 import forward_grip
    pose={1:1500,**grasp_postures()[0]};m=R3Grip('active_reobserve');blank=np.zeros((480,640,3),np.uint8)
    for i in range(5):m.observe(blank,i*.1)
    q=m.request_reobserve(.4,.4,pose);assert q and q['until']==pytest.approx(1.3)
    assert all(p==1500 for _,sid,p in q['events'] if sid==1)
    assert np.linalg.norm(np.array(forward_grip(q['pose']))-np.array(forward_grip(pose)))<.0003
    assert m.observe(image(),.5)['state']=='unknown'
    for t in (.6,.7,.8,.9,1.,1.1,1.2):assert m.observe(image(),t)['state']=='unknown'
    for t in (1.3,1.4,1.5):r=m.observe(image(),t)
    assert r['state']=='held' and m.request_reobserve(1.5,1.5,pose) is None
    n=R3Grip('active_reobserve')
    for i in range(5):n.observe(blank,i*.1)
    assert n.request_reobserve(2.1,2.1,pose) is None
    with pytest.raises(ValueError):R3Grip('edge_roi',robot_id='r1')


def test_existing_is_same_frozen_sensor_and_all_seeds_paired():
    from harness.s4_grip_visual import TemporalGrip
    a=R3Grip();b=TemporalGrip('cyan')
    for i in range(5):assert a.observe(image(),i*.1)==b.observe(image(),i*.1)
    rows=commands('a'*40);assert len(rows)==8
    for name,argv in rows:
        job,seq=cases(name);assert len(seq)==4
        assert {c['variant'] for c in seq}=={'hold','loss'}
        assert len({c['seed'] for c in seq})==2
    old=json.loads(Path('experiments/2026-10-06-s4-llm/s4grip2/batch-plan.json').read_text())
    refs={c['seed']:c for j in old['runs'] if j['robot_id']=='r3' for c in j['cases']}
    _,seq=cases('s4grip3-existing-explore-r1')
    for c in seq:
        assert c['onset_s']==refs[c['seed']]['onset_s'] and c['force_xy_n']==refs[c['seed']]['force_xy_n']


def health(**changes):
    return dict(status='RUNNING',phase='POST_GRASP_MONITOR',sim_time=10.4,frames=3,issued_commands=30,
        servo_ids=[1,3,4,5,6],arm_displacement_m=.06,**changes)


def test_initial_check_requires_advancing_frames_and_actual_arm_motion():
    h=health();assert healthy(h)
    h['arm_displacement_m']=0.;assert not healthy(h)
    ticks=[0.];calls=[0]
    def read(names):
        calls[0]+=1;h=health();h['sim_time']+=calls[0];h['frames']+=calls[0]
        return {'job':dict(health=h,exit=None)}
    result=initial_checks(['job'],'a'*40,read=read,terminate=lambda *a:pytest.fail('unexpected stop'),wait=lambda s:ticks.__setitem__(0,ticks[0]+s),clock=lambda:ticks[0])
    assert result['job']['status']=='PASS' and calls[0]==2


def test_initial_exception_stops_only_failed_job():
    killed=[]
    result=initial_checks(['bad','good'],'a'*40,
        read=lambda names:{'bad':dict(health=dict(status='ERROR'),exit=None),'good':dict(health=health(),exit='0')},
        terminate=lambda name,sha,reason:killed.append(name),wait=lambda s:None,clock=lambda:0.)
    assert killed==['bad'] and result['bad']['status']=='FAIL' and result['good']['status']=='PASS_COMPLETED'
