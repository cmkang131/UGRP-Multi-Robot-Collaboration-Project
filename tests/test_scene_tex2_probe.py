"""Pure offline checks: never construct/import a MuJoCo model or renderer."""
from types import SimpleNamespace
import json
import shutil
import subprocess

import numpy as np
import pytest

from scripts import probe_scene_tex2 as probe


def test_mac_main_rejects_before_source_or_simulator(monkeypatch, tmp_path):
    monkeypatch.setattr(probe.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(probe, 'run', lambda *a: pytest.fail('Mac must not render'))
    with pytest.raises(SystemExit, match='2'):
        probe.main(['--output', str(tmp_path / 'new'), '--source-sha', 'a' * 40,
                    '--setup-proof', str(tmp_path / 'missing'), '--execute'])
    assert not (tmp_path / 'new').exists()


def test_setup_proof_requires_named_pass_and_records_bytes(tmp_path):
    path = tmp_path / 'ops.md'
    path.write_text('other: PASS\ngcp2setup: PENDING\n')
    with pytest.raises(ValueError, match='PASS_REQUIRED'):
        probe.setup_proof(path)
    path.write_text('gcp2setup: PASS | source frozen\n')
    record = probe.setup_proof(path)
    assert record['sha256'] == probe.sha256(path.read_bytes())
    assert record['pass_line'] == 'gcp2setup: PASS | source frozen'
    path.write_text(path.read_text() + 'gcp2setup: FAIL | budget-stop\n')
    with pytest.raises(ValueError, match='PASS_REQUIRED'):
        probe.setup_proof(path)


def test_physics_fingerprint_detects_friction_but_ignores_appearance():
    model = SimpleNamespace(geom_friction=np.array([[1., .005, .0001]]),
                            body_mass=np.array([0., 1.1]), geom_matid=np.array([0]),
                            geom_rgba=np.array([[1., 1., 1., 1.]]), tex_data=np.array([14]),
                            opt=SimpleNamespace(timestep=.002, iterations=50))
    before = probe.physics_fingerprint(model)
    model.geom_rgba[:] = 0
    model.geom_matid[:] = 4
    model.tex_data[:] = 125
    assert probe.physics_fingerprint(model) == before
    model.geom_friction[0, 0] = .8
    assert probe.physics_fingerprint(model)['sha256'] != before['sha256']
    model.geom_friction[0, 0] = 1.
    model.opt.timestep = .004
    assert probe.physics_fingerprint(model)['sha256'] != before['sha256']


def test_mask_score_records_missing_support_without_fabricated_success():
    zeros = np.zeros((8, 8), bool)
    empty = probe.mask_score(zeros, zeros)
    assert empty['iou'] is None and empty['recall'] is None
    expected = zeros.copy()
    expected[:2] = True
    row = probe.mask_score(zeros, expected)
    assert row['tp'] == 0 and row['fn'] == 16 and row['recall'] == 0.


def test_surface_metrics_do_not_invent_mask_boundary_features():
    bgr = np.full((480, 640, 3), 120, np.uint8)
    wall = np.zeros((480, 640), bool)
    wall[:240] = True
    result = probe.surface_metrics(bgr, {'wall': wall, 'floor': ~wall})
    assert result['wall']['orb_count'] == result['floor']['orb_count'] == 0
    assert result['wall_floor_colour_separation']['median_delta_E76'] == 0.


def test_colour_metrics_assigns_false_positive_surface_and_target_support():
    image = np.array([[[0, 0, 255], [255, 255, 0]], [[120, 120, 120], [120, 120, 120]]], np.uint8)
    ranges = [{'label': 'red', 'ranges': [((0, 150, 35), (6, 255, 255))]}]
    masks = {name: np.zeros((2, 2), bool) for name in ('wall', 'floor', 'box_red')}
    masks['wall'][0, 0] = True
    result = probe.colour_metrics(image, masks, ranges)['red']
    assert result['pixels'] == 1
    assert result['surface_false_pixels']['wall'] == 1
    assert result['target_support_pixels']['box_red'] == 0


def test_direct_rgb_and_pil_masks_are_measured_independently():
    image = np.array([[[10, 10, 200], [200, 10, 10]], [[90, 200, 10], [200, 200, 200]]], np.uint8)
    masks = probe.colour_range_masks(image, [])
    assert masks['crate_blue'][0, 1]
    assert masks['crate_teal'][1, 0]
    assert masks['PIL_beam'].shape == image.shape[:2]
    assert not any(mask[1, 1] for mask in masks.values())


@pytest.mark.skipif(shutil.which('zstd') is None, reason='zstd not installed')
def test_large_json_storage_returns_surviving_path_and_verifies_roundtrip(tmp_path):
    original = tmp_path / 'large.json'
    value = {'rows': ['same raw record'] * 5000}
    saved = probe.write(original, value)
    assert saved.name == 'large.json.zst' and saved.exists() and not original.exists()
    restored = subprocess.check_output(['zstd', '-q', '-d', '-c', str(saved)])
    assert json.loads(restored) == value
    metadata = json.loads((tmp_path / 'large.json.compression.json').read_text())
    assert probe.sha256(restored) == metadata['original_sha256']
    # Repeated progress writes replace this probe's own compressed index safely.
    saved2 = probe.write(original, {'rows': ['changed record'] * 5000})
    assert saved2 == saved


def test_funnel_is_cumulative_and_has_explicit_rejection_reason():
    rows = [dict(id='good', frame_rendered=True, frame_analysed=True,
                 physics_identical=True, camera_identical=True),
            dict(id='broken', frame_rendered=True, frame_analysed=False,
                 failure_category='HOST_ERROR', failure_reason='JPEG decode failed'),
            dict(id='changed', frame_rendered=True, frame_analysed=True,
                 physics_identical=False)]
    result = probe.funnel(rows, 3)
    assert [r['cumulative_pass_n'] for r in result['stages']] == [3, 2, 1, 1]
    assert [r['rejected_n'] for r in result['stages']] == [0, 1, 1, 0]
    for stage in result['stages']:
        for row in stage['rejections']:
            assert row['category'] and row['reason'] and row['blocking_object']
            assert 'minimum_gap_m' in row


def test_fixture_view_selection_uses_existing_walls_and_audit_distances():
    static = {'bounds_m': [0., 8., 0., 6.], 'obstacles': [
        {'id': 'wall_west', 'center_m': [0., 3.], 'half_extents_m': [.025, 3.]},
        {'id': 'wall_east', 'center_m': [8., 3.], 'half_extents_m': [.025, 3.]}]}
    result = probe.wall_views(static)
    assert [r['distance_m'] for r in result] == list(probe.WALL_DISTANCES_M)
    assert result[0]['wall'] != result[1]['wall']
    assert all(r['minimum_wall_gap_m'] >= r['distance_m'] - 1e-12 for r in result)


def test_all_four_maps_resolve_without_widening_provider_allowlist():
    import json
    from scripts.generate_scene_textures import MAPS
    from harness import zone_final_environment as final, zone_heldout_maps as heldout
    for path in MAPS:
        static = json.loads(path.read_text())
        base, selected = probe.scene_map_selection(static)
        original, _, _ = final.resolve(base)
        if selected == 'off':
            assert original == static
        else:
            assert selected in heldout.IDS
            assert original['map_id'] == heldout.BASE_ID
            assert heldout.load(selected) == static


def test_positive_cases_only_extend_view_zero_and_plan_264_frames():
    assert probe.poses_for_view(0) == probe.POSES + probe.POSITIVE_POSES
    assert probe.poses_for_view(1) == probe.POSES
    assert probe.planned_case_count(2) == 11
    assert 4 * probe.planned_case_count(2) * len(probe.ROBOTS) * len(probe.PROFILES) == 264


def test_positive_postures_use_existing_folded_mode():
    assert all(probe.pose_pwm_mode(pose) == 'FOLDED' for pose in probe.POSITIVE_POSES)
    assert probe.pose_pwm_mode('drive') == 'FOLDED'
    assert probe.pose_pwm_mode('high') == probe.pose_pwm_mode('high_beam_peer_occluded') == 'HIGH'


def test_palette_layout_uses_real_extents_and_keeps_four_boxes_separate():
    boxes = {name: [.017, .020, .016] for name in ('cyan', 'red', 'green', 'yellow')}
    layout = probe.palette_layout((0., 0., 0.), boxes)
    assert sorted(p[0] for p in layout.values()) == [.75, .75, .9, .9]
    for a, pose_a in layout.items():
        for b, pose_b in layout.items():
            if a == b:
                continue
            assert (abs(pose_a[0] - pose_b[0]) >= boxes[a][0] + boxes[b][0] or
                    abs(pose_a[1] - pose_b[1]) >= boxes[a][1] + boxes[b][1])
