"""v96 HIGH raise/carry/lower state machine on RECORDED own RGB (no synthetic images).

Every own image is a recorded floor_light_v1 wrist frame (renderer ON, seed
911, no controller; tests/fixtures/highpose_recorded_frames, sha256 checked).
The frame for a tick is the recorded frame of the same robot whose issued
servo is nearest to the controller's issued servo. Ground-truth labels in the
manifest are provenance only and never read here.

v96 first-E2E scope (user decision 2026-10-03, "ㅇㅇ 그렇게 하자"): the grip
monitor is LOG-ONLY. Barrier readiness and phase progress come from the
robot's own command history plus the fixed-enum partner status.
"""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import zone_pair_highpose_grip as grip
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_runtime as runtime
from harness.zone_pair_highpose_runtime import HighController
from harness.zone_pair_highpose_timing import CHECKPOINT_REOBSERVE_S
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint
from scripts import study_owncam_pair_beam as legacy
from scripts.zone_teacher import ArmSequence

FIX = Path(__file__).parent/'fixtures'/'highpose_recorded_frames'
MANIFEST = json.loads((FIX/'manifest.json').read_text())
_CACHE = {}


def recorded(rid, servo, condition):
    rows = [f for f in MANIFEST['frames'] if f['rid'] == rid and f['condition'] == condition]
    f = min(rows, key=lambda f: (int(f['issued_servo']['1']) != servo.get(1, 1500),
                                 sum(abs(int(f['issued_servo'][str(s)])-servo[s]) for s in (3, 4, 5, 6)), f['t']))
    if f['file'] not in _CACHE:
        data = (FIX/f['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f['sha256']
        _CACHE[f['file']] = (base64.b64encode(data).decode(), f['sha256'])
    return _CACHE[f['file']]


def test_fixture_is_recorded_render_not_synthetic():
    assert MANIFEST['render'] is True and MANIFEST['controller'] is None
    assert MANIFEST['source_root'].startswith('/Users/changmin/projects/ugrp/outputs/pr363-render-frames-')
    conds = {(f['condition'], f['rid']) for f in MANIFEST['frames']}
    assert conds == {('nominal', 'r1'), ('nominal', 'r2'), ('raise_grip_loss', 'r2')}
    for f in MANIFEST['frames']:
        assert hashlib.sha256((FIX/f['file']).read_bytes()).hexdigest() == f['sha256']


class Controller(HighController, legacy.PairStudent):
    def __init__(self, rid, bus, segments=(.1,)):
        self.ep = PairStatusEndpoint(bus, rid)
        issued = {1: 1500, **pose.grasp_postures()[0]}
        self.events, self.issued_log, self.frame, self.slip = [], [], 0, False
        self.port = SimpleNamespace(own=SimpleNamespace(servo=issued, last_report=None,
            pose=SimpleNamespace(provider=SimpleNamespace(beam_edge=SimpleNamespace(available=lambda now: True)),
                                 begin_relocalization=lambda t, servo: self.events.append(
                                     {'event': 'relocalize', 't': t, 'servo': dict(servo)}))))
        self.port.hold = lambda now: self.issued_log.append((now, {'kind': 'hold'}))

        def apply(action, now):
            self.issued_log.append((now, dict(action)))
            if action['kind'] == 'arm':
                issued[action['servo_id']] = action['pulse']
            elif action['kind'] == 'look':
                issued[6] = action['pan_pulse']
        self.port.apply = apply
        arm = ArmSequence(self.port, issued)
        legacy.PairStudent.__init__(self, rid, self.port, arm,
            lambda key: self.ep.sync_for(f'{key}@{self.seg}'),
            lambda rid, event, t, **kw: self.events.append({'event': event, 't': t, **kw}),
            status=(bus, self.ep), hold_check='fullframe_v3')
        self.seg, self.segments = 0, list(segments)
        self.grip_monitor = grip.GripMonitorLog()
        self.grip_epoch = self.grip_closed_epoch = 1       # close was issued in this epoch
        self.pose_anchors, self.transit = {}, None
        self.high_raising = self.high_ready = self.floor_return_verified = False
        self.hover, self.descent = pose.grasp_postures()
        self.grasp_pose = self.descent[-1]
        self.grasp_estimate = [0., 0., 0.]
        self.state = 'lift'                                 # lift barrier GO, hover queued and reached
        self._anchor('floor', self.observation(0., {1: 1500, **self.grasp_pose}), 0.)

    def observation(self, now, servo=None):
        self.frame += 1
        servo = dict(self.port.own.servo if servo is None else servo)
        cond = 'raise_grip_loss' if self.slip and self.rid == 'r2' else 'nominal'
        image, sha = recorded(self.rid, servo, cond)
        return {'robot_id': self.rid, 'sim_time': now, 'frame_id': self.frame, 'sha256': sha,
                'image': image, 'actuator_state': {'servo_pulses': servo}}

    def look(self, now):
        return self.observation(now)


@pytest.fixture(autouse=True)
def short_route(monkeypatch):
    monkeypatch.setattr(legacy, 'build_schedule',
                        lambda rid, t: [(t, t+.2, {'forward': .01, 'left': 0., 'turn': 0.})])


def pair(segments=(.1,)):
    bus = PairStatusChannel('high-transit')
    ctls = [Controller(r, bus, segments) for r in ('r1', 'r2')]
    for c in ctls:
        c.ep.tick('ready', 0.)          # both were in wait_lift when the lift barrier passed
    return bus, ctls


def run(ctls, *, until, fresh_after=None, slip_from=None, no_fix=()):
    """Real tick() (status publish, partner-abort reaction, handlers) + arm ticks."""
    for i in range(int(round(until/.1))+1):
        now = round(i*.1, 8)
        for c in ctls:
            if slip_from is not None and c.rid == 'r2' and now >= slip_from:
                c.slip = True
            if (fresh_after is not None and c.rid not in no_fix
                    and getattr(c, 'checkpoint_fix_after', None) is not None
                    and now-c.checkpoint_started >= fresh_after):
                c.port.own.last_report = SimpleNamespace(t_est=now, initialized=True, last_fix_t=now,
                    std_xy_m=.01, std_yaw_rad=.01, x_m=0., y_m=0., yaw_rad=0.)
            if c.state not in ('failed', 'released', 'done'):
                c.tick(now)
        for c in ctls:
            if c.state != 'failed':
                c.arm.tick(now)          # the open command queued at the open GO
    return ctls


def opened(c):
    return any(a.get('servo_id') == 1 and a.get('pulse') == legacy.OPEN for _, a in c.issued_log)


def kinds(c):
    return {row['kind'] for row in c.grip_monitor.export()}


def test_recorded_nominal_run_releases_with_command_history_readiness():
    _, ctls = pair()
    run(ctls, until=45.)
    for c in ctls:
        assert c.failure is None and c.state == 'released' and opened(c)
        carry = [e for e in c.events if e['event'] == 'barrier_report' and e['barrier'] in ('carry', 'lower', 'open')]
        assert carry and all(e['ready'] for e in carry)
        assert all('own command history' in e['reason'] for e in carry)
        assert {'anchor', 'transit_view', 'high_view', 'hold_view', 'floor_return_view', 'low_lift_view'} <= kinds(c)
        # The retired visual floor-return check would have refused this run:
        # the recorded floor grasp view shows no beam (empty anchor mask).
        floor = [r for r in c.grip_monitor.export() if r['kind'] == 'floor_return_view']
        assert floor[0]['anchor_mask_px'] == 0 and floor[0]['anchor_iou'] < floor[0]['legacy_min_iou']


def test_recorded_r2_grip_loss_frames_are_logged_not_acted_on():
    # v96 scope: a dropped beam is NOT detected or signalled in-run.
    _, ctls = pair()
    run(ctls, until=45., slip_from=0.)
    assert all(c.failure is None and c.state == 'released' for c in ctls)
    r2 = ctls[1].grip_monitor.export()
    assert {r['frame_sha256'] for r in r2 if r['kind'] == 'high_view'} <= {
        f['sha256'] for f in MANIFEST['frames'] if f['condition'] == 'raise_grip_loss'}


class WriteOnlySink:
    """Any read other than record() raises: proves the controller never reads it."""

    def __init__(self):
        object.__setattr__(self, '_rows', [])

    def record(self, *args, **kwargs):
        self._rows.append((args, kwargs))

    def __getattr__(self, name):
        raise AssertionError(f'controller read grip monitor attribute {name!r}')


def trajectory(ctls):
    return [([(t, a) for t, a in c.issued_log],
             [(e['t'], e['state']) for e in c.events if e['event'] == 'state'],
             [(e['t'], e['barrier'], e['ready']) for e in c.events if e['event'] == 'barrier_report'])
            for c in ctls]


def test_monitor_values_are_eval_only_and_never_change_control(monkeypatch):
    _, base = pair()
    run(base, until=45.)
    _, adv = pair()
    for c in adv:
        c.grip_monitor = WriteOnlySink()
    for c in adv:
        if c.transit is not None:
            c.transit.sink = c.grip_monitor
    # Adversarial monitor values: every visual check says "lost".
    from harness import owncam_pair_hold_v3 as hv3
    monkeypatch.setattr(grip, 'relation', lambda image, servo: {'ok': False, 'reason': 'ADVERSARIAL'})
    monkeypatch.setattr(hv3, 'hold_iou', lambda anchor, image: 0.)
    monkeypatch.setattr(legacy.ob, 'signature_iou', lambda a, b: 0.)
    monkeypatch.setattr(runtime, 'edge_line', lambda rgb: None)
    run(adv, until=45.)
    assert trajectory(adv) == trajectory(base)
    assert all(c.state == 'released' for c in adv)
    assert all(len(c.grip_monitor._rows) > 0 for c in adv)


def test_records_export_monitor_as_eval_output_only(monkeypatch):
    _, ctls = pair()
    run(ctls, until=20.)
    monkeypatch.setattr(runtime.previous.Team, 'records', lambda self: [{'robots': {}}])
    team = object.__new__(runtime.Team)
    team.sessions = [{'endpoints': {c.rid: SimpleNamespace(controller=c) for c in ctls}}]
    out = runtime.Team.records(team)[0]['grip_monitor']
    assert out['scope'] == 'log_only_v96' and out['in_run_grip_loss_detection'] is False
    for rid in ('r1', 'r2'):
        rows = out['rows'][rid]
        assert rows and all(r['scope'] == 'log_only_v96' and r['robot_id'] == rid for r in rows)
        json.dumps(rows, allow_nan=False)


def _servo_high_whole_checkpoint(c):
    stop = next(e['t'] for e in c.events if e['event'] == 'checkpoint_high_stop')
    end = next((e['t'] for e in c.events if e['event'] == 'checkpoint_high_reobserved'), None)
    moves = [a for t, a in c.issued_log if stop <= t <= (end if end is not None else 1e9) and a['kind'] == 'arm']
    return stop, end, moves


def test_intermediate_high_checkpoint_stops_reobserves_and_resumes_without_lowering():
    _, ctls = pair(segments=(.1, .1))
    run(ctls, until=60., fresh_after=.5)
    for c in ctls:
        assert c.failure is None and c.state == 'released'
        stop, end, moves = _servo_high_whole_checkpoint(c)
        assert end is not None and end-stop >= CHECKPOINT_REOBSERVE_S-1e-8
        assert moves == []                                   # no lower/open/raise at the checkpoint
        assert not [a for t, a in c.issued_log if stop <= t <= end and a.get('servo_id') == 1]
        assert any(e['event'] == 'relocalize' and e['t'] == stop for e in c.events)
        assert any(e['event'] == 'barrier_go' and e['barrier'] == 'carry' and e['t'] > end for e in c.events)
        assert opened(c)                                     # only after the final lowering
        open_t = min(t for t, a in c.issued_log if a.get('servo_id') == 1 and a.get('pulse') == legacy.OPEN)
        assert open_t > end


def test_checkpoint_reobserve_timeout_aborts_and_partner_stops_on_status():
    _, ctls = pair(segments=(.1, .1))
    run(ctls, until=60., fresh_after=.5, no_fix=('r2',))
    r1, r2 = ctls
    assert r2.failure == 'HIGH_CHECKPOINT_REOBSERVE_TIMEOUT'
    assert r1.failure == 'PARTNER_ABORT' and any(a['kind'] == 'hold' for _, a in r1.issued_log)
    for c in ctls:
        assert not opened(c) and pose.at_high(c.port.own.servo)


def test_checkpoint_with_grip_loss_frames_is_logged_only():
    _, ctls = pair(segments=(.1, .1))
    run(ctls, until=60., fresh_after=.5, slip_from=18.)
    assert all(c.failure is None and c.state == 'released' for c in ctls)
    r2 = ctls[1].grip_monitor.export()
    assert any(r['kind'] == 'hold_view' and r['state'] == 'wait_carry' and r['seg'] == 1 for r in r2)


def test_command_history_still_gates_open_command_and_partner_desync():
    _, ctls = pair()
    c = ctls[0]
    ctls[1].ep.tick('aligning', 0.)
    c.tick(0.)                                               # low lift -> raise start
    assert c.failure == 'TRANSIT_PARTNER_DESYNC'
    monitor = grip.TransitMonitor('raise', 0., {1: 1500, **pose.HIGH}, [], 1., 1)
    obs = Controller('r1', PairStatusChannel('x')).observation(0., {1: 1500, **pose.HIGH})
    assert not monitor.observe(0., obs, {1: 2000, **pose.HIGH}, True)
    assert monitor.failure == 'TRANSIT_GRIP_OPEN_COMMAND'
