"""BRANCH_NAV_V5 (2026-10-21): opt-in nav scene profile v5. No mujoco/warp/GPU.

Default OFF keeps the v230_r5 queue/stack values unchanged; the v5 selection
replaces only ``scene_profile`` and is bound env <-> queue <-> stack_values.
"""
import json
import os

import pytest

from harness import e2ewarp_nav_gate as gate
from harness import e2ewarp_nav_scene as scene
from scripts import run_e2e_warp as runner
from sim import scene_contrast_v5 as contrast

FORWARD = 0.004024203361827748
YAW = 1.7275488814064257
ENV_KEYS = (scene.SCENE_ENV, gate.GATE_MODE_ENV, gate.ARRIVAL_ENV, gate.CALIBRATION_ENV)


@pytest.fixture(autouse=True)
def _clear_env():
    saved = {k: os.environ.pop(k) for k in ENV_KEYS if k in os.environ}
    yield
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    os.environ.update(saved)


def _calibration(tmp_path):
    payload = dict(schema=gate.CALIBRATION_SCHEMA, measured=True, measured_n=60,
                   source_sha='d182b67aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                   constants=dict(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW),
                   per_robot={r: dict(forward_m_per_pct_s=FORWARD, yaw_deg_per_pct_s=YAW)
                              for r in gate.ROBOTS})
    path = tmp_path / 'nav_gate_calibration.json'
    path.write_text(json.dumps(payload))
    return path


def _prepare(tmp_path, monkeypatch, name='run'):
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R5
    os.environ[gate.ARRIVAL_ENV] = 'odom_projection'
    os.environ[gate.CALIBRATION_ENV] = str(_calibration(tmp_path))
    monkeypatch.setattr(runner, 'require_navigation', lambda *_a, **_k: {})
    monkeypatch.setattr(runner, 'head', lambda: 'f' * 40)
    a = runner.build_parser().parse_args(
        ['--mode', 'nav', '--prepare', '--e2e-warp-batch', 'on_v1', '--seed', '601',
         '--nworld', '1', '--condition', 'peer_en', '--nav-sim-budget-s', '60',
         '--arrival-odom-projection',
         '--output', str(tmp_path / name)])
    a.command = ['test']
    return runner.prepare(a)


def test_profiles_exist_and_differ_only_in_pickup_paint():
    v5 = contrast.PROFILES[scene.V5_PROFILE]
    v6 = contrast.PROFILES[scene.V6_PROFILE]
    assert v5['rgb'] == v6['rgb'] and v5['pattern'] == v6['pattern']
    assert v6['assets'] == scene.V5_PROFILE
    assert 'light_scale' not in v5 and v6['light_scale'] == 0.30
    # v6 light 0.30 is factor 1.0 on the base: the lighting is the same.
    assert contrast._base_light_scale() == 0.30
    assert contrast.profile_record(scene.V6_PROFILE)['light_scale_factor_vs_base'] == 1.0
    assert 'pickup' not in v5 and v6['pickup'] == 'neutral_grid_v1'


def test_selection_is_default_off_and_rejects_unknown():
    assert scene.scene_selection() == dict(name='stack', profile=None)
    assert scene.scene_selection('') == dict(name='stack', profile=None)
    assert scene.scene_selection('v5')['profile'] == scene.V5_PROFILE
    with pytest.raises(ValueError, match='NAV_SCENE_PROFILE_UNKNOWN'):
        scene.scene_selection('v6')
    values = dict(scene_profile=scene.V6_PROFILE, other=1)
    same, deviation = scene.apply_scene_profile(values)
    assert same is values and deviation is None
    assert scene.scene_queue_fields() == {}


def test_v5_replaces_only_scene_profile_and_requires_the_v6_stack():
    values = dict(scene_profile=scene.V6_PROFILE, other=1)
    sel = scene.scene_selection('v5')
    out, deviation = scene.apply_scene_profile(values, sel)
    assert out == dict(scene_profile=scene.V5_PROFILE, other=1)
    assert values['scene_profile'] == scene.V6_PROFILE  # input untouched
    assert deviation['id'] == 'scene_profile' and deviation['applied'] == scene.V5_PROFILE
    assert deviation['approval']['authority'] in ('user', 'coordinator')
    assert 'BRANCH_NAV_V5' in deviation['approval']['evidence']
    with pytest.raises(ValueError, match='NAV_SCENE_STACK_PROFILE_UNEXPECTED'):
        scene.apply_scene_profile(dict(scene_profile=scene.V5_PROFILE), sel)


def test_validate_fails_closed_both_ways():
    sel = scene.scene_selection('v5')
    values, deviation = scene.apply_scene_profile(dict(scene_profile=scene.V6_PROFILE), sel)
    queue = dict(stack_values=values, stack_deviations=[deviation],
                 **scene.scene_queue_fields(sel))
    assert scene.validate_scene_queue(queue, sel) is queue
    off = scene.scene_selection()
    with pytest.raises(ValueError, match='NAV_SCENE_PROFILE_MARKER_WITHOUT_ENV'):
        scene.validate_scene_queue(queue, off)
    bare = dict(stack_values=values, stack_deviations=[deviation])
    with pytest.raises(ValueError, match='NAV_SCENE_PROFILE_V5_WITHOUT_ENV'):
        scene.validate_scene_queue(bare, off)
    plain = dict(stack_values=dict(scene_profile=scene.V6_PROFILE), stack_deviations=[])
    with pytest.raises(ValueError, match='NAV_SCENE_PROFILE_MARKER_MISMATCH'):
        scene.validate_scene_queue(plain, sel)
    wrong = dict(queue, stack_values=dict(scene_profile=scene.V6_PROFILE))
    with pytest.raises(ValueError, match='NAV_SCENE_PROFILE_STACK_VALUE_MISMATCH'):
        scene.validate_scene_queue(wrong, sel)
    with pytest.raises(ValueError, match='NAV_SCENE_PROFILE_DEVIATION_REQUIRED'):
        scene.validate_scene_queue(dict(queue, stack_deviations=[]), sel)
    assert scene.validate_scene_queue(plain, off) is plain


def test_prepare_default_off_is_unchanged_and_v5_is_bound(tmp_path, monkeypatch):
    off = _prepare(tmp_path, monkeypatch, 'off')
    assert off['stack_values']['scene_profile'] == scene.V6_PROFILE
    assert 'nav_scene_profile' not in off and 'nav_scene_profile_selection' not in off
    assert not [d for d in off['stack_deviations'] if d['id'] == 'scene_profile']
    scene.validate_scene_queue(off)

    os.environ[scene.SCENE_ENV] = 'v5'
    on = _prepare(tmp_path, monkeypatch, 'on')
    assert on['stack_values']['scene_profile'] == scene.V5_PROFILE
    assert on['nav_scene_profile'] == scene.V5_PROFILE
    assert on['nav_scene_profile_selection'] == 'v5'
    assert [d['applied'] for d in on['stack_deviations'] if d['id'] == 'scene_profile'] == [
        scene.V5_PROFILE]
    scene.validate_scene_queue(on)
    # The rest of the queue (gate mode markers, stack digest) is identical.
    strip = lambda q: {k: v for k, v in q.items()
                       if k not in ('stack_values', 'stack_deviations', 'nav_scene_profile',
                                    'nav_scene_profile_selection', 'rejection_table')}
    assert strip(on) == strip(off)
    written = json.loads((tmp_path / 'on' / 'queue.json').read_text())
    assert written['nav_scene_profile'] == scene.V5_PROFILE
    # the stack checker accepts the deviation entry format
    from scripts.check_current_stack import approvals
    stack = json.loads((runner.ROOT / 'configs/current_stack.json').read_text())
    rules = {r['id']: r for r in stack['rules']}
    assert approvals([on], rules)['scene_profile']['applied'] == scene.V5_PROFILE


def test_scene_env_requires_nav_mode(tmp_path):
    os.environ[scene.SCENE_ENV] = 'v5'
    with pytest.raises(SystemExit):
        runner.main(['--output', str(tmp_path / 'x')])


def test_v5_band_modes_are_r5_with_only_the_hue_floor_raised():
    from harness import e2ewarp_selfnav as sn
    r5 = gate.GATE_MODES[gate.GATE_MODE_V230_R5]
    for mode, profile, floor in ((gate.GATE_MODE_V230_R5_V5H111, 'gpu_calib_v5_h111', 111.0),
                                 (gate.GATE_MODE_V230_R5_V5H112, 'gpu_calib_v5_h112', 112.0)):
        spec = gate.GATE_MODES[mode]
        assert {k: v for k, v in spec.items() if k != 'zone_profile'} == \
            {k: v for k, v in r5.items() if k != 'zone_profile'}
        assert spec['zone_profile'] == profile
        band = sn.GPU_CALIB_PROFILES[profile]
        assert band['hue_cv'] == (floor, 114.0)
        assert {k: v for k, v in band.items() if k != 'hue_cv'} == \
            {k: v for k, v in sn.GPU_CALIB_V230.items() if k != 'hue_cv'}
        assert mode in gate.SLOT_GATE_MODES and mode in gate.STAGE2_GATE_MODES
        assert mode in gate.PROJECTION_GATE_MODES and mode in gate.ACQUISITION_QUALITY_MODES
    # frozen profiles untouched
    assert sn.GPU_CALIB_V230['hue_cv'] == (110.0, 114.0)
    assert sn.DEFAULT_GPU_CALIB_PROFILE == 'gpu_calib_v1'
    assert gate.DEFAULT_GATE_MODE == gate.GATE_MODE_V1


def test_v5_band_mode_queue_requires_scene_v5(tmp_path, monkeypatch):
    os.environ[scene.SCENE_ENV] = 'v5'
    q = _prepare(tmp_path, monkeypatch, 'b0')
    assert q['nav_gate_mode'] == 'v230_r5' and q['nav_zone_profile'] == 'gpu_calib_v230'
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R5_V5H111
    queue = gate.gate_queue_fields(601, calibration=gate.load_calibration(
        os.environ[gate.CALIBRATION_ENV]))
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    gate.validate_gate_queue(queue)
    assert queue['nav_zone_profile'] == 'gpu_calib_v5_h111'
    assert queue['nav_slot_stage2_ground_m'] == 1.5
    with pytest.raises(ValueError, match='NAV_V5_BAND_REQUIRES_SCENE_V5'):
        scene.validate_scene_queue(queue, scene.scene_selection('stack'))
