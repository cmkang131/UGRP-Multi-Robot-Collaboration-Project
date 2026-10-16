"""Acquisition cadence contracts; no renderer, physics or provider calls."""
import copy
from types import SimpleNamespace
import numpy as np
import pytest
from harness.active_camera import SEARCH
from harness.e2e_observation_cadence import configure,limits
from harness.e2e_rgb_vo import VOFusion
from harness.self_pulse_rotation import RotationPulseOdometry
from tests.test_e2e_us_stall import pulse,report
from tests.test_e2e18 import options,ROOT
from scripts.run_e2e_ownmap_live import bundle


def fusion():
    d=RotationPulseOdometry();d.command(dict(t=0.,kind='initial_servo_command',pulses=SEARCH))
    return VOFusion(d,fallback='ultrasonic')


def test_default_rejects_point4_and_registered_cadence_calls_vo(monkeypatch):
    calls=[]
    monkeypatch.setattr('harness.e2e_rgb_vo.ground_pair',lambda *a,**kw:(calls.append(1) or dict(status='measured',delta=[0.,0.,0.],covariance=(np.eye(3)*1e-6).tolist())))
    for option in ('off','on_v1'):
        f=fusion();configure(SimpleNamespace(e2e_vo=f),option,.4)
        rows=[f.observe(t=i*.4,frame_id=i,rgb=np.full((480,640,3),120,np.uint8),servo=SEARCH,range_reading=report(i*.4)) for i in range(5)]
        if option=='off':assert all(r['status']=='unknown_frame_gap' for r in rows[1:])
        else:
            assert rows[-1]['status']=='measured' and calls
            r=f.observe(t=2.4,frame_id=6,rgb=np.full((480,640,3),120,np.uint8),servo=SEARCH,range_reading=report(2.4))
            assert r['status']=='unknown_frame_gap'


def test_range_cadence_keeps_freshness_and_lost_frame_checks():
    f=fusion();configure(SimpleNamespace(e2e_vo=f),'on_v1',.4);d=f.range_stall
    for i in range(5):
        d.command(pulse(i*.4));r=d.observe(t=i*.4,report=report(i*.4),servo=SEARCH,delta=(.026,0.,0.),measured=False)
    assert r['stationary'] and r['samples']==5
    assert d.observe(t=2.4,report=report(2.4),servo=SEARCH,delta=(.026,0.,0.),measured=False)['status']=='duplicate_or_gap'
    assert d.observe(t=2.8,report=report(2.5),servo=SEARCH,delta=(.026,0.,0.),measured=False)['status']=='stale_or_future'
    assert limits(.4)['max_pair_gap_s']==pytest.approx(.45)
    with pytest.raises(ValueError):limits(.8)


def test_runtime_requires_matching_registered_cadence():
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61001,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1')
    assert b['execution_bundle_id']=='e2e18-v220';require_current(b,ROOT)
    assert b['estimator_cadence']['observation_period_s']==.4
    bad=copy.deepcopy(b);bad['estimator_cadence']['max_pair_gap_s']=.25
    with pytest.raises(ValueError,match='CADENCE'):require_current(bad,ROOT)
