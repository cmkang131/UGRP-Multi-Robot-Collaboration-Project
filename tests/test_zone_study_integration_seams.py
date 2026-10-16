"""Integrated zone study runner (issue #223): the seams around the trial.

Pose provider registry and interface, contract v2 of the tags_v2 map placement,
the host link's abort (drops scheduled macros, holds), the eval-only referee and
the workflow/CI registration. Simulator-free, like ``test_zone_study_integration.py``.
"""
from __future__ import annotations

import hashlib
import base64
import copy
import json
import math
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.zone_own_team_host import _RobotSlot
from harness import zone_own_executor as zox  # noqa: E402
from harness import zone_study_contract as A  # noqa: E402
from harness import zone_study_integration as zi  # noqa: E402
from harness.zone_study_inputs import OrderSheetSource  # noqa: E402
from harness.zone_study_scenarios import bundle_for  # noqa: E402

SCENARIO = json.loads((ROOT / 'configs/zone_study_integration/i1_cyan_three_slots.json').read_text())
MAP_ID = 'zone_wide_door_tags_v2'
MAP = json.loads((ROOT / 'maps/zones' / f'{MAP_ID}.json').read_text())
CALIB = json.loads((ROOT / 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json').read_text())
FRAME = sorted((ROOT / 'tests/fixtures/markerless_box/blue_floor_release').glob('*-wrist.jpg'))[0].read_bytes()
BUNDLE = bundle_for(SCENARIO)
SHEET = OrderSheetSource(SCENARIO, BUNDLE).sheet()
ROWS_Y = (-2.45, -1.65, -.85, -.05, .75)
SEED = 700


def executor(rid='r1'):
    return zox.ZoneOwnExecutor(rid, MAP, CALIB['params'], SHEET, skill_factory=lambda o, robot_id: None,
                               pose_estimate_cls=tuple, search_rows_y=ROWS_Y)


class OneFrameLink:
    """A robot with one stored real wrist JPEG at t=0 and a real (idle) executor."""

    def __init__(self, rid):
        self.robot_id, self.ex = rid, executor(rid)

    def clock(self):
        return 1.3

    def frame_at(self, t):
        return zi.OwnFrame(0, 0.0, FRAME, hashlib.sha256(FRAME).hexdigest())

    def belief(self):
        return self.ex.belief_projection()

    def job(self):
        return None

    def call(self, api, *args):
        return getattr(self.ex, api)(*args)


# ---------------------------------------------------------------- pose provider seam
def test_tags_temporary_provider_is_labelled_temporary_and_hashed():
    spec = zi.pose_provider_spec('tags_temporary', map_id=MAP_ID)
    assert spec['temporary'] and not spec['research_result'] and spec['note_ko'] == zi.TEMPORARY_NOTE_KO
    rec = zi.provider_record(spec)
    assert rec['label'] == {'pose_provider': 'tags_temporary', 'temporary': True, 'research_result': False,
                            'note_ko': '임시, 표식 사용, 연구 결과 아님'}
    assert len(rec['record_sha256']) == 64 and set(rec['source_files_sha256']) == set(spec['source_files'])
    provider = zi.build_pose_provider(spec, MAP, CALIB['params'], 700)
    assert provider.source.startswith('owncam_pf_v2:')


@pytest.mark.parametrize('provider_id, map_id', [('vision_zero_tag', MAP_ID), ('', MAP_ID), (None, MAP_ID),
                                                 (0, MAP_ID), ('tags_temporary', 'zone_wide_door'),
                                                 ('tags_temporary', None)])
def test_unknown_provider_or_unregistered_map_is_refused(provider_id, map_id):
    with pytest.raises(A.ContractViolation):
        zi.pose_provider_spec(provider_id, map_id=map_id)


def _write_registry(tmp_path, **override):
    data = json.loads(zi.PROVIDER_CONFIG.read_text())
    entry = {**data['providers']['tags_temporary'], **override}
    data['providers'] = {'vision_stub': entry}
    path = tmp_path / 'providers.json'
    path.write_text(json.dumps(data))
    return path


def test_a_new_provider_drops_in_by_config_without_runner_change(tmp_path, monkeypatch):
    (tmp_path / 'kiro_vision_stub.py').write_text(textwrap.dedent('''
        from harness.owncam_pose_source import OwnCamPoseSource

        class VisionStub(OwnCamPoseSource):
            def __post_init__(self):
                super().__post_init__()
                self.source = 'owncam_pf_vision_stub:00000000'
    '''))
    monkeypatch.syspath_prepend(str(tmp_path))
    path = _write_registry(tmp_path, factory='kiro_vision_stub:VisionStub', version='vision_stub_v0',
                           source_label_prefix='owncam_pf_vision_stub:', uses_landmark_tags=False,
                           temporary=False, research_result=True, note_ko='표식 0개 시험용 대역')
    spec = zi.pose_provider_spec('vision_stub', map_id=MAP_ID, path=path)
    provider = zi.build_pose_provider(spec, MAP, CALIB['params'], 700)
    assert provider.source == 'owncam_pf_vision_stub:00000000'
    ex = executor()
    ex._require_owncam(provider.source, 'pose provider')                      # the executor's own M1 check


@pytest.mark.parametrize('override, match', [
    ({'source_label_prefix': 'gt_pose:'}, 'does not start'),
    ({'uses_landmark_tags': True, 'temporary': False}, 'must be temporary'),
    ({'uses_landmark_tags': True, 'note_ko': '연구 결과'}, 'must be temporary'),
])
def test_provider_registry_refuses_mislabelled_entries(tmp_path, override, match):
    path = _write_registry(tmp_path, **override)
    with pytest.raises(A.ContractViolation, match=match):
        spec = zi.pose_provider_spec('vision_stub', map_id=MAP_ID, path=path)
        zi.build_pose_provider(spec, MAP, CALIB['params'], 700)


def test_provider_without_the_executor_interface_or_with_a_gt_label_is_refused():
    spec = zi.pose_provider_spec('tags_temporary', map_id=MAP_ID)
    good = zi.build_pose_provider(spec, MAP, CALIB['params'], 1)

    class NoLoc:
        source = good.source
        on_command = on_frame = report = set_motion_profile = staticmethod(lambda *a: None)
    with pytest.raises(A.ContractViolation, match='loc'):
        zi.check_pose_provider(NoLoc(), spec)
    good.source = 'gt_pose_from_simulator'
    with pytest.raises(A.ContractViolation):
        zi.check_pose_provider(good, spec)
    good.source = None
    with pytest.raises(A.ContractViolation):
        zi.check_pose_provider(good, spec)


def test_the_study_modules_import_no_simulator():
    program = ('import sys; import harness.zone_study_integration, harness.owncam_pose_source; '
               'import scripts.run_zone_study_integration; '
               'assert not ({"mujoco", "sim.multi_masterpi_production"} & sys.modules.keys())')
    subprocess.run([sys.executable, '-c', program], cwd=ROOT, check=True)


# ---------------------------------------------------------------- contract v2 (tags_v2 map placement)
def _payload():
    trial = zi.IntegratedTrial(SCENARIO, condition='no_comm', seed=SEED,
                               links={r: OneFrameLink(r) for r in zox.ROBOTS}, horizon_s=10., map_bundle=BUNDLE)
    trial.snapshot(type('C', (), {'actor': 'r1', 'started_sim_s': 1.3})())
    return trial.build_inputs('r1', sim_time_s=1.3, request_id='req_t').payload_dict()


def test_contract_v2_accepts_the_tags_v2_landmark_placement():
    payload = _payload()
    placement = payload['static_map']['public_map']['landmarks']['placement']
    assert {'near_door_spacing_m', 'near_door_radius_m', 'door_posts'} <= set(placement)
    assert A.CONTRACT_VERSION == 'ugrp.zone_study_contract.v2'
    # Integration HEAD 844d9dfb and core r7 3b86842c computed the same v2 registry.
    assert A.registry_sha256() == 'c9bb55567a82eef535e7b296ae69f35d5a08e8372479a56ef14c1ac76f08037c'
    A.validate_robot_payload(payload, seed=SEED)


@pytest.mark.parametrize('mutate', [
    lambda p: p['door_posts'].update(live_pose_m=[1., 2.]),
    lambda p: p['door_posts'].update(width_m='wide'),
    lambda p: p['door_posts'].update(tag_center_heights_m=None),
    lambda p: p['door_posts'].update(tag_center_heights_m='0.15'),
    lambda p: p['door_posts'].update(tag_center_heights_m=[0.15, {'x': 1}]),
    lambda p: p.update(door_posts=[0.05]),
    lambda p: p.update(near_door_radius_m='1 m'),
    lambda p: p.update(near_door_radius_m=None),
])
def test_contract_v2_keeps_the_placement_closed_and_typed(mutate):
    payload = _payload()
    mutate(payload['static_map']['public_map']['landmarks']['placement'])
    assert A.payload_violations(payload)


# ---------------------------------------------------------------- abort drops host macros (#221 P1)
def test_host_link_abort_drops_scheduled_macros_and_holds_now():
    from scripts.run_zone_study_integration import HostRobotLink

    class Port:
        def capture(self, camera='robot_cam'):
            raise AssertionError('not captured in this test')

    ex = executor()
    slot = _RobotSlot('r1', Port(), ex)
    holds = []
    host = zox.OwnCamTeamHost.__new__(zox.OwnCamTeamHost)
    host.closed, host.pairs = False, None
    host.robots, host.api_calls = {'r1': slot}, []
    host.world = type('W', (), {'data': type('D', (), {'time': 12.3})()})()
    host._hold = lambda rid, now: holds.append((rid, now))
    link = HostRobotLink(host, 'r1')
    assert link.call('hold', 5.)['accepted']
    slot.timeline = [(12.4, [{'kind': 'arm', 'servo_id': 3, 'pulse': 900}]), (12.5, ['hold'])]
    slot.capture_after, slot.next_decide = True, 99.
    ack = link.call('abort', 'wait_requested')
    assert ack['accepted'] and slot.timeline == [] and not slot.capture_after and slot.next_decide == 12.3
    assert holds == [('r1', 12.3)] and link.aborts[-1]['dropped_macro_commands'] == 2
    assert ex.step(12.3) == {'mode': 'tick', 'commands': [{'kind': 'hold'}]}
    assert not link.call('abort', 'again')['accepted'] and holds == [('r1', 12.3)]   # nothing to abort: no hold


def test_referee_counts_a_box_only_after_it_rests_in_a_zone():
    from harness import zone_study_referee as zr
    zone_a = MAP['regions']['zone_A']['center_m']
    ref = zr.Referee([{'order_id': 'o1', 'kind': 'cyan', 'count': 1, 'identity': 'kind_fungible',
                       'destination_zone': 'A'}], MAP)
    for i in range(int((zr.SETTLE_S + 1) / .05)):
        t = round(i * .05, 3)
        ref.observe(t, {'b0': {'kind': 'cyan', 'x': zone_a[0], 'y': zone_a[1], 'yaw': 0., 'z': .016 if i > 10 else .09,
                               'held': False, 'speed': 0.},
                        'b1': {'kind': 'cyan', 'x': 0., 'y': 0., 'yaw': 0., 'z': .016, 'held': False, 'speed': 0.}})
        if t < .55 + zr.SETTLE_S - .1:
            assert not ref.history
    assert [(r['item_id'], r['zone'], r['sim_s']) for r in ref.record()['deliveries']] == [('b0', 'A', .55)]


# ---------------------------------------------------------------- registration
@pytest.mark.parametrize('map_id, profile', [
    ('zone_wide_corridor', 'zone_eval_top_v2'),
    ('zone_wide_corridor_tags_v1', 'zone_eval_top_v2'),
    (MAP_ID, 'zone_eval_top_v1'),
])
def test_eval_top_profile_applies_after_setup_without_changing_robot_maps_or_cameras(monkeypatch, map_id, profile):
    import numpy as np
    from scripts import run_zone_study_integration as runner

    static = json.loads((ROOT / 'maps/zones' / f'{map_id}.json').read_text())
    before = copy.deepcopy(static)
    cameras = {c['name']: SimpleNamespace(pos=np.array(c['position_m'], dtype=float),
                                         quat=np.array(c['quaternion_wxyz'], dtype=float),
                                         fovy=np.array([c['fov_y_deg']], dtype=float))
               for c in static['top_cameras']}
    cameras['r1__robot_cam'] = SimpleNamespace(pos=np.array([.1, .2, .3]),
                                              quat=np.array([1., 0., 0., 0.]), fovy=np.array([100.]))
    own_camera = copy.deepcopy(cameras['r1__robot_cam'])
    forward = []
    monkeypatch.setitem(sys.modules, 'mujoco', SimpleNamespace(mj_forward=lambda m, d: forward.append(m)))

    def init_host(host, *args, **kwargs):
        host.static, host.eval_only = static, {}
        host.world = SimpleNamespace(model=SimpleNamespace(camera=cameras.__getitem__), data=object())
        host.robots = {}
        for rid in zox.ROBOTS:
            ex = executor(rid)
            ex.map = copy.deepcopy(static)
            host.robots[rid] = _RobotSlot(rid, SimpleNamespace(capture=lambda camera: None), ex)
    monkeypatch.setattr(zox.OwnCamTeamHost, '__init__', init_host)
    monkeypatch.setattr(zi, 'build_pose_provider', lambda *args: SimpleNamespace(source='owncam_pf_v2:test'))
    host = runner.StudyTeamHost({}, {}, root=ROOT, provider_spec={})
    config = runner.evaluation_top_config(static)
    assert config['profile']['id'] == profile
    assert host.eval_only['top_camera']['profile'] == config['profile']
    for applied, expected in zip(host.eval_only['top_camera']['applied'], config['cameras'], strict=True):
        assert applied['name'] == expected['name']
        for field in ('position_m', 'quaternion_wxyz', 'fov_y_deg'):
            assert applied[field] == pytest.approx(expected[field], abs=1e-6)
    assert forward == [host.world.model]
    assert static == before and all(s.executor.map == before for s in host.robots.values())
    assert host.eval_static['eval_top_profile'] == config['profile']
    assert host.eval_static['top_cameras'] == config['cameras']
    if profile == 'zone_eval_top_v2':
        assert list(cameras['cctv_top_north_east'].pos) == [3.4, .8, 3.]
        assert config['cameras'] != static['top_cameras']
    else:
        assert config['cameras'] == static['top_cameras']
    for field in ('pos', 'quat', 'fovy'):
        assert np.array_equal(getattr(cameras['r1__robot_cam'], field), getattr(own_camera, field))


@pytest.mark.parametrize('condition', A.MAIN_CONDITIONS)
def test_corridor_eval_overlay_never_changes_robot_request_bytes(condition):
    from harness.zone_study_scenarios import load
    from scripts import run_zone_study_integration as runner

    scenario = load('s4_narrow_door_standoff')
    bundle = bundle_for(scenario)
    static = json.loads((ROOT / bundle['map_file']).read_text())
    trial = zi.IntegratedTrial(scenario, condition=condition, seed=SEED,
                               links={r: OneFrameLink(r) for r in zox.ROBOTS}, horizon_s=10., map_bundle=bundle)

    def request():
        call = SimpleNamespace(actor='r1', started_sim_s=1.3, call_id='call_own')
        trial.snapshot(call)
        return trial.prepare_call(call).request
    before = request()
    overlay = runner.zone_eval_top.eval_static_map(static, runner.evaluation_top_config(static)['profile']['id'])
    after = request()
    assert before == after
    assert overlay['top_cameras'] != static['top_cameras']
    assert [image['label'] for image in after['images']] == ['CURRENT OWN WRIST RGB']
    assert 'eval_top' not in json.dumps(after) and 'top_cameras' not in json.dumps(after)


def test_host_link_refuses_top_camera_requests_and_mislabeled_frames():
    from scripts.run_zone_study_integration import HostRobotLink

    captured = []
    def capture(camera):
        captured.append(camera)
        return {'camera': 'cctv_top_north_east', 'robot_id': 'r1', 'image': base64.b64encode(FRAME).decode(),
                'sha256': hashlib.sha256(FRAME).hexdigest(), 'sim_time': 0.}
    slot = _RobotSlot('r1', SimpleNamespace(capture=capture), executor())
    link = HostRobotLink(SimpleNamespace(robots={'r1': slot}), 'r1')
    with pytest.raises(A.ContractViolation, match='own robot_cam'):
        slot.port.capture('cctv_top_north_east')
    assert captured == []
    with pytest.raises(RuntimeError, match='foreign or corrupted'):
        slot.port.capture('robot_cam')
    assert link.frame_at(1.) is None


def test_runner_is_registered_and_collected_by_ci():
    rows = json.loads((ROOT / 'configs/simulation_workflows.json').read_text())['workflows']
    row = next(r for r in rows if r['id'] == 'zone-study-integration-run')
    assert row['entry'] == 'scripts/run_zone_study_integration.py' and (ROOT / row['docs']).is_file()
    from scripts import run_ci_tests
    assert {'tests/test_zone_study_integration.py', 'tests/test_zone_study_integration_seams.py'} <= \
        set(run_ci_tests.TEST_PATTERNS)


def test_quantum_is_the_sim_cost_quantum():
    assert zi.QUANTUM_S == zi.cost_params_for().quantum_s == .1 and math.isclose(zi.WAIT_HOLD_S, 10.)
