import copy
import json
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest
from harness import zone_solo_cyan_rotation_envelope as m


def profile(sign=1):
    return dict(mean_curve=[[0, 0, 0], [0, 0, sign*math.radians(5)]],
                mean_delta=[0, 0, sign*math.radians(5)], prediction_variance=[0, 0, 0])


def test_off_exact_and_invalid():
    r=NS(record=lambda:{'untouched':True},step=lambda t:[('r3',{'kind':'hold'})])
    attrs=dict(vars(r));data=json.dumps(r.record()).encode()
    assert m.attach(r) is r and m.attach(r,active_rotation_guard='off') is r
    assert vars(r)==attrs and json.dumps(r.record()).encode()==data
    with pytest.raises(ValueError):m.attach(r,active_rotation_guard='bad')
    with pytest.raises(ValueError):m.attach(r,active_rotation_guard=m.OPTION)


@pytest.mark.parametrize('sign',[-1,1])
def test_actual_measured_yaw_not_nominal_pulse_count_bounds_both_directions(sign):
    guard=m.RotationEnvelope()
    for _ in range(16):
        assert guard.permit(profile(sign))['permitted']
        assert guard.update(dict(status='measured',delta_yaw=sign*math.radians(5.5),sigma_yaw=0))
    # 16 nominal pulses mean 80deg, measured motion is 88deg. Next pulse
    # must be blocked before it can cross 90, with the limit unchanged.
    assert not guard.permit(profile(sign))['permitted']
    assert guard.permit(profile(-sign))['permitted']
    assert m.PARAMS['max_abs_deg']==90


def test_uncertainty_is_not_averaged_away_and_unknown_never_counts_zero():
    guard=m.RotationEnvelope()
    assert not guard.update(dict(status='unknown_texture'))
    assert not guard.update(dict(status='measured',delta_yaw=float('nan'),sigma_yaw=0))
    for _ in range(10):
        guard.update(dict(status='measured',delta_yaw=math.radians(5),sigma_yaw=math.radians(1)))
    row=guard.permit(profile())
    assert row['uncertainty_deg']==pytest.approx(30)
    assert row['upper_deg']==pytest.approx(88)
    guard.update(dict(status='measured',delta_yaw=math.radians(5),sigma_yaw=math.radians(1)))
    assert not guard.permit(profile())['permitted']


def fake_runtime():
    state={'event':None}
    def step(t):
        if state['event'] is None:
            state['event']={'t':t,'schedule':[(t+.2,{'kind':'mecanum'})],
                            'action':{'added_s':8.}}
        return [('r3',dict(kind='mecanum',forward=0.,left=0.,turn=.35,duration_s=.1))]
    pf=NS(column_model_for=lambda s:object(),load=NS(loaded=True))
    return NS(step=step,on_frames=lambda t,f:None,record=lambda:dict(active=True),
              active_observation={},robot_id='r3',servo={1:1500,3:1000},
              pose=NS(provider=NS(loc=NS(_pf=pf))),flow=NS(table={}),
              pulse_profiles={'1:turn:0.35:0.10':profile()}),state


def test_missing_or_unknown_rgb_cancels_optional_action_without_open_loop_return(monkeypatch):
    r,state=fake_runtime();m.attach(r,active_rotation_guard=m.OPTION)
    assert r.step(100)==[('r3',{'kind':'hold'})]
    assert state['event']['schedule']==[]
    assert state['event']['action']['added_s']==pytest.approx(1.9)
    assert state['event']['rotation_guard_stop']['reason']=='missing_fresh_own_rgb'
    r,state=fake_runtime();m.attach(r,active_rotation_guard=m.OPTION)
    r.on_frames(100,{'r3':({'sim_time':100},np.zeros((480,640,3),np.uint8))})
    monkeypatch.setattr(m,'yaw_measurement',lambda *a:dict(status='unknown_texture'))
    assert r.step(100)==[('r3',{'kind':'hold'})]
    assert r.record()['active_rotation_guard']['events'][0]['stop']['reason']=='unknown_texture'


def test_default_off_actual_v140_runtime_bytes_and_rng():
    from pathlib import Path
    from scripts.run_s2_landmarks_dev import runtime_factory
    from harness import zone_solo_cyan_contract_v106 as c
    from harness.zone_solo_cyan_active_observation import attach,OPTION
    b=json.loads(Path('tests/fixtures/s2_ci/v133-bundle.json').read_text())
    r=runtime_factory(b)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**b['task'])
    try:
        attach(r,active_localization=OPTION)
        methods=(r.step,r.on_frames,r.record)
        data=json.dumps(r.record()).encode()
        rng=copy.deepcopy(r.pose.provider.loc._pf.rng.bit_generator.state)
        m.attach(r)
        assert methods==(r.step,r.on_frames,r.record)
        assert data==json.dumps(r.record()).encode()
        assert rng==r.pose.provider.loc._pf.rng.bit_generator.state
    finally:r.close()


def test_calibrated_homography_measures_rotation_without_command_or_truth(monkeypatch):
    import cv2
    from harness import vision_loc_protocol as vp
    K=np.array([[500.,0,320],[0,500.,240],[0,0,1.]])
    monkeypatch.setattr(vp,'load_vis3',lambda:(NS(mp=NS(K_INV=np.linalg.inv(K),undistort=lambda x:x)),))
    rng=np.random.default_rng(2)
    image=np.zeros((480,640,3),np.uint8)+40
    for x,y in rng.integers([30,30],[610,450],size=(150,2)):
        cv2.rectangle(image,(x-3,y-3),(x+3,y+3),(220,220,220),-1)
    cm=NS(_rot=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]]))
    yaw=math.radians(4.);c,s=math.cos(yaw),math.sin(yaw)
    body=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
    h=K@cm._rot.T@body.T@cm._rot@np.linalg.inv(K)
    moved=cv2.warpPerspective(image,h,(640,480))
    result=m.yaw_measurement(image,moved,cm,{}, {})
    assert result['status']=='measured' and result['inliers']>=6
    assert abs(result['delta_yaw']-yaw)<=3*result['sigma_yaw']
    assert result['delta_yaw']>0
