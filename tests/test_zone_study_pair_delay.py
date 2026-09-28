"""Real PairTeam/M2 + real 0.16 SIM-s pose provider on stored own RGB.

Start at an opened checkpoint (the preceding navigation/carry is outside this
test). The fake world advances only a number; the real host runs arm commands,
M2's PF replacement/sweep, RGB grip check and status readiness/GO. No inference
result, readiness, guard, controller method or delay is replaced by a stub.
"""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import sys
from pathlib import Path

import pytest

from harness.zone_own_executor import ZoneOwnExecutor
from harness.zone_pair_executor import PairTeam
from harness.zone_study_pose_delay import DelayedPoseSource
from scripts import run_m2_pair as m2
from scripts import run_zone_study_integration as runner
from tests.test_zone_own_executor import MAP, ROWS_Y, obs, rgb_of
from tests.test_zone_own_executor_host import FakeHost
from tests.test_zone_pair_executor import ORDER, SHEETS, active, start
from tests.test_zone_study_integration import FRAMES

FIX = Path(__file__).parent / 'fixtures/zone_study_pair_delay'
REPLAY = json.loads((FIX / 'frames.json').read_text())
PREREG = runner.load_prereg(runner.ROOT / 'configs/zone_study_integration/pair_dev_DRAFT.json')
CALIB = json.loads((runner.ROOT / PREREG['student']['calibration']).read_text())


@pytest.fixture(autouse=True)
def no_physics_or_network(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    monkeypatch.setattr(socket.socket, 'connect_ex', lambda *a: pytest.fail('network forbidden'))


class SavedRGBHost(FakeHost):
    def __init__(self):
        spec = runner.zi.pose_provider_spec('tags_temporary', map_id='zone_wide_door_tags_v2')
        executors = {r: ZoneOwnExecutor(r, MAP, CALIB['params'], ORDER, judgments=False,
                                      skill_factory=lambda *a, **k: None, pose_estimate_cls=tuple,
                                      search_rows_y=ROWS_Y) for r in runner.ROBOTS}
        for ex in executors.values():
            ex.pose = runner.zi.build_pose_provider(spec, MAP, CALIB['params'], 700)
        super().__init__(executors, lambda *a: None)
        self.contact_record = {'profile': 'cargo_noslip_v1'}
        self.enable_pair_carry(SHEETS, CALIB['params'])  # production m2_controller
        self.saved = {}
        for rid in ('r1', 'r2'):
            self.saved[rid] = []
            for row in REPLAY['frames']:
                if row['robot'] != rid:
                    continue
                data = (FIX / row['file']).read_bytes()
                assert hashlib.sha256(data).hexdigest() == row['sha256']
                self.saved[rid].append((row, data))

    def _capture_raw(self, rid, now):
        slot = self.robots[rid]
        if rid == 'r3':
            jpeg = FRAMES[0]  # idle third robot's own saved stream
        else:
            # At a recorded settled look, replay that robot's corresponding RGB.
            # During interpolation use its tagless grasp JPEG: no fictional tag
            # coordinates or live simulated geometry enter the estimator.
            choices = self.saved[rid]
            jpeg = choices[-1][1]
            for row, data in choices:
                commanded = {int(k): v for k, v in row['own_pose_commands'].items()}
                if row['state'] == 'pregrasp_look' and slot.port.servo == commanded:
                    jpeg = data
                    break
        slot.port.fid += 1
        frame = {**obs(rid, slot.port.fid, now, slot.port.servo),
                 'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest()}
        slot.executor.on_frame(now, frame, rgb_of(frame))
        slot.frames.append({'robot_id': rid, 't': now, 'sha256': frame['sha256']})
        slot.next_frame = now + self.FRAME_S

    def admit_from_saved_sweep(self):
        # Replay only issued servo commands and own images to initialize the
        # filters/admission gates; never seed them from an evaluated pose.
        for i in range(12):
            now = round(i * .2, 6)
            self.world.data.time = now
            for rid in ('r1', 'r2'):
                row, _ = self.saved[rid][min(i, 7)]
                slot = self.robots[rid]
                slot.port.servo = {int(k): v for k, v in row['own_pose_commands'].items()}
                self._sink(rid, {'t': now, 'kind': 'initial_servo_command', 'pulses': slot.port.servo})
                self._capture(rid, now)
            self._capture('r3', now)
        for rid in ('r1', 'r2'):
            ex = self.robots[rid].executor
            assert ex.last_report.initialized and ex.gate.ok
        assert isinstance(self.pairs, PairTeam)
        assert self.pairs.contact_profile == 'cargo_noslip_v1' and not self.pairs.weld
        assert start(self)['accepted']


@pytest.mark.parametrize('arm_settle_s,expected_go', [(6., True), (0., False)])
def test_real_m2_checkpoint_relocalization_readiness_and_go(arm_settle_s, expected_go):
    host = SavedRGBHost()
    host.admit_from_saved_sweep()
    eps = active(host)
    before = {}
    for rid, ep in eps.items():
        ctl, provider = ep.controller, ep.own.pose
        assert isinstance(ctl, m2.M2DoorStudent) and ctl.version == 'v3'
        assert isinstance(provider, DelayedPoseSource)
        assert ctl.driver.loc is provider.loc
        before[rid] = provider.loc, provider.provider.loc, len(provider.timing)
        # Checkpoint entry state from own M2 state/previous RGB grasp estimate.
        # No navigation, preceding physical carry or success is claimed.
        ctl.grip_base = REPLAY['checkpoint_grip_base_from_own_rgb'][rid]
        ctl.look_name = 'p45'
        ctl.set('cp_open', host.world.data.time)
        # Fixture checkpoint with r1's preceding arm settle still pending.
        ctl.arm.until = host.world.data.time + (arm_settle_s if rid == 'r1' else 0.)

    unreleased = set()
    for i in range(1, 601):
        runner.StudyTeamHost.advance_to(host, round(2.2 + i * .05, 6))
        for rid, ep in eps.items():
            provider = ep.own.pose
            resets = [e for e in ep.events if e['event'] == 'state' and e['state'] == 'pregrasp_look']
            if resets and host.world.data.time < resets[-1]['sim_s'] + .16 - 1e-9:
                # Actual M2 replaced the PF. Neither loc nor report may retain
                # the admission estimate or see an image before release.
                assert provider.loc is before[rid][0]
                assert provider.provider.loc is not before[rid][1]
                assert not provider.loc.estimate()['initialized']
                assert not provider.report(host.world.data.time).initialized
                assert not any(m['robot_id'] == rid and m['state'] == 'lift_ready_1'
                               for m in ep.status.channel.log)
                unreleased.add(rid)
        if all(ep.controller.state == 'lift' for ep in eps.values()):
            break
        if any(ep.terminal for ep in eps.values()):
            assert not expected_go, [ep.own.events[-3:] for ep in eps.values()]
            break
    else:
        pytest.fail(str([(r, ep.controller.state, ep.events[-5:]) for r, ep in eps.items()]))

    assert unreleased == {'r1', 'r2'}
    messages = host.pairs.records()[0]['status_messages']
    go = [m for m in messages if m['state'] == 'lift_go_1']
    if not expected_go:
        # Unsynchronised checkpoint settling in this RGB replay: r1 finishes
        # first, waits for r2, then its own loaded pose crosses the guard limit.
        # The real guard aborts; a past readiness must never become joint GO.
        assert not go
        assert any(m['state'] == 'lift_ready_1' for m in messages)
        assert any(e['event'] == 'job_failed' and e['detail']['reason'] == 'POSE_UNCERTAIN'
                   for ep in eps.values() for e in ep.own.events)
        assert all(ep.terminal for ep in eps.values())
        assert all(ep.port.commands == [] and ep.controller.arm.events == [] for ep in eps.values())
        return
    assert {m['robot_id'] for m in go} == {'r1', 'r2'}
    assert len({m['sent_at_s'] for m in go}) == 1
    for rid, ep in eps.items():
        provider = ep.own.pose
        facade, old_filter, n = before[rid]
        assert provider.loc is facade and provider.provider.loc is not old_filter
        assert ep.controller.driver.loc is facade
        fixes = [e for e in ep.events if e['event'] == 'pregrasp_fix' and e['ok']]
        assert fixes
        ready = next(m for m in messages if m['robot_id'] == rid and m['state'] == 'lift_ready_1')
        assert fixes[0]['sim_s'] < ready['sent_at_s'] < go[0]['sent_at_s']
        latest_ready = next(m for m in reversed(messages) if m['robot_id'] == rid and m['state'] == 'lift_ready_1')
        assert go[0]['sent_at_s'] < latest_ready['ready_until_s']
        assert any(row['sha256'] in {f['sha256'] for f in host.robots[rid].frames}
                   for row in ep.inputs if row['phase'] == 'pregrasp_look')
        timing = provider.timing[n:]
        assert timing and all(t['available_sim_s'] == pytest.approx(t['captured_sim_s'] + .16)
                              and t['consumed_sim_s'] + 1e-9 >= t['available_sim_s'] for t in timing)
        assert ep.own.last_report.t_est <= host.world.data.time - .16 + 1e-9
        assert any(kind == 'arm' for _, kind, _ in host.robots[rid].port.log)
