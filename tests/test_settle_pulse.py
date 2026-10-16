"""Closed-loop numerical plant and saved-feature adapter; no MuJoCo/render."""
import math

import numpy as np
import pytest

from sim import release14, release17, release18, release19, release20
from sim.settle_pulse import PulseSettler, proportional_pulse
from tests.test_release18 import setup


@pytest.mark.parametrize('initial', [-.4, -.065, -.03, .03, .065, .4])
@pytest.mark.parametrize('actual_gain', [.8, 1., 1.3])
def test_noisy_closed_loop_settles_without_sustained_cycle(initial, actual_gain):
    policy = PulseSettler(.005)
    error = initial
    pulses = 0
    for i in range(100):
        observed = error + .001*math.sin(i*1.7)
        result = policy.observe(observed, .06)
        if result['settled']:
            # Remains quiet across subsequent noisy RGB samples.
            for j in range(10):
                assert policy.observe(error+.001*math.sin(j), .06)['settled']
            break
        command = proportional_pulse(observed, .06, maximum=.15)
        policy.issued(observed)
        error -= actual_gain*command
        pulses += 1
    else:
        pytest.fail('limit cycle remains')
    assert pulses < 15 and abs(error) < .09


def test_old_tolerance_reproduces_two_cycle():
    error = .03
    errors = []
    for _ in range(16):
        assert abs(error) > .025
        errors.append(error)
        error -= math.copysign(.06, error)
    assert sum(a*b < 0 for a,b in zip(errors, errors[1:])) == 15
    assert PulseSettler(.025).observe(errors[0], .06)['settled']


def test_three_actual_pulse_reversals_settle_model_mismatch():
    p = PulseSettler(.005)
    for e in (.045, -.045, .045):
        assert not p.observe(e, .05)['settled']
        p.issued(e)
    d = p.observe(-.045, .05)
    assert d['settled'] and d['reason'] == 'consecutive_reversals'
    assert d['pulses'] == d['total_reversals'] == 3
    assert not p.observe(.3, .05)['settled']  # new large motion cannot reuse latch


def test_passive_noise_or_large_alternation_cannot_trigger_reversal_acceptance():
    p = PulseSettler(.005)
    for e in [.045, -.045]*10:
        assert not p.observe(e, .05)['settled']
    assert p.total_reversals == 0
    for e in [1., -1.]*10:
        assert not p.observe(e, .05)['settled']
        p.issued(e)


def test_proportional_magnitude_floor_and_cap():
    assert proportional_pulse(.01, .04) == .04
    assert proportional_pulse(.2, .04) == .1
    assert proportional_pulse(-2., .04, maximum=.15) == -.15
    with pytest.raises(ValueError): proportional_pulse(float('nan'), .04)
    assert proportional_pulse(.01, .04, quantize=False) == .005


def test_saved_78526_coupled_pulse_is_not_quantized_twice():
    import json
    from pathlib import Path
    from sim.lookaround_localization import Camera
    from tests.test_release_regrasp import teachers
    d=json.loads((Path(__file__).parent/'fixtures/release20_quantization.json').read_text())
    t=teachers()['r1'];t.pwm={int(k):v for k,v in d['pwm'].items()};t.odometry_profile='yaw_cal_v1'
    a=release20.LineAlign(t,122.7,camera=Camera(),undistort=lambda f:f,wheel_command=lambda *args:None,
                          clearance=lambda *args:True,fov_step=release17.FOV_STEP)
    old=release17.line_step(d['feature'],Camera(),t.pwm,clearance=lambda *args:True,profile='yaw_cal_v1')
    step=a.choose_step(d['feature'],.1,122.7)
    assert not step['aligned'] and step['kind']=='line_ibvs'
    assert [step['left'],step['yaw']]==pytest.approx([old['left'],old['yaw']],abs=1e-12)
    w,d,_=release17.yaw_pulse_for(0.,step['left'],step['yaw'],'yaw_cal_v1')
    assert w==[-.35,.35,.35,-.35] and d==[.04]*4  # pure lateral, no introduced yaw


def test_release_adapter_keeps_wait_and_fresh_stability_and_resets_on_missing():
    a,t,h,issued,scheduled = setup()
    a.__class__ = release20.LineAlign
    a.settlers = [PulseSettler(.025), PulseSettler(.06)]
    a.last_quantum = None
    from tests.test_release_regrasp import stripe
    for now in (3., 3.1, 3.2, 3.3):
        h.observe(t.pwm, now)
        status = a.tick(now, lambda *args: stripe(), lambda *args: scheduled.append(args))
        assert (status == 'ready') == (now == 3.3)
    assert not issued and not scheduled
    assert len([e for e in a.records if e['event']=='release20_settle']) == 4
    a.choose_step(dict(valid=False), .1, 4.)
    assert all(s.band is None for s in a.settlers)


@pytest.mark.parametrize('profile', [release18.PROFILE, release19.PROFILE])
def test_toggle_composes_with_wait_reuse_and_training_remains_blocked(profile):
    opts = {**release14.SAFE, 'command_motion':'yaw_cal_v1',
            'release20_settle':release20.SETTLE, 'release_settle_reuse':release18.REUSE}
    plan = dict(end_color_scene='grasp_act_teal_blue_v1')
    release20.validate(profile, False, opts, plan)
    with pytest.raises(ValueError): release20.validate(profile, True, opts, plan)
    with pytest.raises(ValueError): release20.validate('off', False, opts, plan)
    with pytest.raises(ValueError): release20.validate(profile, False, {**opts,'command_motion':'off'}, plan)


def test_rejected_pulse_does_not_enter_command_history(monkeypatch):
    a,t,h,issued,scheduled = setup()
    a.__class__ = release20.LineAlign
    a.settlers = [PulseSettler(.025), PulseSettler(.06)]
    a.last_quantum = None
    # Pixel adapter exercises the actual parent's clearance rejection.
    from tests.test_release_regrasp import stripe
    a.clearance = lambda *args: False
    a.tick(3., lambda *args: stripe(70), lambda *args: None)
    assert all(s.pulses == 0 for s in a.settlers)
