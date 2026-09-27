"""Issue #221: real executor/host API on fake controllers and a fake world.

No test creates a MuJoCo model or runs a physical cohort. A separate adapter
test instantiates the actual frozen M2 controller and replays own JPEGs.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from harness.owncam_pose_source import PoseReport
from harness.zone_own_executor import ZoneOwnExecutor
from harness.zone_pair_executor import PairTeam, make_plan, m2_controller
from harness.zone_pair_status import STATES
from harness.zone_pair_status import FIELDS
from scripts import run_m2_pair as m2
from tests.test_zone_own_executor import CALIB, MAP, ROWS_Y, SEARCH_POSE, obs
from tests.test_zone_own_executor_host import FakeHost, issued_after

ROOT = Path(__file__).resolve().parents[1]
ORDER = {'orders': [{'order_id': 'cargoX', 'kind': 'long_beam', 'count': 1, 'required_robots': 2,
                     'destination_zone': 'B', 'initial_location': {'pickup_bay': 'P2', 'slot': 'P2-3'}}]}
SHEETS = {'cargoX': m2.pa.coarse_order_sheet([1., .05, 0.])}


@pytest.fixture
def beam_fit(monkeypatch):
    """Explicit own-RGB geometry fixture, independent of recorded grip pixels.

    The grip JPEG tests the existing close-view classifier only; it does not
    establish an unclipped whole-beam pose. Scheduling positives supply that
    separate observation here, rather than silently assuming attachment.
    """
    from harness import owncam_pair_beam_v2 as ob2
    beam = dict(visible=True, end_visible=True, grip_source='band_centre',
                grip_base_m=[.162, 0.], axis_heading_rad=0.,
                lateral_spread_m=.001, visible_length_m=.5)
    monkeypatch.setattr(ob2, 'observe_beam', lambda image, servo: dict(beam))
    return beam


def pair_obs(rid, fid, now, servo):
    result = obs(rid, fid, now, servo)
    jpeg = (ROOT / 'tests/fixtures/m2_pair_door_v3/lift_824_r2_00759.jpg').read_bytes()
    return {**result, 'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest()}


class PairFakeHost(FakeHost):
    def _capture_raw(self, rid, now):
        from tests.test_zone_own_executor import rgb_of
        slot = self.robots[rid]
        slot.port.fid += 1
        frame = pair_obs(rid, slot.port.fid, now, slot.port.servo)
        # A deterministic own-pose fixture for scheduling tests, not localisation
        # evidence from this recorded JPEG or a simulated ground-truth pose.
        slot.executor.pose.on_frame = lambda t, rgb: PoseReport(
            t, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01, std_yaw_rad=.01,
            since_tag_s=0., source=slot.executor.pose.source)
        slot.executor.on_frame(now, frame, rgb_of(frame))
        slot.next_frame = now + self.FRAME_S


def report_ready(barrier, ep, now):
    o = ep.own.last_obs
    return barrier.report(ep.own.robot_id, ready=True, observed_at_s=o['sim_time'], received_at_s=now,
                          frame_id=f"{ep.own.robot_id}-{o['frame_id']}-{o['sha256'][:12]}")


def robot(rid, *, limit=720):
    ex = ZoneOwnExecutor(rid, MAP, CALIB['params'], ORDER, skill_factory=lambda *a, **kw: None,
                          pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False, job_sim_limit_s=limit)
    ex.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
    ex.last_obs = pair_obs(rid, 1, 0., SEARCH_POSE)
    ex.last_report = PoseReport(t_est=0., initialized=True, x_m=0., y_m=0., yaw_rad=0.,
                                std_xy_m=.01, std_yaw_rad=.01, source=ex.pose.source)
    ex.gate.state = 'ok'
    return ex


class FakeM2:
    """M2 I/O contract only; all rendezvous use the production status adapter."""
    def __init__(self, ep, plan, params):
        self.ep, self.state, self.state_t = ep, 'approach', ep.own.now
        self.failure, self.schedule = None, [(100., 101., {'forward': 1.})]
        self.driver = types.SimpleNamespace(on_command=lambda row: None)
        self.arm = types.SimpleNamespace(events=[(100., 1, 1500)], until=101., tick=lambda t: None)
        self.seg, self.calls = 0, 0
        self.claims = {}

    def tick(self, now):
        self.calls += 1
        ep = self.ep
        ep.status.tick('aligning', now)
        if self.state == 'approach':
            self.state = 'wait_lift'
        if self.state == 'wait_lift':
            b = ep.status.sync_for('lift@0')
            if b.authorize(now)['phase'] == 'GO':
                self.state = 'carry'
            else:
                report_ready(b, ep, now)
        if self.state == 'carry':
            ep.port.apply({'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15}, now)


class PhasedM2(FakeM2):
    """Two checkpoint cycles through the real status adapters and host scheduler."""
    phases = ('approach', 'lift', 'carry', 'lower', 'open')

    def __init__(self, *args):
        super().__init__(*args)
        self.index = 0
        self.go_events = []

    def tick(self, now):
        ep = self.ep
        phase = self.phases[self.index % len(self.phases)]
        segment = self.index // len(self.phases)
        ep.status.tick({'approach': 'aligning', 'lift': 'ready', 'carry': 'lift',
                        'lower': 'carry', 'open': 'put_down'}[phase], now)
        barrier = ep.status.sync_for(f'{phase}@{segment}')
        if barrier.authorize(now)['phase'] != 'GO':
            report_ready(barrier, ep, now)
            return
        self.go_events.append((phase, segment, round(now, 4)))
        ep.port.apply({'kind': 'arm', 'servo_id': 1, 'pulse': 1500 if phase == 'lift' else 2000}, now)
        self.index += 1
        self.state = 'done' if self.index == 2 * len(self.phases) else self.phases[self.index % len(self.phases)]


def setup(*, factory=FakeM2, limit=720):
    exs = {r: robot(r, limit=limit) for r in ('r1', 'r2', 'r3')}
    host = PairFakeHost(exs, lambda *a: None)
    host.contact_record = {'profile': 'cargo_noslip_v1'}
    host.enable_pair_carry(SHEETS, CALIB['params'], controller_factory=factory)
    return host, exs


def start(host):
    first = host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    if not first['accepted']:
        return first
    return host.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')


def active(host):
    return host.pairs.sessions[-1]['endpoints']


def ends(ex):
    return [e for e in ex.events if e['event'] in ('job_done', 'job_failed')]


def test_accepts_both_and_consumes_status_channel_for_lift():
    host, exs = setup()
    ack = start(host)
    assert ack['accepted'] and all(exs[r].job.kind == 'pair_carry' for r in ('r1', 'r2'))
    a, b = (active(host)[r] for r in ('r1', 'r2'))
    a.step(0.)
    assert a.controller.state == 'wait_lift'
    assert not a.port.commands
    b.step(0.)
    for ep in (a, b):
        ep.step(.1)
    for ep in (a, b):
        decision = ep.step(.2)
        assert ep.controller.state == 'carry'
        assert decision['commands'][0]['kind'] == 'mecanum'
    assert all(set(m) == FIELDS and m['state'] in STATES for m in a.status.channel.log)
    assert 'cargoX' not in str(a.status.channel.log) and 'target_ref' not in str(a.status.channel.log)
    assert any(e['event'] == 'pair_progress' for e in exs['r1'].events)
    assert exs['r1'].status()['job']['phase'] == 'carry'
    from harness.zone_own_contract import action_record
    assert action_record(ack, run_id='dev-contract', condition='no_comm', seed=0, request_id='req')['accepted']


@pytest.mark.parametrize('case,reason', [('busy', 'SELF_BUSY'), ('uncertain', 'SELF_UNCERTAIN'),
                                       ('stopped', 'SELF_STOPPED'), ('occupied', 'SELF_OCCUPIED'),
                                       ('incompatible', 'WRONG_PAIR_DESTINATION')])
def test_refuses_partner_without_partial_reservation(case, reason):
    host, exs = setup()
    if case == 'busy':
        exs['r2'].hold(10.)
    elif case == 'uncertain':
        exs['r2'].gate.state = 'uncertain'
    elif case == 'stopped':
        exs['r2'].stop(0., 'test')
    elif case == 'occupied':
        exs['r2']._holding_after = {'answer': 'unknown', 'source': 'own_view'}
    else:
        exs['r2'].orders['cargoX']['destination_zone'] = 'A'
    ack = start(host)
    assert not ack['accepted'] and ack['rejected_reason'] == reason
    # The first actor owns only a pending submission. A peer's explicit
    # refusal or deadline ends it; no private partner read occurs on submission.
    host.pairs.poll(5.01)
    assert exs['r1'].job is None and exs['r1']._pair is None


@pytest.mark.parametrize('args', [(), ('cargoX',), ('cargoX', 'B'), ('cargoX', 'B', 'r2', 'extra'),
                                 (None, 'B', 'r2'), ([], 'B', 'r2'), ({}, 'B', 'r2'),
                                 ('cargoX', [], 'r2'), ('cargoX', 'B', []), ('cargoX', 'B', 'r1'),
                                 ('cargoX', 'B', 'r3'), ('missing', 'B', 'r2'), ('cargoX', 'A', 'r2'),
                                 ('cargoX', 'B2', 'r2')])
def test_invalid_llm_arguments_return_refusal_not_exception(args):
    host, exs = setup()
    ack = host.call('r1', 'pair_carry', *args)
    assert ack['accepted'] is False
    assert all(ex.job is None for ex in exs.values())


@pytest.mark.parametrize('profile,weld', [('local_contact_fine', False), ('cargo_noslip_v1', True)])
def test_refuses_wrong_contact_or_weld(profile, weld):
    host, _ = setup()
    host.pairs.contact_profile, host.pairs.weld = profile, weld
    assert start(host)['rejected_reason'] == 'PAIR_REQUIRES_NOSLIP_WELD_OFF'


@pytest.mark.parametrize('cause', ['abort', 'timeout', 'partner_loss', 'exception', 'drop', 'episode_end'])
def test_all_stop_paths_clear_both_arm_queues_and_host_macros(cause):
    host, exs = setup(limit=.5 if cause == 'timeout' else 720.)
    assert start(host)['accepted']
    eps = active(host)
    for r in ('r1', 'r2'):
        slot = host.robots[r]
        slot.timeline = [(10., [{'kind': 'arm', 'servo_id': 1, 'pulse': 2000}])]
        slot.capture_after = True
    now = 2.1 if cause == 'partner_loss' else .6
    host.world.data.time = now
    if cause == 'abort':
        assert host.call('r2', 'abort')['accepted']
    elif cause == 'timeout':
        host._expire('r2', now)
    elif cause == 'partner_loss':
        # r2 stops sending; no private dead flag is required for loss detection.
        eps['r1'].status.tick('aligning', now)
        host._pair_safety(now)
    elif cause == 'exception':
        def broken(*args):
            raise RuntimeError('fixture')
        host._guard('r2', now, broken)
    elif cause == 'drop':
        eps['r2'].controller.state = 'failed'
        eps['r2'].controller.failure = 'LOAD_CHANGED_IN_CARRY'
        eps['r2'].controller.tick = lambda t: None
        host._decide('r2', now)
    else:
        host.close_episode('TEST')
    for r in ('r1', 'r2'):
        assert eps[r].terminal and not eps[r].controller.arm.events and not eps[r].controller.schedule
        assert not host.robots[r].timeline and not host.robots[r].capture_after
        assert len(ends(exs[r])) == 1 and ends(exs[r])[0]['event'] == 'job_failed'
        assert exs[r].job is None
        assert any(t == now and k == 'hold' for t, k, _ in host.robots[r].port.log)
        host._run_timeline(r, 10.)
        assert not issued_after(host.robots[r].port, now)
    assert exs['r3'].stopped is None and exs['r3'].job is None
    host._pair_safety(now + 1.)
    assert all(len(ends(exs[r])) == 1 for r in ('r1', 'r2'))


def test_peer_private_state_does_not_affect_local_control_until_status_is_sent():
    host, exs = setup()
    start(host)
    eps = active(host)
    eps['r1'].step(0.)
    transcript = copy.deepcopy(eps['r1'].status.channel.log)
    # Changing pose, job phase, claims, failure and private arm queue publishes
    # nothing. r1 has no path to these objects and remains at the barrier.
    exs['r2'].last_report = PoseReport(t_est=0., initialized=False)
    exs['r2'].job.phase = 'private carry'
    eps['r2'].controller.state = 'failed'
    eps['r2'].controller.failure = 'private failure'
    eps['r2'].controller.claims['gt_fake'] = [999., 999.]
    eps['r2'].controller.arm.events.clear()
    exs['r2'].map['regions']['zone_B']['center_m'] = [999., 999.]
    assert eps['r1'].step(.1)['commands'] == []
    assert eps['r1'].controller.state == 'wait_lift'
    assert eps['r1'].status.channel.latest['r2'] == next(m for m in reversed(transcript) if m['robot_id'] == 'r2')
    eps['r2'].status.tick('abort', .1)
    assert eps['r1'].step(.1)['commands'] == [{'kind': 'hold'}]
    assert ends(exs['r1'])[0]['detail']['reason'] == 'PARTNER_ABORT'


def test_done_is_joint_sequence_completion_never_zone_success():
    host, exs = setup()
    start(host)
    eps = active(host)
    eps['r1'].controller.state = 'done'
    eps['r1'].step(.1)
    assert not ends(exs['r1'])
    eps['r2'].controller.state = 'done'
    eps['r2'].step(.1)
    eps['r1'].step(.2)
    for r in ('r1', 'r2'):
        assert len(ends(exs[r])) == 1
        assert ends(exs[r])[0]['detail']['confirmation'] == 'unconfirmed'
        assert ends(exs[r])[0]['detail']['outcome'] == 'PAIR_SEQUENCE_DONE'


@pytest.mark.parametrize('start_s', [0., .55])
def test_host_drives_checkpoint_barriers_to_joint_done_with_identical_go_times(start_s, beam_fit):
    host, exs = setup(factory=PhasedM2)
    if start_s:
        host.world.data.time = start_s
        for rid in exs:
            host._capture_raw(rid, start_s)

    def layer(h, event, payload, now):
        if event != 'start':
            return
        for ex in exs.values():
            # Fake camera pose evidence for admission, not simulator state.
            ex.last_report = PoseReport(t_est=now, initialized=True, std_xy_m=.01, std_yaw_rad=.01,
                                        x_m=0., y_m=0., yaw_rad=0., source=ex.pose.source)
            ex.gate.state = 'ok'
        assert start(h)['accepted']

    host.study_layer = layer
    result = host.run(10., done=lambda: bool(host.pairs.sessions) and all(ep.terminal for ep in active(host).values()))
    assert result['outcome'] == 'STUDY_LAYER_DONE'
    eps = active(host)
    assert eps['r1'].controller.go_events == eps['r2'].controller.go_events
    assert len(eps['r1'].controller.go_events) == 10
    for r in ('r1', 'r2'):
        assert len(ends(exs[r])) == 1 and ends(exs[r])[0]['event'] == 'job_done'
        assert ends(exs[r])[0]['detail']['confirmation'] == 'unconfirmed'
        assert not host.robots[r].timeline and not eps[r].controller.arm.events
    records = host.pairs.records()[0]
    assert records['status_messages'] and not records['rejected_status']
    assert len(records['plan']['map_sha256']) == len(records['calibration_sha256']) == 64


def test_real_factory_and_first_control_step_do_not_import_mujoco():
    code = '''
import importlib.abc, sys
class DenyMuJoCo(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'mujoco' or fullname.startswith('mujoco.'):
            raise AssertionError('MuJoCo imported by executor')
sys.meta_path.insert(0, DenyMuJoCo())
from tests.test_zone_pair_executor import setup, start, m2_controller, active
host, _ = setup(factory=m2_controller)
assert start(host)['accepted']
for ep in active(host).values():
    assert ep.step(0.)['mode'] == 'tick'
assert 'mujoco' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=os.environ.copy(),
                             capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_destination_route_reaches_zone_b_and_uses_bounded_segments():
    plan = make_plan(MAP, SHEETS['cargoX'], 'B')
    assert plan['route'][-1] == MAP['regions']['zone_B']['center_m']
    assert len(plan['route']) <= 9
    import math
    assert max(math.dist(a, b) for a, b in zip(plan['route'], plan['route'][1:])) <= .85 + 1e-9
    bad = copy.deepcopy(SHEETS['cargoX'])
    bad['beam_xyyaw'][0] = 1.01234
    with pytest.raises(ValueError, match='GRID'):
        make_plan(MAP, bad, 'B')


def test_real_m2_factory_reuses_v3_controller_and_lateral_schedule():
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    eps = active(host)
    plan = make_plan(MAP, SHEETS['cargoX'], 'B')
    for r, ep in eps.items():
        ctl = ep.controller
        assert isinstance(ctl, m2.M2DoorStudent) and ctl.version == 'v3'
        assert ctl.hold_check == 'fullframe_v3'
        assert ctl._lift.__func__ is m2.M2DoorStudent._lift
        assert ctl.port.capture()['robot_id'] == r
        ctl.seg = 3
        ctl.grasp_estimate = [3.2, .05, 0. if r == 'r1' else m2.math.pi]
        schedule = ctl.door_schedule(10.)
        assert schedule[-1][2]['forward'] == 0.
        assert schedule[-1][2]['left'] * (1 if r == 'r1' else -1) < 0
        assert len(ctl.segments) == len(plan['route']) - 1
    # No new dynamic world import is needed to instantiate/run the adapter.
    assert not hasattr(eps['r1'], 'world') and not hasattr(eps['r1'].controller, 'partner')


def test_real_adapter_requests_fresh_frame_before_advancing_controller_timers():
    host, _ = setup(factory=m2_controller)
    start(host)
    ep = active(host)['r1']
    before = ep.controller.state, ep.controller.state_t, ep.controller.next_frame
    assert ep.step(.1) == {'mode': 'capture'}
    assert (ep.controller.state, ep.controller.state_t, ep.controller.next_frame) == before


def test_pair_endpoint_graph_has_no_host_world_peer_executor_or_peer_controller():
    host, exs = setup(factory=m2_controller)
    start(host)
    # Traverse application containers/instances, not Python class/module globals.
    def reachable(obj):
        seen, todo = set(), [obj]
        while todo:
            obj = todo.pop()
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            if isinstance(obj, dict):
                todo.extend(obj.values())
            elif isinstance(obj, (list, tuple, set)):
                todo.extend(obj)
            elif isinstance(obj, types.MethodType):
                todo.append(obj.__self__)
            elif isinstance(obj, types.FunctionType):
                todo.extend(c.cell_contents for c in obj.__closure__ or ())
            elif not isinstance(obj, (type, types.ModuleType)) and hasattr(obj, '__dict__'):
                todo.extend(vars(obj).values())
        return seen
    seen = reachable(exs['r1'])
    assert not {id(host), id(host.world), id(exs['r2']), id(host.robots['r2'].port),
                id(active(host)['r2'].controller)} & seen


def test_real_m2_recovery_exhausts_once_then_explicit_failure():
    host, exs = setup(factory=m2_controller)
    start(host)
    ep = active(host)['r1']
    ctl = ep.controller
    ctl._start_reapproach(.1, [.9, 0.])
    assert ctl.reapproaches == 1 and ctl.state == 'reapproach'
    ctl._start_reapproach(.2, [.9, 0.])
    assert ctl.state == 'failed' and ctl.failure == 'APPROACH_INCONSISTENT_WITH_BEAM'
    host._pair_safety(.2)
    assert ends(exs['r2'])[0]['detail']['reason'] == 'PARTNER_ABORT'


def test_real_v3_rejects_lost_lift_from_own_image_and_stops_both():
    host, exs = setup(factory=m2_controller)
    start(host)
    ep = active(host)['r1']
    fix = ROOT / 'tests/fixtures/m2_pair_door_v3'
    ep.controller.anchor = m2.lv3.co_motion_signature(base64.b64encode(
        (fix / 'grasp_824_r2_00757.jpg').read_bytes()).decode())
    # Recorded foreign-session pixels are replayed as this robot's own fake
    # camera input; no live peer frame handle is provided to the controller.
    jpeg = (fix / 'approach_824_r2_00010.jpg').read_bytes()
    exs['r1'].last_obs = {**exs['r1'].last_obs, 'image': base64.b64encode(jpeg).decode(),
                         'sha256': hashlib.sha256(jpeg).hexdigest()}
    ep.controller.state = 'lift'
    ep.controller._lift(0., True)
    assert ep.controller.failure == 'LOAD_NOT_HELD_AFTER_LIFT'
    host._pair_safety(0.)
    assert all(ep.terminal for ep in active(host).values())
    assert ends(exs['r1'])[0]['detail']['reason'] == 'LOAD_NOT_HELD_AFTER_LIFT'


def test_frozen_m2_sources_or_explicit_followup_hashes():
    manifest = json.loads((ROOT / 'experiments/2026-09-26-zone-m2-pair/imports.json').read_text())
    files = manifest['imports']
    # Reviewed revisions that reached main after the freeze (records stay on their pinned SHA).
    post_freeze = {'sim/zone_landmarks.py': {
        '2de8bf3a32673c5305d87639894e90deb9932ac015b697ddb8a05dcccf56e5f1'}}  # PR #208 env v3 registries
    # PR #240 requested time-contract followup; old runs keep their frozen source.
    post_freeze['harness/owncam_pose_source.py'] = {'215821c84c58ff1e939b7c0fa2c0a6956d82f9f4f9f2ad63db95c1a1b7bfb6ae'}
    for row in files:
        got = hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest()
        assert got in {row['sha256'], *post_freeze.get(row['path'], ())}, row['path']
    sources = {
        'scripts/run_m2_pair.py': '3432df1fbefd4779921dc89a20f60fb67299fcdd02aa4568c6ecd14e27978783',
        'harness/pair_owncam_approach.py': '75058e95ff0f78dc388e9e34deba59f0524ef0647fb4e8a2597852ae0440f184',
        'harness/owncam_pair_lift_v3.py': 'faf725e3b1b1ee1e387c0f8c593b7508b6e170387d010debb551df7bd05d087d',
    }
    for path, digest in sources.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
