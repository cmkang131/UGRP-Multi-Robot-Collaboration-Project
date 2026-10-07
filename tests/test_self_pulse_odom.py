import hashlib
import json
import numpy as np
import pytest
from harness import self_pulse_odom as p
from harness.self_map_prob import V7CommandOdometry
from harness.wall_parallax import joint_pose_covariance


def test_off_byte_golden():
    a=p.command_odometry()
    b=V7CommandOdometry()
    rows=[dict(t=0.,kind='initial_servo_command',pulses={1:2000,3:740,4:2320,5:1320,6:1500}),
          dict(t=.5,kind='mecanum',forward=0.,left=.65,turn=0.,duration_s=.65)]
    for row in rows:a.command(row),b.command(row)
    for t in (1.,1.3,1.8,3.):
        a.advance(t),b.advance(t)
        assert np.array(a.pose).tobytes()==np.array(b.pose).tobytes()
        assert a.covariance.tobytes()==b.covariance.tobytes()


def test_all_original_profile_means_and_covariance():
    assert hashlib.sha256(p.MODEL.read_bytes()).hexdigest()==p.MODEL_SHA256
    for key,profile in p.model()['profiles'].items():
        d=p.PulseOdometry()
        d.command(dict(t=0.,kind='initial_servo_command',pulses={1:1500 if profile['loaded'] else 2000}))
        action=dict(t=.1,kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=profile['duration_s'])
        action[profile['axis']]=profile['u']
        d.command(action)
        for t in np.arange(.15,.1+profile['times'][-1],.05):
            d.advance(t)
            np.testing.assert_allclose(d.pose,p.response(profile,t-.1),atol=1e-13)
        d.advance(.1+profile['times'][-1])
        np.testing.assert_allclose(d.pose,profile['mean_delta'],atol=1e-13)
        assert np.linalg.eigvalsh(d.covariance).min()>0
        before=d.pose
        d.advance(d.t+1)
        assert before==d.pose


def test_unsupported_and_interrupt_are_explicit():
    d=p.PulseOdometry()
    with pytest.raises(ValueError,match='UNCALIBRATED_PULSE'):
        d.command(dict(t=0.,kind='mecanum',forward=0.,left=.651,turn=0.,duration_s=.65))
    d.command(dict(t=0.,kind='mecanum',forward=0.,left=.65,turn=0.,duration_s=.65))
    with pytest.raises(ValueError,match='EARLY_INTERRUPTION'):d.command(dict(t=.2,kind='stop'))
    d.command(dict(t=.65,kind='hold'))
    d.advance(1.)
    assert d.pose[1]>0 and d.pose[2]<0
