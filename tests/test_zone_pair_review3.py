"""Third review: per-robot time isolation and merged executor safety, fake physics only."""
import copy
from dataclasses import replace

import pytest

from harness import zone_study_protocol as protocol
from harness.zone_study_prompts_ko import system_prompt
from tests.test_zone_pair_executor import (CALIB, SHEETS, SEARCH_POSE, active, pair_obs, robot, setup,
                                          start, m2_controller, PoseReport)
from tests.test_zone_pair_review2 import TwoMsHost
from tests.test_zone_own_executor import rgb_of


class IsolatedClockHost(TwoMsHost):
    def __init__(self, exs, layer, *, step_s):
        self.trace = []
        super().__init__(exs, layer)
        self.world.model.opt.timestep = step_s

    def record(self, rid, kind, now, payload):
        if rid == 'r2':
            self.trace.append((kind, float(now).hex(), copy.deepcopy(payload)))

    def _capture_raw(self, rid, now):
        slot = self.robots[rid]
        slot.port.fid += 1
        frame = pair_obs(rid, slot.port.fid, now, slot.port.servo)
        slot.executor.on_frame(now, frame, rgb_of(frame))
        slot.next_frame = now + self.FRAME_S
        self.record(rid, 'input', now, frame)

    def _decide_raw(self, rid, now):
        self.record(rid, 'poll', now, None)
        return super()._decide_raw(rid, now)

    def _sink(self, rid, row):
        self.record(rid, 'command', self.world.data.time, row)
        super()._sink(rid, row)

    def call(self, rid, api, *args):
        ack = super().call(rid, api, *args)
        self.record(rid, 'api', self.world.data.time, ack)
        return ack

    def _physics_until(self, end):
        d = self.world.data
        while d.time < end - 1e-9:
            self._pair_arm_tick(d.time)
            d.time += self.world.model.opt.timestep  # accumulated, never rounded
            while self.hooks and d.time + 1e-9 >= self.hooks[0][0]:
                self.hooks.pop(0)[1](self)
            for rid, slot in self.robots.items():
                if not slot.dead and d.time + 1e-9 >= slot.next_frame:
                    self._capture(rid, d.time)


@pytest.mark.parametrize('condition', ['no_comm', 'peer_ko', 'leader_ko', 'structured'])
@pytest.mark.parametrize('step_s', [.00025, .002, .01])
def test_peer_submission_cannot_change_own_input_event_api_command_times_or_order(condition, step_s):
    traces = []
    for submit in (False, True):
        exs = {r: robot(r) for r in ('r1', 'r2', 'r3')}
        for r, ex in exs.items():
            # Identical OWN observations/pose evidence in both worlds; no simulator poses.
            ex.pose.on_frame = lambda now, rgb, rid=r, source=ex.pose.source: PoseReport(
                now, True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.2 if rid == 'r2' and now >= 2. else .01,
                std_yaw_rad=.01, since_tag_s=0., fix_age_s=0., last_fix_t=now, source=source)
        transport = protocol.Transport(condition, seed=0, order_ids=['cargoX'], roles=['end_neg', 'end_pos'])
        transport.open_window('clock', at_sim_s=0.)
        assert system_prompt(condition, 'r1', seed=0)

        def layer(host, kind, event, now):
            if kind == 'event':
                host.record(event['robot_id'], 'delivery', now, event)
                if event['robot_id'] == 'r2' and event['event'] == 'pose_uncertain':
                    host.call('r2', 'hold', .2)

        h = IsolatedClockHost(exs, layer, step_s=step_s)
        h.contact_record = {'profile': 'cargo_noslip_v1'}
        from tests.test_zone_pair_executor import FakeM2
        h.enable_pair_carry(SHEETS, CALIB['params'], controller_factory=FakeM2)
        if submit:
            def attempt(host):
                reply = protocol.validate_reply(
                    {'request_id': 'attempt', 'decision_sources': ['own_rgb', 'order_sheet'],
                     'action': {'kind': 'claim', 'order_id': 'cargoX', 'role': 'end_neg', 'destination_zone': 'B'},
                     'messages': []}, request_id='attempt', condition=condition, actor='r1',
                    order_ids=['cargoX'], roles_by_order={'cargoX': ['end_neg', 'end_pos']})
                assert not protocol.relay(transport, 'r1', reply, at_sim_s=host.world.data.time)
                assert host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')['accepted']
            h.hooks = [(2.412, attempt)]
        h.run(3.1)
        assert not transport.sent_count() and not transport.inbox('r2', now_sim_s=4.)
        assert any(k == 'api' for k, _, _ in h.trace)
        assert any(k == 'delivery' and p['event'] == 'pose_uncertain' for k, _, p in h.trace)
        traces.append(h.trace)
    assert traces[0] == traces[1]


def test_pair_approach_reuses_merged_guarded_driver_and_own_pose_source():
    from harness.zone_own_driver import GuardedDriver
    from harness.pair_owncam_approach import PairApproachDriverV2
    h, exs = setup(factory=m2_controller)
    assert start(h)['accepted']
    for r, ep in active(h).items():
        drv = ep.controller.driver
        assert isinstance(drv, GuardedDriver) and isinstance(drv, PairApproachDriverV2)
        assert drv.loc is exs[r].pose.loc and drv.gate is exs[r].gate and drv.guard is exs[r].guard


def test_pair_pose_consumes_each_own_frame_and_command_only_once(monkeypatch):
    h, exs = setup(factory=m2_controller)
    start(h)
    ex = exs['r1']
    drv = active(h)['r1'].controller.driver
    assert drv.loc is ex.pose.loc
    calls = []
    update, command = ex.pose.loc.update, ex.pose.loc.command
    def observe(*args, **kwargs):
        calls.append('frame')
        return update(*args, **kwargs)
    def issued(*args, **kwargs):
        calls.append('command')
        return command(*args, **kwargs)
    monkeypatch.setattr(ex.pose.loc, 'update', observe)
    monkeypatch.setattr(ex.pose.loc, 'command', issued)
    obs = pair_obs('r1', 2, .1, SEARCH_POSE)
    ex.on_frame(.1, obs, rgb_of(obs))
    drv.observe(.1, rgb_of(obs))
    ex.on_command({'t': .1, 'kind': 'hold'})
    assert calls == ['frame', 'command']


def test_pair_refuses_a_different_pose_calibration():
    h, exs = setup()
    exs['r1'].params = {**exs['r1'].params, 'unexpected_override': 1}
    assert h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')['rejected_reason'] == 'PAIR_CALIBRATION_MISMATCH'
    assert not h.pairs.sessions and not exs['r2'].events


@pytest.mark.parametrize('fault', ['uncertain', 'stale', 'collision'])
def test_pair_carry_guard_stops_both_before_command(fault):
    h, exs = setup()
    assert start(h)['accepted']
    eps = active(h)
    for ep in eps.values():
        ep.controller.state = 'carry'
    if fault == 'uncertain':
        exs['r1'].gate.state = 'uncertain'
    elif fault == 'stale':
        exs['r1'].last_report = replace(exs['r1'].last_report, t_est=-1.)
    else:
        from harness.zone_own_guards import SweepGuard
        exs['r1'].guard = SweepGuard({'obstacles': [{'id': 'wall', 'center_m': [0., 0.],
                                                  'half_extents_m': [1., 1.], 'height_m': 1.}]})
    h._decide('r1', 0.)
    assert all(ep.terminal for ep in eps.values())
    assert all(not ep.controller.arm.events and not ep.controller.schedule for ep in eps.values())
    assert not [k for _, k, _ in h.robots['r1'].port.log if k == 'mecanum']


def test_dead_robot_api_is_refused_without_a_new_pair_endpoint():
    h, exs = setup()
    h.robots['r1'].dead = True
    ack = h.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    assert not ack['accepted'] and not h.pairs.sessions
    assert all(ex._pair is None for ex in exs.values())


def test_pair_approach_stall_uses_two_guarded_recoveries_then_the_common_abort_path():
    from harness.zone_own_guards import MAX_RECOVERIES, STALL_COMMANDED_M
    from tests.test_zone_own_executor_guards import ScriptedLoc
    h, exs = setup(factory=m2_controller)
    assert start(h)['accepted']
    ep = active(h)['r1']
    drv = ep.controller.driver
    drv.loc = ScriptedLoc(lambda t: (.33, -1.60, 0., .01, .01, .1))
    assert exs['r1'].pose.loc is drv.loc
    drv.goal = [.9, -1.6]
    for attempt in range(MAX_RECOVERIES + 1):
        drv.state, drv.state_since = 'drive', 0.
        drv.path = [drv.goal]
        drv.monitor.trusted((.33, -1.6), .57)
        drv.monitor.drove(STALL_COMMANDED_M + .01)
        drv.monitor.trusted((.33, -1.6), .57)
        drv._drive_guard(0.)
    assert drv.recoveries == MAX_RECOVERIES and drv.outcome == 'blocked'
    h._decide('r1', 0.)
    assert all(p.terminal for p in active(h).values())
    assert any(e['event'] == 'blockage_seen' for e in exs['r1'].events)
    assert all(not p.controller.arm.events and not p.controller.schedule for p in active(h).values())


def test_loaded_pair_stall_stops_both_without_unilateral_backoff():
    h, exs = setup()
    start(h)
    ep = active(h)['r1']
    ep.controller.state = 'carry'
    exs['r1'].last_report = replace(exs['r1'].last_report, since_tag_s=0., fix_age_s=0., last_fix_t=0.)
    h._decide('r1', 0.)  # baseline own estimate, followed by an own motion command
    for i in range(1, 45):
        now = i / 10.
        active(h)['r2'].status.tick('aligning', now)
        exs['r1'].last_obs = {**exs['r1'].last_obs, 'frame_id': i + 1, 'sim_time': now}
        exs['r1'].last_report = replace(exs['r1'].last_report, t_est=now)
        count = len(h.robots['r1'].port.log)
        h._decide('r1', now)
        if ep.terminal:
            break
    assert all(p.terminal for p in active(h).values())
    assert not [r for r in h.robots['r1'].port.log[count:] if r[1] == 'mecanum']
    assert any(e['event'] == 'job_failed' and e['detail']['reason'] == 'PAIR_blocked' for e in exs['r1'].events)


def test_queued_arm_commands_pass_the_same_3d_guard_before_issue():
    from harness.zone_own_guards import SweepGuard
    from tests.test_zone_pair_review import ArmTiming
    h, exs = setup(factory=ArmTiming)
    start(h)
    h._decide('r1', 0.)
    active(h)['r1'].controller.arm.queue({3: 1400}, 0., duration=1.2)
    exs['r1'].guard = SweepGuard({'obstacles': [{'id': 'wall', 'center_m': [0., 0.],
                                              'half_extents_m': [1., 1.], 'height_m': 1.}]})
    h._pair_arm_tick(.05)
    assert all(p.terminal for p in active(h).values())
    assert not [r for r in h.robots['r1'].port.log if r[1] == 'arm']


def test_frozen_help_test_explicitly_skips_without_mujoco(monkeypatch):
    import sys
    from tests.test_m2_pair_door_v3 import test_runner_status_channel_default_on_and_help_text
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    with pytest.raises(pytest.skip.Exception, match='frozen M2 CLI'):
        test_runner_status_channel_default_on_and_help_text()


def test_workflow_docs_use_the_existing_readme_fixed_in_main():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / 'configs/simulation_workflows.json').read_text())['workflows']
    assert next(r['docs'] for r in rows if r['id'] == 'zone-m1-owncam-run') == 'experiments/2026-09-26-zone-m1-owncam/README.md'
    assert all((root / r['docs']).is_file() for r in rows)
