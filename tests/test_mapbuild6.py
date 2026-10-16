"""Non-physics regression for replay command isolation and timing."""
import math
import pytest
from scripts.mapbuild6_capture import command_delta, duty, run


def test_default_off_rejects_before_any_simulator_import():
    from types import SimpleNamespace
    with pytest.raises(ValueError,match='EXPLICIT_GCP5_ONLY'):
        run(SimpleNamespace(enabled=False))


def test_duty_preserves_wheel_impulses_and_native_dead_zone():
    # Per-wheel pulse width carries mixed steering ratios. Every nonzero
    # wheel stays at the original board speed35 instead of a sub-deadzone PWM.
    for body in ((.1,0,0),(0,.05,0),(.1,-.05,.02)):
        wheels,widths=duty(body)
        f,l,t=body;desired=(f-l-t,f+l+t,f+l-t,f-l+t)
        scale=max(.35,max(map(abs,desired)))
        for wheel,width,expected in zip(wheels,widths,desired):
            assert abs(wheel) in (0,.35)
            assert 0<=width<=.1
            if .1*abs(expected)/scale>=.001:
                assert math.isclose(wheel*width,.35*.1*expected/scale)


def test_command_prediction_uses_issued_width_and_persists_no_truth():
    command={'wheels':[.35]*4,'duration_s':[.05]*4}
    forward=command_delta(command,.1)
    # All four wheels yield translation and exactly zero yaw/lateral.
    assert math.isclose(forward[0],.0325*150*2*math.pi/60*.35*.05)
    assert forward[1:]==[0.,0.]
    assert command_delta({'wheels':[0]*4,'duration_s':[0]*4},.1)==[0.,0.,0.]


def test_chassis_alignment_removes_only_initial_se2_not_scale():
    import numpy as np
    from scripts.mapbuild6_evaluate import relative_trajectory,errors
    # World path is 1m north from a chassis facing north. A free initial
    # SE2 alignment yields 1m forward, while a wrong 2x estimate stays wrong.
    gt=relative_trajectory([[3,4,math.pi/2],[3,5,math.pi/2],[2,5,math.pi]])
    assert np.allclose(gt,[[0,0,0],[1,0,0],[1,1,math.pi/2]])
    prediction=gt.copy();prediction[:,:2]*=2
    xy,yaw=errors(prediction,gt)
    assert np.allclose(xy,[0,1,math.sqrt(2)])
    assert np.allclose(yaw,0)


def test_unqualified_loaded_camera_never_runs_lk(monkeypatch):
    import sys
    from types import SimpleNamespace
    from scripts.mapbuild6_capture import qualified_pair
    called=[]
    monkeypatch.setitem(sys.modules,'harness.servo_camera_fk',SimpleNamespace(
        transform_from_commands=lambda *a,**kw:(None,'loaded_or_unknown_load_not_qualified')))
    monkeypatch.setitem(sys.modules,'harness.e2e_rgb_vo',SimpleNamespace(ground_pair=lambda *a:called.append(a)))
    assert qualified_pair(None,None,{1:1500})=={'status':'unknown_loaded_or_unknown_load_not_qualified'}
    assert called==[]
