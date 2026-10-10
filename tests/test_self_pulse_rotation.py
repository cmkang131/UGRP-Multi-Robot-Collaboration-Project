import json
import numpy as np
import pytest
from harness import self_pulse_odom as old
from harness import self_pulse_rotation as new


def test_only_unloaded_left_yaw_mean_changes():
    a,b=old.model(),new.calibrated_model()
    for key,p in a['profiles'].items():
        q=b['profiles'][key]
        if key!='0:turn:0.35:0.10':
            assert json.dumps(p)==json.dumps(q)
            continue
        for k in p:
            if k not in ('mean_curve','mean_delta'):assert json.dumps(p[k])==json.dumps(q[k])
        np.testing.assert_array_equal(np.array(p['mean_curve'])[:,:2],np.array(q['mean_curve'])[:,:2])
        np.testing.assert_allclose(np.array(q['mean_curve'])[:,2],np.array(p['mean_curve'])[:,2]*1.1049453391322106)
        assert p['mean_delta'][:2]==q['mean_delta'][:2]
    with pytest.raises(ValueError,match='UNKNOWN'):new.selected_model('bad')


def test_cw_trajectory_and_covariance_bytes_identical():
    a=old.PulseOdometry()
    b=old.command_odometry(motion_model=new.OPTION)
    for i in range(10):
        row=dict(t=i*.2,kind='mecanum',forward=0.,left=0.,turn=-.35,duration_s=.1)
        for d in (a,b):d.command(row)
        for elapsed in (.05,.1,.15,.2):
            for d in (a,b):d.advance(i*.2+elapsed)
            assert np.array(a.pose).tobytes()==np.array(b.pose).tobytes()
            assert a.covariance.tobytes()==b.covariance.tobytes()


def test_model_connected_to_memory_and_pulse_prediction():
    from harness.active_wall_mapping import pulse_command
    from harness.active_wall_recovery import make_mapper
    from harness.active_camera import SEARCH
    a=make_mapper('r3',1.3,SEARCH,active_mapping='frontier_rbpf_v1',motion_model=new.OPTION)
    assert isinstance(a.memory.self_map.odom.driver,new.RotationPulseOdometry)
    row,p=pulse_command([0,0,.5],3.,motion_model=new.OPTION)
    assert row['turn']==.35
    profile=new.calibrated_model()['profiles']['0:turn:0.35:0.10']
    np.testing.assert_array_equal(p['predicted_delta'],profile['mean_delta'])
    a.command({**row,'t':1.3})
    a.memory.self_map.odom.advance(1.5)
    np.testing.assert_allclose(a.local_pose,profile['mean_delta'],atol=1e-13)
    assert a.memory.snapshot()['self_map_motion_model']['rotation_calibration_sha256']==new.CALIBRATION_SHA256
