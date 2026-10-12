"""Pure controller / fake backend contracts. No physics, renderer or provider call."""
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness.active_camera import SEARCH
from harness.e2e_us_stall import OPTION, RangeStall
from harness.e2e_rgb_vo import VOFusion
from harness.range_provider import OwnUltrasonicRangeProvider
from harness.ultrasonic_model import RangeReading
from harness.self_pulse_rotation import RotationPulseOdometry


def report(t, r=.1):
    p = OwnUltrasonicRangeProvider()
    p.on_reading(RangeReading(t, r, True, 'ok'))
    return p.report(t)


def pulse(t, **kw):
    return dict(t=t, kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1, **kw)


def warm(detector, *, readings=None, measured=False, servo=SEARCH, delta=(.013, 0., 0.)):
    for i in range(5):
        detector.command(pulse(i*.2))
        row = detector.observe(t=i*.2, report=report(i*.2, .1 if readings is None else readings[i]),
                               servo=servo, delta=delta, measured=measured)
    return row


def test_stationary_window_needs_resolvable_forward_motion_and_not_just_equal_distance():
    d = RangeStall()
    out = warm(d, readings=[.1, .102, .099, .101, .1])
    assert out['stationary'] and out['expected_m'] == pytest.approx(.052)
    assert not warm(RangeStall(), delta=(.001, 0., 0.))['stationary']
    assert not warm(RangeStall(), readings=[.16, .147, .134, .121, .108])['stationary']
    assert not warm(RangeStall(), readings=[1.]*5)['stationary']
    assert not warm(RangeStall(), measured=True)['stationary']
    assert not warm(RangeStall(), servo={**SEARCH, 1: 1500})['stationary']


@pytest.mark.parametrize('change', [dict(valid=False), dict(status='blind'), dict(status='no_echo'),
    dict(status='sensor_absent'), dict(range_m=float('nan')), dict(range_m=.019), dict(range_m=4.1),
    dict(t_meas=.8), dict(t_meas=1.1), dict(sigma_m=float('inf')), dict(source='unknown')])
def test_invalid_stale_future_or_duplicate_cannot_suppress_and_clears_window(change):
    d = RangeStall();assert warm(d)['stationary']
    out = d.observe(t=1., report=dataclasses.replace(report(1.), **change), servo=SEARCH,
                    delta=(.013, 0., 0.), measured=False)
    assert not out['stationary'] and not d.frames


@pytest.mark.parametrize('action', [dict(kind='hold'), dict(kind='stop'),
    dict(kind='mecanum', forward=-.35), dict(kind='mecanum', left=.35), dict(kind='mecanum', turn=.35),
    dict(kind='look', pan_pulse=1500), dict(kind='arm', servo_id=1, pulse=1500)])
def test_nonforward_commands_release_without_a_latched_zero(action):
    d = RangeStall();assert warm(d)['stationary']
    d.command(dict(t=1., **action))
    assert not d.frames and d.direction is None


def run_fusion(*, ranges=True, measured=False, fallback='ultrasonic', monkeypatch):
    if measured:
        monkeypatch.setattr('harness.e2e_rgb_vo.ground_pair', lambda *a: dict(
            status='measured', delta=[.0129, 0., 0.], covariance=(np.eye(3)*1e-6).tolist()))
    d = RotationPulseOdometry();d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    f = VOFusion(d, fallback=fallback);active = [False]
    d.motion_filter = lambda delta, q: f.motion_filter(delta, q) if active[0] else (delta, q)
    rows=[]
    for i in range(12):
        t = i*.2
        rows.append(f.observe(t=t, frame_id=i, rgb=np.full((480, 640, 3), 120, np.uint8),
                              servo=SEARCH, range_reading=report(t) if ranges else None))
        active[0]=True
        d.advance(t);active[0]=False;f.finish_interval()
        f.command(pulse(t));d.command(pulse(t))
    return d, f, rows


def test_zupt_applies_to_real_odom_driver_preserves_yaw_and_inflates_q(monkeypatch):
    d, f, rows = run_fusion(monkeypatch=monkeypatch)
    zeros = [r for r in rows if r['fusion']=='us_zero']
    assert len(zeros) == 7
    assert f.counts['substep_mismatch']==0 and d.pose[0] < f.nominal.pose[0]*.5
    for r in zeros:
        assert r['fused_delta'][:2] == [0., 0.]
        assert r['fused_delta'][2] == r['command_delta'][2]
        assert all(v > 0 for v in r['fused_variance'])
    assert np.trace(d.covariance) > np.trace(f.nominal.covariance)


def test_vo_priority_and_missing_range_exact_v2_fallback(monkeypatch):
    _, _, rows = run_fusion(measured=True, monkeypatch=monkeypatch)
    assert all(r['fusion'] in ('fused', 'vo_replaced') for r in rows if r['status']=='measured')
    a, _, ar = run_fusion(ranges=False, monkeypatch=monkeypatch)
    b, _, br = run_fusion(ranges=False, fallback='pulse_gate', monkeypatch=monkeypatch)
    assert a.pose == b.pose
    assert [(r['fusion'],r['fused_delta']) for r in ar] == [(r['fusion'],r['fused_delta']) for r in br]


def test_changed_rgb_vetoes_constant_range_zero_update_and_clears_window(monkeypatch):
    monkeypatch.setattr('harness.e2e_stall_odometry.flow_pair',lambda *a: dict(
        status='changed_view',tracks=30,cells=6,median_px=2.,p90_px=4.))
    d,f,rows=run_fusion(monkeypatch=monkeypatch)
    moving=[r for r in rows if r['gate']['status']=='changed_view']
    assert moving and all(r['ultrasonic']['status']=='rgb_motion_veto' for r in moving)
    assert all(r['fusion']=='command_kept' for r in moving)
    assert f.counts['us_zero']==0 and not f.range_stall.frames
    np.testing.assert_allclose(d.pose,f.nominal.pose,atol=1e-12)


def test_live_wrapper_consumes_only_own_range_and_injects_zero_into_callback():
    from harness.e2e_rgb_vo import install
    d=RotationPulseOdometry();d.command(dict(t=0.,kind='initial_servo_command',pulses=SEARCH))
    steps=[];d.step_callback=lambda delta,q:steps.append(delta.copy())
    def receive(**kw):
        assert 'own_range' not in kw
        return {'kind':'hold'},{}
    goal=SimpleNamespace(robot_id='r1',command=d.command,receive=receive,
        explorer=SimpleNamespace(memory=SimpleNamespace(self_map=SimpleNamespace(
            odom=SimpleNamespace(driver=d,advance=d.advance)))))
    install(goal,OPTION)
    for i in range(9):
        t=i*.2
        _,trace=goal.receive(robot_id='r1',t=t,frame_id=i,rgb=np.full((480,640,3),120,np.uint8),
                             servo=SEARCH,frame_sha256=str(i),own_range=report(t))
        goal.command(pulse(t))
    assert trace['stall_odometry']['fusion']=='us_zero'
    assert np.linalg.norm(trace['stall_odometry']['applied_delta'][:2])<1e-12
    assert all(np.linalg.norm(s[:2])<1e-12 for s in steps[-4:])
    with pytest.raises(ValueError,match='PEER_INPUT'):
        goal.receive(robot_id='r2',t=2.,frame_id=10)


def config(**extra):
    from scripts.run_e2e_ownmap_live import bundle
    return bundle('test-sha',61001,'study_gemma4_31b_v1',enabled=True,
        exploration_progress='frontier_progress_v1',boundary_views='candidate_views_v1',
        b_marker_detect='contrast_v1', **extra)


def test_registered_sensor_bundle_and_baseline_and_relay_admission():
    from harness.e2e_stall_odometry import Options
    from scripts.s4_proxy_relay import accepted_call_id
    from harness.zone_study_contract import CONDITIONS
    from harness.range_provider import provider_config_for_condition
    from harness.ultrasonic_input import REGISTERED_RANGE_CONSUMERS
    assert Options().stall_odometry == 'off'
    b=config(stall_odometry=OPTION,ultrasonic_front='on_v1')
    assert (b['execution_bundle_id'],b['workflow_version'])==('e2e-usstall-v206','7.99.0')
    assert b['sensors']['ultrasonic_front']['profile']=='on_v1'
    assert OPTION in b['sensors']['ultrasonic_front']['controller_use']
    assert 'sim/e2e_us_input.py' in b['source_sha256'] and OPTION in REGISTERED_RANGE_CONSUMERS
    assert len({json.dumps(provider_config_for_condition(c),sort_keys=True) for c in CONDITIONS})==1
    base=config(stall_odometry='rgb_vo_v2')
    assert base['execution_bundle_id']=='e2e-combo14-vo2-v205' and 'sensors' not in base
    with pytest.raises(ValueError):config(stall_odometry=OPTION)
    with pytest.raises(ValueError):config(stall_odometry='rgb_vo_v2',ultrasonic_front='on_v1')
    with pytest.raises(ValueError):Options(OPTION,stall_recovery='backup_replan_v1')
    for arm in 'ab':
        for seed in range(61001,61004):assert accepted_call_id(f'e2e-usstall-{arm}-s{seed}:call-0001-r1:1')
    assert not accepted_call_id('e2e-usstall-a-s61004:call-0001-r1:1')


def test_sensor_adapter_clock_ownership_history_and_close_without_physics(monkeypatch,tmp_path):
    pytest.importorskip('mujoco', exc_type=ModuleNotFoundError)
    from sim import e2e_us_input as adapter
    events=[]
    class Rig:
        def __init__(self, model, data, robots, *, episode_seed, range_input):self.input=range_input
        def provider(self,rid):return self.input.provider(rid)
        def tick(self,t):
            events.append(('tick',t))
            for i,rid in enumerate(('r1','r2')):self.input.feed(rid,RangeReading(t,.1+i,True,'ok'))
        def close(self):self.input.close();events.append(('close',))
    monkeypatch.setattr(adapter,'OwnUltrasonicRig',Rig)
    backend=SimpleNamespace(now=1.3,world=SimpleNamespace(model=None,data=None))
    def advance(t):backend.now=t;events.append(('advance',t))
    backend.advance_to=advance;backend.close=lambda:events.append(('backend_close',))
    robots={r:SimpleNamespace() for r in ('r1','r2')}
    adapter.attach(backend,robots,seed=61001,out=tmp_path)
    backend.advance_to(1.5)
    assert events[-2:]==[('advance',1.5),('tick',.2)]
    assert robots['r1'].range_provider.report(.2).range_m==.1
    assert robots['r2'].range_provider.report(.2).range_m==1.1
    backend.close();assert events[-2:]==[('close',),('backend_close',)]
    assert len((tmp_path/'robots/r1/inputs/range.jsonl').read_text().splitlines())==3
