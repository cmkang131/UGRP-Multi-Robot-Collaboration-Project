import math
from types import SimpleNamespace
import numpy as np
import pytest
from harness.natural_floor_slam import compose,Observation
from harness.reloc15_handoff import deliver


def test_nonzero_map_frame_and_delayed_command_replay_once():
    anchor=np.array([2.,-1.,math.pi/2]);exposure=np.array([.4,.2,.3]);delta=np.array([.1,-.04,.2])
    map_pose=compose(anchor,exposure);odom=np.array([.5,-.8,-.6])
    (pose,P),record=deliver(map_pose,np.eye(3)*.01,map_from_execution=anchor,
        exposure_t=1.,release_t=2.,odom_at_exposure=odom,odom_at_release=compose(odom,delta),replay_covariance=np.zeros((3,3)))
    np.testing.assert_allclose(pose,compose(exposure,delta),atol=1e-14)
    assert record['replay_count']==1 and np.linalg.eigvalsh(P).min()>0


def test_empty_orb_bank_still_receives_admitted_map_fix():
    from harness.selfmap6_safety import GatedPriorSLAM
    s=GatedPriorSLAM('r3',max_sigma_xy_m=.15,max_sigma_yaw_rad=math.radians(5))
    s.reloc15_pose_handoff=True;s._gate_prediction=np.eye(3)*.01;s.reloc13_absolute_static=True
    calls=[]
    def gate(p,q,P,d):calls.append(q.copy());return dict(accepted=True)
    obs=Observation(1,1.,np.empty((0,2)),np.empty((0,32),np.uint8))
    target=np.array([.2,-.1,.3])
    e=s.guarded_step(obs,command_delta=np.array([.05,0,.1]),command_covariance=np.zeros((3,3)),
        correction_gate=gate,pose_override=(target,np.eye(3)*.002))
    np.testing.assert_allclose(s.pose,target)
    assert len(calls)==1 and e['status']=='visual_relocalized'


def test_rgb_yaw_replaces_pair_command_once_without_refreshing_metric_fix(monkeypatch):
    from harness.reloc15_heading import Heading
    import harness.zone_solo_cyan_rotation_envelope as mod
    monkeypatch.setattr(mod,'yaw_measurement',lambda *a:dict(status='measured',delta_yaw=.06,sigma_yaw=.01))
    h=Heading();h.servo={1:1500,3:803,4:1888,5:2192,6:1491};h.servo_since=0.
    own=SimpleNamespace(x=np.array([2.,3.,.1]),P=np.eye(3)*.01)
    image=np.zeros((480,640,3),np.uint8)
    h.observe(image,3.,own);own.x[2]+=.02;h.delta_yaw=.02;h.observe(image,3.2,own)
    assert own.x[2]==pytest.approx(.16)
    np.testing.assert_equal(own.x[:2],[2.,3.])
    assert not h.last['metric_fix_refreshed'] and h.last_measurement_t==3.2
    monkeypatch.setattr(mod,'yaw_measurement',lambda *a:dict(status='unknown_texture'))
    h.observe(image,3.4,own)
    assert h.last_measurement_t==3.2 and own.x[2]==pytest.approx(.16)


def test_recording_buffer_keeps_only_ten_sim_seconds(tmp_path):
    from harness.failure_rgb_buffer import FailureRGBBuffer
    b=FailureRGBBuffer(tmp_path/'frames')
    for i in range(152):b.add(i*.1,b'jpeg',camera='r1/robot_cam')
    r=b.flush('supervisor_stop')
    assert r['frame_N']==101 and r['bytes']==404
    assert r['frames'][0]['t']==pytest.approx(5.1)


def test_rel15_disabled_by_default_and_requires_tracking():
    from harness.self_map_integration import Options
    assert not Options().reloc15_pose_handoff_v1
    with pytest.raises(ValueError):Options(reloc15_pose_handoff_v1=True)


def test_update_budget_is_per_filter_and_stationary_image_is_not_remeasured():
    from harness.e2e_static_rgb_localizer import create
    from harness.selfmap4_geometry import static_input
    from harness.own_map_amcl_vendor.field import PARAMS
    static,_=static_input()
    baseline=create(static,option='static_landmarks_v1',seed=1)
    candidate=create(static,option='static_landmarks_v1',seed=1)
    candidate.reloc15_update_budget=dict(distance_m=.05,yaw_rad=math.radians(2.5))
    servo={1:2000,3:740,4:2320,5:1320,6:1500}
    for pf in (baseline,candidate):
        pf.step(t=0.,points=[[1.,0]],delta=[0,0,0],servo=servo)
    old=baseline.step(t=1.,points=[[1.,0]],delta=[.06,0,.05],servo=servo)
    new=candidate.step(t=1.,points=[[1.,0]],delta=[.06,0,.05],servo=servo)
    assert not old['updated'] and new['updated']
    assert not candidate.step(t=2.,points=[[1.,0]],delta=[0,0,0],servo=servo)['updated']
    assert PARAMS['update_min_d_m']==.25 and PARAMS['update_min_a_rad']==.2


def test_fixed_image_border_cannot_override_moving_floor():
    import json,cv2
    from pathlib import Path
    from harness.reloc15_heading import commanded_rotation
    from harness.reloc15_dense_yaw import measure
    from harness.zone_solo_cyan_rotation_envelope import yaw_measurement
    p=Path(__file__).parent/'fixtures/reloc15'
    label=json.loads((p/'counterexample.json').read_text())
    images=[cv2.cvtColor(cv2.imread(str(p/f'heading-{s}.jpg')),cv2.COLOR_BGR2RGB) for s in ('before','after')]
    cm=SimpleNamespace(_rot=commanded_rotation(label['pwm']))
    sparse=yaw_measurement(*images,cm,label['pwm'],None)
    dense=measure(*images,cm)
    expected=math.radians(label['actual_delta_yaw_deg'])
    assert dense['status']=='measured' and dense['gradient_rank']==8
    assert abs(dense['delta_yaw']-expected)<abs(sparse['delta_yaw']-expected)
    assert dense['support_radius_px']==80 and not dense['correlation_is_accuracy_certificate']
