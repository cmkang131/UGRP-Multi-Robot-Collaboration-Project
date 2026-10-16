"""v5h raw command clock regression: saved 158 reports, fake ports/providers only."""
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from harness.owncam_pose_source import PoseReport
from harness.zone_own_guards import GATE_LOADED, UncertaintyGate
from harness.zone_own_team_host import OwnCamTeamHost
from harness.zone_pair_guards import PairCommandGuard

FIX = Path(__file__).parent / 'fixtures/zone_pair_v5h'
DATA = json.loads((FIX / 'reports.json').read_text())


def guard_host():
    events, issued = [], []
    own = NS(robot_id='r2', now=0., servo={1: 2000, 3: 770, 4: 1982, 5: 1876, 6: 1500},
             last_report=PoseReport(0., True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01, std_yaw_rad=.01),
             gate=UncertaintyGate(GATE_LOADED))
    # Establish LOW through the real dwell, without inferring it from fix age.
    own.gate.update(-1., True, .01, .01)
    own.gate.update(0., True, .01, .01)
    ep = NS(own=own, controller=NS(driver=None, state='align_relook_stop', seg=0),
            log=lambda rid, event, now, **kw: events.append(dict(event=event, now=now, **kw)))
    guard = PairCommandGuard(ep)
    own.on_command = guard.on_command
    port = NS(hold=lambda now: issued.append(now), apply=lambda action, now: issued.append(now))
    host = OwnCamTeamHost.__new__(OwnCamTeamHost)
    host.robots = {'r2': NS(commands=[], executor=own, port=port)}
    return host, guard, own, events, issued


def saved_report(row):
    r = row['report']
    return PoseReport(t_est=r['t_est'], initialized=r['initialized'],
                      x_m=r['xyyaw'][0], y_m=r['xyyaw'][1], yaw_rad=r['xyyaw'][2],
                      **{k: r[k] for k in ('std_xy_m', 'std_yaw_rad', 'last_fix_t', 'fix_age_s',
                                          'fix_source', 'source', 'observation_quality')})


@pytest.mark.parametrize('run', DATA['runs'], ids=lambda r: r['id'])
def test_all_158_saved_reports_reproduce_old_stop_deadlock_and_pass_raw_host(run):
    source = (FIX / DATA['baseline']['file']).read_bytes()
    assert hashlib.sha256(source).hexdigest() == DATA['baseline']['sha256']
    old = {}; exec(compile(source, '<exact v5g host methods>', 'exec'), old)
    stopped_at = run['stop_event']['sim_s']
    outcomes = []
    for legacy in (True, False):
        host, guard, own, events, issued = guard_host()
        drive, hold = [x['row'] for x in run['commands']]
        # The old issued drive is deliberately left byte-for-byte unchanged.
        # Replay the hold at the separately saved raw controller start time.
        guard.on_command(drive)
        (old['_hold'] if legacy else OwnCamTeamHost._hold)(host, 'r2', stopped_at)
        assert issued == [stopped_at]
        assert guard.motion_until == (hold['t'] if legacy else stopped_at)
        passed = 0
        for row in run['reports']:
            own.last_report = saved_report(row)
            own.gate.update(row['now'], True, own.last_report.std_xy_m, own.last_report.std_yaw_rad)
            assert own.gate.ok
            passed += guard.align_stop_ready(row['now'], stopped_at)
            if legacy:
                assert events[-1]['failed_checks'] == ['motion_ended_at_stop']
            # Passing the STOP stage is not a new accepted fix or relook success.
            assert own.last_report.last_fix_t < stopped_at
        outcomes.append(passed)
    assert len(run['reports']) == 79 and outcomes == [0, 79]


@pytest.mark.parametrize('raw', [184.3999999973675, 168.69999999773876, 2.000049, 2.000051])
def test_both_rounding_directions_keep_port_command_and_stop_identical(raw):
    host, guard, own, events, issued = guard_host()
    host._apply('r2', {'kind': 'mecanum', 'forward': .08, 'left': 0., 'turn': 0.,
                       'duration_s': .3, 't': -999.}, raw)
    assert host.robots['r2'].commands[-1]['t'] == raw  # action cannot replace host time
    assert guard.motion_until == raw + .3
    stop = raw + .1
    host._hold('r2', stop)
    assert guard.motion_until == stop and issued == [raw, stop]
    own.last_report = replace(own.last_report, t_est=round(stop + .1, 4))
    assert guard.align_stop_ready(stop + .1, stop)
    assert not events
    assert guard.before_control(stop + .1)


@pytest.mark.parametrize('dt,ok', [(-.000099, True), (.000099, True), (-.000101, False)])
def test_report_quantization_contract_is_unchanged(dt, ok):
    host, guard, own, events, _ = guard_host()
    host._apply('r2', dict(kind='drive', forward=.1, turn=0., duration_s=1.), 1.5)
    host._hold('r2', 2.)
    own.last_report = replace(own.last_report, t_est=2. + dt)
    assert guard.align_stop_ready(2.1, 2.) is ok
    if not ok:
        assert 'report_after_stop' in events[-1]['failed_checks']


@pytest.mark.parametrize('fault,failed', [
    ('moving', 'motion_ended_at_stop'), ('same_tick', 'after_stop'),
    ('pre_stop', 'report_after_stop'), ('uninitialized', 'initialized'),
    ('stale', 'report_fresh'), ('future', 'report_fresh'),
    ('high_xy', 'pose_bounded'), ('high_yaw', 'pose_bounded'), ('dwell', 'gate_ok'),
])
def test_stop_wait_logs_failed_conditions_and_preserves_rejections(fault, failed):
    host, guard, own, events, _ = guard_host()
    host._apply('r2', dict(kind='drive', forward=.1, turn=0., duration_s=1.), 1.5)
    if fault != 'moving': host._hold('r2', 2.)
    now = 2. if fault == 'same_tick' else 2.1
    own.last_report = replace(own.last_report, t_est=now)
    changes = {'pre_stop': {'t_est': 1.99}, 'uninitialized': {'initialized': False},
               'stale': {'t_est': 1.7}, 'future': {'t_est': 2.2},
               'high_xy': {'std_xy_m': .071}, 'high_yaw': {'std_yaw_rad': math.radians(3.01)}}
    own.last_report = replace(own.last_report, **changes.get(fault, {}))
    if fault == 'dwell':
        own.gate = UncertaintyGate(GATE_LOADED)
        own.gate.update(2., True, .01, .01)
        own.gate.update(now, True, .01, .01)
    assert not guard.align_stop_ready(now, 2.)
    row = events[-1]
    assert row['event'] == 'align_relook_stop_wait' and failed in row['failed_checks']
    assert row['failed_checks'] == [k for k, v in row['checks'].items() if not v]
    assert (row['stopped_at_s'], row['motion_until_s'], row['report_t']) == (2., guard.motion_until, own.last_report.t_est)
    if fault == 'dwell':
        own.gate.update(2.4, True, .01, .01)
        own.last_report = replace(own.last_report, t_est=2.4)
        assert guard.align_stop_ready(2.4, 2.)


def test_actual_unended_motion_one_nanosecond_is_still_rejected():
    host, guard, own, events, _ = guard_host()
    host._apply('r2', dict(kind='drive', forward=.1, turn=0., duration_s=.1), 2.)
    stop = guard.motion_until - 1e-9
    own.last_report = replace(own.last_report, t_est=round(stop, 4))
    assert not guard.align_stop_ready(stop + .1, stop)
    assert 'motion_ended_at_stop' in events[-1]['failed_checks']


@pytest.mark.parametrize('raw', [2.000049, 2.000051])
def test_raw_host_clock_prevents_beam_reset_and_pose_guard_backward_time(raw):
    from harness.owncam_pose_guard_v3 import PoseGuardV3
    host, guard, own, _, _ = guard_host()
    track = guard.beam_track
    track.t = raw
    track.beam = dict(grip_base_m=[.1, 0.], axis_heading_rad=0., std_xy_m=.01, std_yaw_rad=.01)
    confidence = PoseGuardV3()
    confidence.advance(raw)
    def consume(row):
        guard.on_command(row)
        confidence.on_command(row, {})
    own.on_command = consume
    host._hold('r2', raw)
    track.advance(raw)
    confidence.advance(raw)
    assert track.beam is not None and track.t == confidence.command_t == raw
    assert confidence.command_travel_m == 0.


class MarkerlessFakeProvider:
    """No landmark IDs/detector/model; accepts only explicitly injected fake fixes."""
    source = 'fake_geometry_pose'
    def __init__(self, report):
        self.loc, self.current, self.resets = NS(command=lambda row: None), report, []
    def expected_observability(self, pose, pan, static): return 1.
    def begin_relocalization(self, now, servo):
        self.resets.append(now)
        self.loc = NS(command=lambda row: None)
    def report(self, now): return self.current
    def on_command(self, row): pass


@pytest.mark.parametrize('fault,ok', [(None, True), ('no_fix', False), ('rejected', False),
    ('high_sigma', False), ('dwell', False), ('before', False), ('at_start', False), ('future', False)])
def test_markerless_provider_stop_reset_and_raw_fix_boundaries(monkeypatch, fault, ok):
    from tests.test_zone_pair_grasp import real_pair
    from harness.wall_tags import TagDetector
    from harness.owncam_localizer import OwnCamLocalizer
    host, _, eps = real_pair(); ep = eps['r1']; ctl, own = ep.controller, ep.own
    def forbidden(*args, **kwargs): pytest.fail('relook tried to initialize a marker provider')
    monkeypatch.setattr(TagDetector, 'for_map', forbidden)
    monkeypatch.setattr(OwnCamLocalizer, '__init__', forbidden)
    start = 2.000049
    fake = MarkerlessFakeProvider(replace(own.last_report, t_est=round(start, 4), source='fake_geometry_pose',
                                         last_valid_obs=None, last_fix_t=start-.1, fix_age_s=.1,
                                         fix_source='geometry', observation_quality={'accepted': False}))
    own.pose = fake
    ctl.driver._shared_pose = fake
    own.last_report = fake.report(start)
    own.now = start
    # Drive -> actual host hold -> wait -> reset: production controller path.
    host._apply('r1', dict(kind='drive', forward=.01, turn=0., duration_s=.3), start-.1)
    ctl.set('align', start)
    host._hold('r1', start)
    ctl._align_relook_stop(start+.1, True)
    assert ctl.state == 'align_relook' and fake.resets == [start+.1]
    now = start+1.
    fields = dict(t_est=round(now,4), last_fix_t=now, fix_age_s=0., observation_quality={'accepted': True})
    if fault in ('no_fix', 'rejected'):
        fields.update(last_fix_t=None if fault=='no_fix' else start-.1,
                      observation_quality={'accepted': False})
    elif fault == 'high_sigma': fields['std_xy_m'] = .051
    elif fault == 'dwell':
        own.gate = UncertaintyGate(GATE_LOADED)
        own.gate.update(now, True, .01, .01)
    elif fault == 'before': fields['last_fix_t'] = start-1e-9
    elif fault == 'at_start': fields['last_fix_t'] = start
    elif fault == 'future': fields['last_fix_t'] = now+1e-9
    fake.current = replace(fake.current, **fields)
    own.last_report = fake.report(now)
    assert ctl._align_fix_ready(now) is ok
    assert ctl.align_look_count == 1 and ctl.align_look_total_s == 0.
    if fault == 'dwell':
        own.gate.update(now+.4, True, .01, .01)
        own.last_report = replace(own.last_report, t_est=round(now+.4,4))
        assert ctl._align_fix_ready(now+.4)


@pytest.mark.parametrize('now', [1.00049, 1.00051])
def test_memory_fix_capture_is_raw_and_never_rounded_across_look_start(now):
    from harness.owncam_memory import OwnCamMemory, LOOK_P20
    from harness.owncam_landmarks import GeometricLandmarkProvider
    from tests.test_owncam_memory import tagged, params, report
    static = tagged('zone_wide_door_tags_v1'); static.pop('landmarks', None)
    mem = OwnCamMemory(static, params(), robot_id='r1', detect=lambda *a: [],
                       provider=GeometricLandmarkProvider(detector=lambda *a: []))
    lid = next(iter(mem.catalogue.by_id))
    # Generic static-geometry observation; no tag metadata or model calls.
    mem.provider.observe = lambda *a, **kw: [dict(landmark_id=lid, landmark_type='wall_face',
        feature_id='edge', range_m=1., azimuth_rad=0., elevation_rad=0.)]
    mem.observe_frame(now, frame_id=1, image=None, servo={**LOOK_P20, 1:2000, 6:1500},
                      report=report(0.,0.,0.), arm_settled_s=1., loaded=False)
    assert mem.last_fix['t'] == mem.last_look_fix['t'] == now
    assert mem.look_fix_since(now) and not mem.look_fix_since(now+.00001)
