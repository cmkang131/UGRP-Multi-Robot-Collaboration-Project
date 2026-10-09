"""Own recorded/synthetic estimates only; no native physics or renderer."""
import copy
import json
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from harness import zone_solo_cyan_path_heading as m
from harness import zone_solo_cyan_contract_v106 as legacy
from harness import zone_s2_heading_contract as contract
from harness import zone_s2_graduation59_contract as baseline
from harness.zone_solo_cyan_pulse_cal import Runtime as Pulse, action_of
from scripts.run_s2_heading import runtime_factory


def profiles():
    return json.loads((legacy.ROOT/'configs/s2_motion_v7_pulse_cal_v1.json').read_text())['profiles']


@pytest.mark.parametrize('loaded', [False, True])
@pytest.mark.parametrize('angle', [-math.pi+1e-4, -math.pi/2, math.pi/2, math.pi-1e-4])
def test_far_goal_rotates_without_strafe_or_translation(loaded, angle):
    p, score = m.select(profiles(), loaded, [math.cos(angle), math.sin(angle)], 0, 1.)
    assert p['axis'] == 'turn' and math.copysign(1, p['u']) == math.copysign(1, angle)
    assert abs(p['u']) <= .35 and p['duration_s'] == .10
    assert score['after'] < score['before']


def test_intermediate_waypoint_never_enables_strafe_and_final_only_fine():
    p, _ = m.select(profiles(), True, [0, .04], 0, 1.)
    assert p['axis'] == 'turn'
    p, _ = m.select(profiles(), True, [0, .04], 0, .04)
    assert p['axis'] == 'left' and abs(p['u']) == .35 and p['duration_s'] == .06
    p, _ = m.select(profiles(), True, [.5, 0], 0, .5)
    assert p['axis'] == 'forward' and p['u'] > 0


def stub(cls, loaded=False):
    r = object.__new__(cls)
    r.map = legacy.hp.resolve(legacy.MAP_ID)[0]
    r.path, r.path_goal = [], None
    r.state = 'search_move'
    r.cal_rows, r.heading_rows = [], []
    r.events, r.soft_counts = [], {}
    r.robot_id = 'r3'
    r.pulse_option = 'v7_pulse_cal_v1'
    r.pulse_profiles = profiles()
    r.pose = NS(provider=NS(loc=NS(_pf=NS(load=NS(loaded=loaded)))))
    return r


def report(xy, yaw=0):
    return NS(initialized=True, x_m=xy[0], y_m=xy[1], yaw_rad=yaw,
              std_xy_m=.01, std_yaw_rad=.01, last_fix_t=0)


def test_cooperative_off_drive_paths_commands_and_events_bytes():
    a, b = stub(Pulse), stub(m._HeadingPulse)
    for xy, yaw in [((-.4,-.85),.1), ((-.3,-.83),0), ((-.2,-.6),.02)]:
        for r in (a, b):
            r.last_report = report(xy, yaw)
        assert json.dumps(a.drive((.3,-.4),1)).encode() == json.dumps(b.drive((.3,-.4),1)).encode()
        assert json.dumps(a.cal_rows).encode() == json.dumps(b.cal_rows).encode()
        assert json.dumps(a.events).encode() == json.dumps(b.events).encode()


def test_actual_v141_off_factory_record_rng_and_bundle_bytes():
    from scripts.run_s2_graduation59 import runtime_factory as old
    a = baseline.bundle('a'*40, 1066, **baseline.NEW_OPTIONS)
    b = contract.bundle('a'*40, 1066)
    assert json.dumps(a).encode() == json.dumps(b).encode()
    args = (legacy.hp.resolve(legacy.MAP_ID)[0], legacy.ROOT/legacy.CALIBRATION, legacy.CALIBRATION_SHA)
    x, y = old(a, {}, [])(*args, **a['task']), runtime_factory(b, {}, [])(*args, **b['task'])
    try:
        assert json.dumps(x.record()).encode() == json.dumps(y.record()).encode()
        assert x.pose.provider.loc._pf.rng.bit_generator.state == y.pose.provider.loc._pf.rng.bit_generator.state
        assert not hasattr(y, 'heading_mode')
    finally:
        x.close(); y.close()


def test_actual_on_stack_keeps_slip_active_rotation_envelope_and_delayed_stop():
    from harness.zone_solo_cyan_slip_recovery import Runtime as Slip
    from harness.zone_solo_cyan_unknown_start import Runtime as Unknown
    b = contract.bundle('a'*40, 1066, heading_mode=m.OPTION)
    contract.require_execution(b)
    r = runtime_factory(b, {}, [])(legacy.hp.resolve(legacy.MAP_ID)[0],
        legacy.ROOT/legacy.CALIBRATION, legacy.CALIBRATION_SHA, **b['task'])
    try:
        chain = type(r).__mro__
        assert chain.index(Unknown) < chain.index(Slip) < chain.index(m._HeadingPulse) < chain.index(Pulse)
        assert r.record()['active_rotation_guard']['parameters']['max_abs_deg'] == 90
        assert r.record()['active_localization']['gt_inputs'] is False
        r.state = 'carry'; r.cal_until = 10.1; r.cal_settled_at = 10.2
        r.last_report = NS(t_est=10.1)
        assert Pulse.step(r,10.05) == []
        assert Pulse.step(r,10.1) == [('r3',dict(kind='hold'))]
        assert Pulse.step(r,10.2) == []
    finally:
        r.close()


@pytest.mark.parametrize('loaded', [False, True])
def test_calibrated_closed_loop_north_route_finishes_without_far_strafe(loaded):
    r = stub(m._HeadingPulse, loaded)
    r.heading_mode = m.OPTION
    xy, yaw, goal = np.array([.3,-2.15]), 0., (.3,-.85)
    for i in range(500):
        r.last_report = report(xy, yaw)
        actions, done = r.drive(goal, float(i))
        if done:
            break
        a = actions[0]
        assert a['kind'] == 'mecanum', (i,xy,yaw)
        if a['left']:
            assert math.dist(xy,goal) <= .10
        p = r.pulse_profiles[r.cal_rows[-1]['profile_key']]
        d = p['mean_delta']; c,s = math.cos(yaw), math.sin(yaw)
        xy += np.array([[c,-s],[s,c]]) @ d[:2]; yaw = m.wrap(yaw+d[2])
    assert done and math.dist(xy,goal) <= .03


def test_contract_refuses_unregistered_seed_off_execution_and_unknown_mode():
    with pytest.raises(ValueError): contract.bundle('a'*40,1067,heading_mode=m.OPTION)
    with pytest.raises(ValueError): contract.bundle('a'*40,1066,heading_mode='bad')
    with pytest.raises(ValueError): contract.require_execution(contract.bundle('a'*40,1066))


def test_far_visual_alignment_replaces_strafe_and_waits_for_coast_and_estimate():
    class Previous(Pulse):
        def __init__(self, **kw):
            self.state='align'; self.target=[.6,.4]; self.robot_id='r3'
            self.last_report=NS(t_est=10.,yaw_rad=0.)
            self.pose=NS(provider=NS(loc=NS(_pf=NS(load=NS(loaded=False)))))
            self.pulse_profiles=profiles();self.fine_rows=[]
        def step(self, now):
            return [('r3',dict(kind='mecanum',forward=0.,left=.35,turn=0.,duration_s=.06))]
    r=m.runtime_class(Previous)(heading_mode=m.OPTION,pulse_motion_model='v7_pulse_cal_v1')
    rows=r.step(10.)
    assert rows[0][1]['turn']==.35 and rows[0][1]['left']==0 and rows[0][1]['duration_s']==.10
    assert r.step(10.05)==[]
    assert r.step(10.1)==[('r3',dict(kind='hold'))]
    assert r.step(10.2)==[]  # stale estimate cannot issue another pulse


def test_time_denominator_respects_early_hold_and_ignores_arm():
    from scripts.replay_s2_heading import command_time
    rows=[dict(t=0.,kind='mecanum',left=.35,duration_s=.1),
          dict(t=.01,kind='arm',pulse=1000),dict(t=.04,kind='hold'),
          dict(t=1.,kind='mecanum',forward=.35,duration_s=.1)]
    q=command_time(rows,2.)
    assert q['lateral_s']==pytest.approx(.04)
    assert q['moving_s']==pytest.approx(.14)
    assert q['lateral_fraction_moving']==pytest.approx(2/7)


def test_queue_requires_all_predecessors_even_between_free_lock_intervals():
    from scripts.run_s2_heading import queue_receipt
    names=['s2v59 preregistered six-seed DEV and one pair throughput',
           'S3 v142 single mixed no-prior smoke',
           *[f'egomap54 teach/repeat seed{s}' for s in (54001,54002,54003,54004)],
           'simspeed bounded ABBA (research first)']
    records=[dict(purpose=p,released_unix=i+1) for i,p in enumerate(names)]
    for n in range(len(records)):
        with pytest.raises(ValueError):queue_receipt(records[:n])
    assert len(queue_receipt(records)['egomap54'])==4
