"""Scheduler integration and final-v3 admission; no World, renderer or worker."""
from dataclasses import replace
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.zone_study_contract import ContractViolation
from harness import zone_target_environment as admission
from scripts import run_zone_target_checks as runner
from scripts.zone_target_bundle import load_config, candidate_bundle
from scripts.zone_target_host import TargetStudyHost


def active_scheduler(monkeypatch):
    from tests.test_zone_own_executor_target import backend_fixture, detection, FakeDelivery
    from harness.zone_target_identity import CueFrame
    from harness.zone_own_team_host import _RobotSlot
    executor, _ = backend_fixture()
    executor.inner.on_frame = lambda *args: SimpleNamespace(initialized=False)
    executor.inner.on_command = lambda row: None
    assert executor.jobs.submit('order-cyan', 'a', item_id='cyan_1', now_sim_s=1.)['state'] == 'running'
    host = TargetStudyHost.__new__(TargetStudyHost)
    host.pairs = None
    slot = _RobotSlot('r1', None, executor)
    host.robots = {'r1': slot}
    captures, commands = [], []
    host._hold = lambda rid, now: commands.append(('hold', rid, now))
    host._apply = lambda rid, cmd, now: (commands.append((cmd['kind'], rid, now)),
                                       executor.on_command({**cmd, 't': now}))
    executor.cancel_scheduled = lambda now, reason: host._drop_scheduled('r1', now, reason)
    executor.inner.cancel = lambda now, reason: setattr(executor.inner, 'job', None)

    def observe(now, obs, report):
        previous = executor.recognizer.frame
        frame = CueFrame('r1', previous.sequence + 1, now, str(previous.sequence + 1) * 64,
                         previous.rgb_sha256, (detection(previous=('a',)),))
        executor.recognizer.frame = frame
        return frame

    executor.recognizer.observe = observe

    def capture(rid, now):
        captures.append((rid, now))
        executor.on_frame(now, {}, None)

    host._capture_raw = capture
    return host, slot, executor, captures, commands


def test_active_target_arm_macro_periodic_and_completion_share_one_frame(monkeypatch):
    host, slot, executor, captures, commands = active_scheduler(monkeypatch)
    slot.timeline = [(1.2, [{'kind': 'arm', 'servo_id': 3, 'pulse': 740}])]
    slot.capture_after = True
    host._capture('r1', 1.2)  # periodic capture at the macro's completion tick
    refreshed = len(executor.job.ctl.views)
    host._run_timeline('r1', 1.2)
    host._capture('r1', 1.2)  # another explicit request in this same tick
    assert not slot.dead and slot.exception is None
    assert captures == [('r1', 1.2)]
    assert len(executor.job.ctl.views) == refreshed
    assert commands == [('arm', 'r1', 1.2)]
    assert executor.jobs.claim('order-cyan')['observed_count'] == 0
    assert slot.timeline == [] and not slot.capture_after
    host._capture('r1', 1.4)
    assert len(captures) == 2 and len(executor.job.ctl.views) == refreshed + 1
    assert not slot.dead


def test_capture_dedup_is_per_robot_and_failed_capture_is_not_cached():
    host = TargetStudyHost.__new__(TargetStudyHost)
    host.robots = {r: SimpleNamespace(dead=False) for r in ('r1', 'r2')}
    captures = []
    host._capture_raw = lambda rid, now: captures.append((rid, now))
    for rid in ('r1', 'r1', 'r2', 'r2'):
        host._capture(rid, 1.)
    assert captures == [('r1', 1.), ('r2', 1.)]
    def fail(*args):
        raise OSError(28, 'fake ENOSPC')
    host._capture_raw = fail
    with pytest.raises(OSError): host._capture('r1', 1.2)
    host._capture_raw = lambda rid, now: captures.append((rid, now))
    host._capture('r1', 1.2)
    assert captures[-1] == ('r1', 1.2)


def test_reordered_host_capture_still_stops_active_target(monkeypatch):
    host, slot, executor, captures, commands = active_scheduler(monkeypatch)
    host._capture('r1', 1.2)
    host._capture('r1', 1.1)
    assert slot.dead and slot.exception['type'] == 'ContractViolation'
    assert executor.target is None


def test_equal_time_identity_frames_cannot_count_as_two_observations():
    from tests.test_zone_own_executor_target import Fixture, detection
    f = Fixture()
    frame = f.frame(detection())
    with pytest.raises(ContractViolation):
        f.jobs.observe(replace(frame, sequence=2, previous_rgb_sha256=frame.rgb_sha256))


def test_final_environment_bundle_is_bound_but_not_claimed_runnable():
    cfg = load_config()
    bundle = candidate_bundle()
    parent = bundle['final_environment']
    assert parent['execution_bundle_id'] == 'zone-final-environment-v84'
    assert parent['map_id'] == cfg['map_id'] == 'zone_wide_door_geometry_v3'
    assert parent['robot_model'] == cfg['robot_model'] == 'masterpi_v3'
    assert parent['provider']['factory'] == 'harness.vision_pose_source_final:FinalVisionPoseSource'
    assert parent['calibration_contract']['status'] == 'DRAFT_UNMEASURED'
    assert bundle['controller_inputs'] == ['own_rgb', 'static_map', 'own_command_history', 'delivered_messages']
    assert not bundle['runnable']
    assert bundle['blocked_on'] == ['measured_final_v3_calibration',
                                     'final_v3_target_rgb_and_manipulation_adapter']


@pytest.mark.parametrize('field,value', [('map_id', 'zone_wide_door_geometry_v2'),
    ('robot_model', 'masterpi_v2'), ('pose_provider', 'vision_zero_tag_v2'),
    ('render_profile', 'floor_light_v1'), ('weld', True), ('sensor', 'on_v1')])
def test_final_environment_rejects_incompatible_combinations(field, value):
    cfg = load_config()
    cfg[field] = value
    with pytest.raises(ValueError): admission.environment_contract(cfg)


def test_v2_calibration_is_rejected_and_valid_measurements_do_not_admit_v2_skill(monkeypatch):
    from harness import zone_final_environment as env
    cfg = load_config()
    cfg['student']['calibration'] = 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'
    cfg['student']['calibration_sha256'] = env.sha(env.ROOT / cfg['student']['calibration'])
    with pytest.raises(ValueError, match='combination mismatch'):
        admission.require_execution(cfg)
    # Only measurement validation is faked: a capability gap cannot be filled
    # by a calibration file, a config approval flag or a renamed map.
    monkeypatch.setattr(env, 'measured_calibration', lambda *a, **k: {})
    cfg.update(runnable=True, physical_ready=True)
    with pytest.raises(ValueError, match='final_v3_target_rgb_and_manipulation_adapter'):
        admission.require_execution(cfg)


def test_cli_and_direct_api_refuse_before_output_lock_native_or_inference(monkeypatch, tmp_path):
    import sim.workflow_manager as wm
    from scripts import agent_lock
    from harness.vision_loc_client import VisionWorkerClient
    fail = lambda *a, **kw: pytest.fail('admission reached a forbidden side effect')
    monkeypatch.setattr(wm, 'git_identity', lambda root: {'source_sha': 'a'*40, 'source_dirty': False})
    monkeypatch.setattr(agent_lock, 'acquire', fail)
    monkeypatch.setattr(VisionWorkerClient, '__init__', fail)
    monkeypatch.setattr(TargetStudyHost, '__init__', fail)
    out = tmp_path / 'new-parent' / 'run'
    with pytest.raises(ValueError, match='T13_FINAL_ENVIRONMENT_NOT_READY'):
        runner.main(['--group', 't13a', '--execute', '--expected-source-sha', 'a'*40, '--output', str(out)])
    cfg = load_config()
    with pytest.raises(ValueError, match='T13_FINAL_ENVIRONMENT_NOT_READY'):
        runner.execute_cell(cfg, 'I1', 'no_comm', out, {}, 'a'*64)
    assert not out.parent.exists()


def test_final_v3_cannot_enter_legacy_host_projection_or_delivery():
    from harness.zone_target_executor import TargetOwnExecutor, TargetDelivery
    from harness.zone_target_rgb import OwnRGBRecognizer
    from harness.zone_final_environment import resolve
    from tests.test_zone_own_executor import make
    from tests.test_zone_own_executor_target import catalogue
    cfg = load_config()
    with pytest.raises(ValueError, match='FINAL_V3_TARGET_HOST'):
        TargetStudyHost({'map': cfg['map_id']}, cfg['student'])
    static = resolve(cfg['map_id'])[0]
    with pytest.raises(ContractViolation, match='FINAL_V3_TARGET_RGB_PROJECTION'):
        OwnRGBRecognizer('r1', static)
    inner = make()
    inner.map = static
    with pytest.raises(ContractViolation, match='FINAL_V3_TARGET_RGB_AND_MANIPULATION'):
        TargetOwnExecutor(inner, visual_catalogue=catalogue(), cancel_scheduled=lambda *a: None)
    with pytest.raises(ContractViolation, match='FINAL_V3_TARGET_MANIPULATION'):
        TargetDelivery(inner, None, None, None, None)
