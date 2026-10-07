import copy
import json
from types import SimpleNamespace as NS

import cv2
import numpy as np
import pytest

from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from harness import zone_solo_cyan_landmarks as m
from harness.zone_solo_cyan_amcl_sensor import runtime_class as sensor_runtime, OPTION as SENSOR
from harness.zone_solo_cyan_best_cluster import runtime_class as best_runtime
from harness.zone_solo_cyan_look_ahead import Runtime as Carry


def test_default_off_command_record_bytes(static, cal):
    Previous=sensor_runtime(best_runtime(Carry));Wrapped=m.runtime_class(Previous)
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
        vision_factory=FakeVision,**kw) for cls,kw in
        [(Previous,{}),(Wrapped,{}),(Wrapped,dict(sensor_landmarks='off'))]]
    try:
        for r in rs:
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
            r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            issued=[r.step(t) for r in rs]
            assert len({json.dumps(c).encode() for c in issued})==1
            for r,cmds in zip(rs,issued):
                for rid,a in cmds:r.on_command(rid,t,a)
        assert len({json.dumps(r.record()).encode() for r in rs})==1
    finally:
        for r in rs:r.close()


def map_data():
    return dict(regions=dict(pickup=dict(center_m=[0.,0.],half_extents_m=[1.,1.],rgba='.12 .36 .70 .14'),
        B=dict(center_m=[4.,0.],half_extents_m=[1.,1.],rgba='.20 .40 .95 .30')),
        passages=[dict(kind='door',center_m=[2.,0.],width_m=.5)])


def test_partial_edge_not_visible_midpoint_as_map_center_and_blue_ambiguous():
    mapped=m.MapFeatures(map_data());f=dict(kind='floor_line',hue=110.,
        endpoints=[[-1.,-.5],[-1.,.5]],normal=[1.,0.])
    values=m.landmark_likelihood(mapped,np.array([[0.,0.,0.],[4.,0.,0.],[0.,.2,0.],[.5,0.,0.],[0.,0.,np.pi]]),[f])
    assert values[0]==pytest.approx(values[1])  # no privileged pickup vs B label
    assert values[0]==pytest.approx(values[2])  # partial line does not identify along-line translation
    assert values[0]>values[3]*100
    assert values[0]==pytest.approx(values[4])  # square opposite-edge symmetry retained
    np.testing.assert_array_equal(m.landmark_likelihood(mapped,np.zeros((3,3)),[]),np.ones(3))


def test_door_gaussian_matches_textbook_range_bearing_signature():
    mapped=m.MapFeatures(map_data());features=[dict(kind='door',center=[2.,0.],width=.5)]
    result=m.landmark_likelihood(mapped,np.array([[0.,0.,0.],[0.,1.,0.]]),features)
    p=m.PARAMS
    expected=(1-p['random_fraction'])*m.gaussian(0,p['sigma_range_m'])*m.gaussian(0,p['sigma_bearing_rad'])*m.gaussian(0,p['sigma_width_m'])+p['random_fraction']/(p['max_range_m']*2*np.pi*p['door_width_m'][1])
    assert result[0]==pytest.approx(expected)
    assert result[0]>result[1]*100


def test_floor_projection_and_segmentation_ignore_crops_and_self_mask():
    cm=NS(origin=np.array([0.,0.,1.]),_rot=np.diag([1.,-1.,-1.]))
    K=np.array([[200.,0.,160.],[0.,200.,120.],[0.,0.,1.]])
    image=np.full((240,320,3),130,np.uint8);image[:,:160]=[150,130,110]
    clear=np.ones((240,320),bool);mapped=m.MapFeatures(map_data())
    features=m.floor_features(image,cm,np.linalg.inv(K),mapped,clear)
    assert len(features)==1
    assert abs(np.mean(features[0]['endpoints'],axis=0)[0])<.01
    assert features[0]['normal'][0]<-.99
    assert m.floor_features(image,cm,np.linalg.inv(K),mapped,np.zeros_like(clear))==[]
    assert m.floor_features(np.full_like(image,[150,130,110]),cm,np.linalg.inv(K),mapped,clear)==[]
    uv=np.array([[160,120],[200,180]])
    xy,good,_=m.ground(cm,uv,np.linalg.inv(K));assert good.all()
    np.testing.assert_allclose(m.project(cm,np.c_[xy,np.zeros(2)],K),uv)


def test_no_door_from_missing_returns_or_unpaired_gap():
    cm=NS(origin=np.array([0.,0.,1.]),_rot=np.diag([1.,-1.,-1.]),
        t_of_row=lambda x:x,floor_point=lambda x:np.c_[np.arange(10)/10,np.ones(10)])
    obs=NS(b_kind=np.zeros(10),b_lo=np.full(10,120.),columns=np.arange(10)*20)
    image=np.full((240,320,3),120,np.uint8)
    assert m.door_features(image,cm,obs,np.eye(3),np.ones((240,320),bool))==[]


def test_invalid_options(static):
    for kw in [dict(sensor_landmarks='bad'),dict(sensor_landmarks=m.OPTION)]:
        with pytest.raises(ValueError):m.runtime_class(Carry)(static,None,None,**kw)


def test_private_update_and_floor_only_measurement_keeps_other_runtime_unchanged(static):
    from harness import zone_s2_realism_contract_v131 as contract
    from scripts.run_s2_look_ahead_dev import runtime_factory
    b=contract.bundle('a'*40,carry_pose='look_ahead_v1',servo_stiffness='real_v1',
        camera_pitch='stiff_target_v1',pregrasp_policy='log_only_v1')
    rs=[runtime_factory(b)(static,contract.ROOT/contract.old.CALIBRATION,
        contract.old.CALIBRATION_SHA,seed=1051) for _ in range(2)]
    try:
        other=rs[1].pose.provider.loc._pf.update_obs
        m.install(rs[0],static)
        assert rs[1].pose.provider.loc._pf.update_obs is other
        assert len(m.Measurement(np.empty((0,2)),[dict(kind='door')]))==1
    finally:
        for r in rs:r.close()
