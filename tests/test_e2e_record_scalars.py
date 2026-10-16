import json
from types import SimpleNamespace
import numpy as np
import pytest
from harness.active_camera import SEARCH
from harness.e2e_stall_odometry import Detector,GATE
from harness.self_pulse_rotation import RotationPulseOdometry
from scripts.run_e2e_ownmap_live import ownmap_record


def test_expired_issued_pulse_numpy_false_can_be_saved_without_control_changes():
    driver=RotationPulseOdometry();detector=Detector(driver,GATE)
    frame=np.full((480,640,3),120,np.uint8)
    detector.command(dict(t=0.,kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1))
    for i in range(4):row=detector.observe(t=i*.4,frame_id=i,rgb=frame,servo=SEARCH,sha256='a'*64)
    assert isinstance(row['stationary'],np.bool_) and not row['stationary']
    goal=SimpleNamespace(explorer=SimpleNamespace(local_pose=np.zeros(3)),entities={},stage='explore')
    robot=SimpleNamespace(goal=goal,nav_command={'kind':'hold'},beam=None)
    trace={'stall_odometry':row};obs={'frame_id':3,'sha256':'a'*64}
    with pytest.raises(TypeError):json.dumps(ownmap_record(robot,obs,trace,1.2),allow_nan=False)
    goal.e2e_record_scalars='python_v1';record=ownmap_record(robot,obs,trace,1.2)
    assert json.loads(json.dumps(record,allow_nan=False))['stall_odometry']['stationary'] is False
    assert isinstance(row['stationary'],np.bool_)  # observational conversion never mutates the owner
    trace['bad']=object()  # unsupported data is not silently stringified
    from harness.e2e_record_scalars import normalize
    with pytest.raises(TypeError):json.dumps(normalize(trace))
    with pytest.raises(ValueError):json.dumps(normalize({'x':np.float64('nan')}),allow_nan=False)
