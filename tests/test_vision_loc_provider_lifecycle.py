"""P03: own-only fake worker, numeric PF and clocks; no renderer or inference."""
import copy
import socket
import sys

import numpy as np
import pytest

from harness import vision_loc_protocol as vp
from harness.vision_loc_client import InProcessWorker
from harness.vision_pose_source_p03 import VisionPoseSourceV2
from harness.zone_study_pose_delay_p03 import DelayedPoseSource
from tests.test_vision_pose_source import CALIB, DOCK, FRAME, SEARCH_POSE, _reply


@pytest.fixture(autouse=True)
def forbid_runtime_side_effects(monkeypatch):
    for name in ('mujoco', 'torch', 'torchvision'):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))


def make(*, prior=True, fail_at=None):
    # Fixed protocol JSON from the torch-free fake-worker contract. No truth
    # pose, peer frame, world, renderer or model is available to this worker.
    row = _reply()
    obs = vp.check_reply(row, seq=0, bgr_sha256='a' * 64, n_columns=len(vp.columns()))[1]
    worker = InProcessWorker(lambda seq, own_bgr: copy.deepcopy(obs), fail_at=fail_at)
    p = VisionPoseSourceV2(vp.load_json(VisionPoseSourceV2.map_file), CALIB['params'], worker=worker)
    if prior:
        p.init_prior(DOCK, source='setup:r1:own_dock')
    p.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
    return p


def test_late_frame_cannot_update_current_belief_with_an_old_fix_time():
    p = make()
    try:
        p.on_frame(.4, FRAME)
        p.report(2.)
        before = p.loc._pf.px.copy(), p.loc._pf.logw.copy(), p.loc.last_scan_t, p.worker.seq
        p.on_frame(.8, FRAME)
        np.testing.assert_array_equal(p.loc._pf.px, before[0])
        np.testing.assert_array_equal(p.loc._pf.logw, before[1])
        assert (p.loc.last_scan_t, p.worker.seq) == before[2:]
    finally:
        p.close()


def test_relocalization_keeps_unreleased_own_commands_and_motion_profile():
    p = make()
    d = DelayedPoseSource(p)
    try:
        d.on_command({'t': 1., 'kind': 'arm', 'servo_id': 3, 'pulse': 1072})
        profile = next(iter(CALIB['params']['motion_profiles']))
        d.set_motion_profile(1., profile)
        d.begin_relocalization(1.05, SEARCH_POSE)
        assert any(method == 'on_command' and args[0].get('servo_id') == 3
                   for _, _, method, args in d.pending)
        assert any(method == 'set_motion_profile' for _, _, method, _ in d.pending)
        d.report(1.3)
        assert p.servo[3] == 1072 and p.loc.motion_profile == profile
    finally:
        d.close()


@pytest.mark.parametrize('started_by', ['command', 'relocalization'])
def test_prior_cannot_be_injected_after_commands_or_relocalization(started_by):
    p = make(prior=False)
    try:
        if started_by == 'command':
            p.on_command({'t': .1, 'kind': 'hold'})
        else:
            p.begin_relocalization(0., SEARCH_POSE)
        with pytest.raises(RuntimeError):
            p.init_prior(DOCK, source='GT/dock reseed during runtime')
    finally:
        p.close()


def test_legacy_loc_command_uses_the_same_own_servo_and_prior_boundary():
    p = make(prior=False)
    try:
        p.loc.command({'t': .1, 'kind': 'look', 'pan_pulse': 1230})
        assert p.servo[6] == p.loc.servo[6] == 1230
        assert p.loc.own_servo_cmd_t == .1
        assert p.lifecycle[-1]['row']['kind'] == 'look'
        with pytest.raises(RuntimeError):
            p.init_prior(DOCK, source='late dock through loc.command')
    finally:
        p.close()


def test_delay_cannot_be_applied_twice():
    p = make()
    d = DelayedPoseSource(p)
    try:
        with pytest.raises(ValueError, match='delay'):
            DelayedPoseSource(d)
    finally:
        d.close()


def test_candidate_delay_rejects_an_already_legacy_wrapped_provider():
    from harness.zone_study_pose_delay import DelayedPoseSource as LegacyDelay
    p = make()
    d = LegacyDelay(p)
    try:
        with pytest.raises(ValueError, match='exactly once'):
            DelayedPoseSource(d)
    finally:
        d.close()


class OwnRobotOnly:
    __slots__ = ('servo', '_shared_pose')

    def __init__(self, pose, servo):
        self.servo, self._shared_pose = dict(servo), pose

    def __getattr__(self, name):
        raise AssertionError(f'forbidden peer/GT/world access: {name}')


def test_whole_command_lifecycle_and_m2_p20_scan_preserve_one_belief():
    from types import SimpleNamespace as NS
    from harness.m2_provider_adapter import ProviderM2DoorStudent
    from harness.owncam_drive import LOOK_P20
    from scripts.run_m2_pair import PREGRASP_PANS_V2
    p = make()
    d = DelayedPoseSource(p)
    pf, facade = p.loc._pf, d.loc
    robot = OwnRobotOnly(d, SEARCH_POSE)
    phases = [
        ('approach', {'t': .4, 'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': .01, 'duration_s': .4}),
        ('align', {'t': 1., 'kind': 'hold'}),
        ('grasp', {'t': 1.4, 'kind': 'arm', 'servo_id': 1, 'pulse': 1200}),
        ('lift', {'t': 1.8, 'kind': 'arm', 'servo_id': 3, 'pulse': 1000}),
        ('carry', {'t': 2.4, 'kind': 'mecanum', 'forward': .05, 'left': .01, 'turn': .01, 'duration_s': .4}),
        ('lower', {'t': 3., 'kind': 'arm', 'servo_id': 3, 'pulse': 740}),
        ('open', {'t': 3.4, 'kind': 'arm', 'servo_id': 1, 'pulse': 2000}),
    ]
    try:
        for _, row in phases:
            d.on_command(row)
            d.report(row['t'] + .2)
            if row['kind'] == 'arm':
                robot.servo[row['servo_id']] = row['pulse']
            assert p.loc._pf is pf and d.loc is facade
            assert pf.t == pytest.approx(row['t'] + .04)
        assert pf.stats['resets'] == 0 and p.prior['source'] == 'setup:r1:own_dock'
        d.on_frame(3.8, FRAME)  # queued pre-scan image must never be a new fix
        d.report(3.85)
        before = pf.px.copy(), pf.logw.copy(), pf.scale.copy(), copy.deepcopy(pf.rng.bit_generator.state)
        servo_before = dict(p.servo), pf.own_servo_cmd_t, pf.last_servo_cmd_t
        calls_before = p.worker.seq
        queued = []

        def queue(pulses, now, **kw):
            queued.append(dict(pulses))
            for sid, pulse in pulses.items():
                d.on_command({'t': now, 'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
                robot.servo[sid] = pulse

        ctl = ProviderM2DoorStudent.__new__(ProviderM2DoorStudent)
        ctl.driver = robot
        ctl.pregrasp_done, ctl.pregrasp_sweeps, ctl.version = False, 0, 'v3'
        ctl.arm, ctl.set = NS(queue=queue), lambda *a, **kw: None
        ctl._queue_grasp(3.85)
        assert p.loc._pf is pf and d.loc is facade
        for got, want in zip((pf.px, pf.logw, pf.scale), before[:3]):
            np.testing.assert_array_equal(got, want)
        assert pf.rng.bit_generator.state == before[3]
        assert (p.servo, pf.own_servo_cmd_t, pf.last_servo_cmd_t) == servo_before
        assert d.loc.estimate()['last_fix_t'] is None and p.last_obs is None
        assert queued[0] == {**LOOK_P20, 6: PREGRASP_PANS_V2[0]}
        with pytest.raises(RuntimeError):
            d.init_prior(DOCK, source='GT/dock checkpoint reset')
        # Real adapter's first p20 command, then all eight own pan observations.
        for i, pan in enumerate(PREGRASP_PANS_V2):
            t = 4. + i
            d.on_command({'t': t, 'kind': 'look', 'pan_pulse': pan})
            d.on_frame(t + .7, FRAME)
            d.report(t + .85)
            if i == 0:
                assert d.loc.estimate()['last_fix_t'] is None
            report = d.report(t + .86)
            assert report.last_fix_t == pytest.approx(t + .7)
            assert report.t_est <= t + .7 + 1e-9
        assert p.worker.seq == calls_before + 8
        assert p.loc._pf is pf and d.loc is facade and pf.stats['resets'] == 0
        assert [r['row'] for r in p.lifecycle if r['event'] == 'own_command'][1:8] == [r for _, r in phases]
        d.on_command({'t': 12., 'kind': 'arm', 'servo_id': 1, 'pulse': 1200})  # regrasp command
        d.report(12.2)
        assert p.servo[1] == 1200 and pf.t == pytest.approx(12.04)
        assert all(r['available_sim_s'] == pytest.approx(r['captured_sim_s'] + .16) for r in d.timing)
    finally:
        d.close()
    assert p.worker.closed and d.record()['closed'] and p.record()['closed']
    assert p.record()['applied_perception_delay_s'] == 0.
    assert d.record()['applied_perception_delay_s'] == .16
    d.close()
    with pytest.raises(RuntimeError, match='closed'):
        d.report(13.)


@pytest.mark.parametrize('bad', ['stale', 'duplicate', 'future', 'missing', 'rejected', 'failed'])
def test_invalid_frame_or_response_never_becomes_a_fresh_fix(bad):
    p = make()
    d = DelayedPoseSource(p)
    try:
        d.on_frame(.4, FRAME)
        d.report(.56)
        old_fix, calls = p.loc.last_scan_t, p.worker.seq
        if bad == 'stale':
            d.report(2.)
            d.on_frame(2.1, FRAME, captured_sim_s=.8)
        elif bad == 'duplicate':
            d.on_frame(.7, FRAME, captured_sim_s=.4)
        elif bad == 'future':
            d.on_frame(.7, FRAME, captured_sim_s=.9)
        else:
            if bad == 'rejected':
                p.worker.fn = lambda *a: None
            elif bad == 'failed':
                p.worker.fail_at = p.worker.seq
            d.on_frame(.8, None if bad == 'missing' else FRAME)
            d.report(1.)
        assert p.loc.last_scan_t == old_fix
        if bad in ('stale', 'duplicate', 'future', 'missing'):
            assert p.worker.seq == calls
        if bad == 'failed':
            assert not d.report(1.1).initialized and not d.loc.estimate()['initialized']
            d.begin_relocalization(1.2, SEARCH_POSE)
            assert not d.report(2.).initialized
    finally:
        d.close()


@pytest.mark.parametrize('corruption', ['missing', 'stale', 'future', 'boolean_seq', 'truth'])
def test_closed_worker_json_rejects_wrong_response_identity(corruption):
    row = _reply()
    if corruption == 'missing':
        del row['obs']
    elif corruption in ('stale', 'future', 'boolean_seq'):
        row['seq'] = {'stale': 0, 'future': 2, 'boolean_seq': True}[corruption]
    else:
        row['GT'] = [1., 2., 3.]
    with pytest.raises(vp.ProtocolError):
        vp.check_reply(row, seq=1 if corruption in ('stale', 'future', 'boolean_seq') else 0,
                       bgr_sha256='a' * 64, n_columns=len(vp.columns()))


def test_worker_sim_charge_cannot_duplicate_wrapper_delay():
    p = make()
    try:
        p.cfg = {**p.cfg, 'sim_time_charge': {'charged': True}}
        with pytest.raises(ValueError, match='duplicate'):
            DelayedPoseSource(p)
    finally:
        p.close()


@pytest.mark.parametrize('runtime_input', ['profile', 'scan', 'command'])
def test_queued_runtime_input_locks_the_setup_prior_boundary(runtime_input):
    p = make(prior=False)
    d = DelayedPoseSource(p)
    try:
        if runtime_input == 'profile':
            d.set_motion_profile(0., None)
        elif runtime_input == 'scan':
            d.begin_observation(0., SEARCH_POSE)
        else:
            d.on_command({'t': 0., 'kind': 'hold'})
        with pytest.raises(RuntimeError):
            d.init_prior(DOCK, source='late dock')
    finally:
        d.close()


@pytest.mark.parametrize('failure', ['none', 'missing_prior', 'post_setup'])
def test_study_host_owns_each_worker_and_closes_on_exit_or_setup_failure(monkeypatch, failure):
    from scripts import zone_study_provider_p03 as runner
    from tests.test_zone_pair_tag_boundary_matrix import host_fixture
    from tests.test_zone_own_executor import MAP
    spec, student = host_fixture(monkeypatch, MAP)
    if failure == 'missing_prior':
        del spec['pose_priors']['r2']
    if failure == 'post_setup':
        def fail(*a):
            raise ValueError('injected post-setup failure')
        monkeypatch.setattr(runner.zone_eval_top, 'apply_to_world', fail)
    poses = [make(prior=False) for _ in range(3)]
    providers = iter(DelayedPoseSource(p) for p in poses)
    monkeypatch.setattr(runner, 'build_pose_provider', lambda *a: next(providers))
    try:
        if failure == 'missing_prior':
            with pytest.raises(runner.zi.ContractViolation, match='own dock prior'):
                runner.StudyTeamHost(spec, student, root=runner.ROOT, provider_spec={'uses_landmark_tags': False})
            assert poses[0].worker.closed and poses[1].worker.closed
        elif failure == 'post_setup':
            with pytest.raises(ValueError, match='injected post-setup failure'):
                runner.StudyTeamHost(spec, student, root=runner.ROOT, provider_spec={'uses_landmark_tags': False})
            assert all(p.worker.closed for p in poses)
        else:
            host = runner.StudyTeamHost(spec, student, root=runner.ROOT, provider_spec={'uses_landmark_tags': False})
            assert len({id(p.loc._pf) for p in poses}) == 3
            assert all(p.prior['source'] == 'scenario own dock' for p in poses)
            host.close(); host.close()
            assert all(p.worker.closed for p in poses)
    finally:
        for p in poses:
            p.close()


def test_candidate_writer_adds_provider_receipt_and_retains_legacy_summary(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace as NS
    from scripts import zone_study_provider_p03 as runner

    summary = {'stop': 'fake-only'}
    monkeypatch.setattr(runner.legacy, 'write_outputs', lambda *a, **kw: summary)
    p = make()
    d = DelayedPoseSource(p)
    try:
        host = NS(robots={'r1': NS(executor=NS(pose=d))})
        result = runner.write_outputs(tmp_path, {}, {}, 'no_comm', {}, 'fake', host,
                                      None, None, 'fake-only', None, {}, 0., (), True)
        assert result is summary
        receipt = json.loads((tmp_path / 'robots/r1/inputs/pose_provider.json').read_text())
        assert receipt['applied_perception_delay_s'] == .16
        assert receipt['provider']['provider'] == runner.PROVIDER_ID
        assert receipt['provider']['prior']['setup_only'] is True
    finally:
        d.close()


def test_candidate_factory_uses_new_provider_and_one_delay_without_rebinding_defaults(monkeypatch):
    from harness import vision_pose_source_p03
    from scripts import zone_study_provider_p03 as runner

    worker = InProcessWorker(lambda seq, own_bgr: None)
    monkeypatch.setattr(vision_pose_source_p03, 'VisionWorkerClient', lambda cfg: worker)
    static = vp.load_json(VisionPoseSourceV2.map_file)
    spec = runner.provider_spec(static['map_id'])
    d = runner.build_pose_provider(spec, static, CALIB['params'], 0)
    try:
        assert type(d) is DelayedPoseSource
        assert type(d.provider) is VisionPoseSourceV2
        assert d.provider.provider_id == spec['provider_id'] == runner.PROVIDER_ID
        assert d.source.startswith(spec['source_label_prefix'])
        assert d.record()['applied_perception_delay_s'] == .16
        assert d.provider.record()['applied_perception_delay_s'] == 0.
        with pytest.raises(runner.zi.ContractViolation, match='exact explicit'):
            runner.build_pose_provider({**spec, 'factory': 'harness.vision_pose_source:VisionPoseSourceV2'},
                                       static, CALIB['params'], 0)
    finally:
        d.close()
    assert worker.closed
