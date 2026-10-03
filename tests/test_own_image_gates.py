"""Own-image gates recalibrated for floor_light_v1 (no simulator, no renderer, no model)."""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness import own_image_gates as gates_module
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_vision as vision
from harness.opencv_wall_observation import observations

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/highpose_recorded_frames'


@pytest.fixture(autouse=True)
def legacy_frame_gate_around_test():
    # Runtime construction elsewhere installs the process-level gate; start and end from the v1 values.
    vision.use_gates(None)
    yield
    vision.use_gates(None)


def recorded():
    return json.loads((ROOT/gates_module.PATH).read_text())


def obs_from_jpeg(data, *, now=10.):
    return {'camera': 'robot_cam', 'robot_id': 'r1', 'frame_id': 3, 'sim_time': now - .05,
            'image': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}


def test_registry_pins_the_gates_file_and_a_changed_file_fails_closed(tmp_path):
    gates = c.own_image_gates()
    doc = recorded()
    assert gates['values'] == {k: float(v) for k, v in doc['values'].items()}
    assert gates['sha256'] == hashlib.sha256((ROOT/gates_module.PATH).read_bytes()).hexdigest()
    assert c.registry()['own_image_gates']['sha256'] == gates['sha256']
    assert c.bundle('zone_wide_door_geometry_v3', 'p03')['source_sha256'][gates_module.PATH] == gates['sha256']
    edited = tmp_path/'gates.json'
    edited.write_text(json.dumps({**doc, 'values': {**doc['values'], 'wall_band_saturation_max': 80}}))
    with pytest.raises(ValueError, match='hash mismatch'):
        gates_module.load(edited, gates['sha256'])
    edited.write_text(json.dumps({**doc, 'render_profile': 'other'}))
    with pytest.raises(ValueError, match='mismatch'):
        gates_module.load(edited)


def test_values_follow_the_recorded_rules_and_acceptance_passed():
    doc = recorded()
    v, p = doc['values'], doc['results']['frame_stats_percentiles']['cal']
    assert v['frame_contrast_spread_min'] == round(.5*p['spread']['0.1'], 1)
    assert v['frame_value_std_min'] == round(.5*p['std']['0.1'], 2)
    assert doc['acceptance_passed'] and all(doc['acceptance_passed'].values())
    assert doc['legacy_values'] == gates_module.LEGACY
    assert all(len(h) == 64 for runs in doc['data_sha256'].values() for h in runs.values())
    # calibration and evaluation never share a run
    cal = {r if isinstance(r, str) else r[0] for k in ('column_calibration', 'frame_calibration')
           for r in doc['splits'][k]['runs']}
    ev = {r if isinstance(r, str) else r[0] for k in ('column_evaluation', 'frame_evaluation')
          for r in doc['splits'][k]['runs']}
    assert not cal & ev


def test_frame_gate_accepts_recorded_flat_floor_views_that_the_v1_dev_values_rejected():
    frames = [(FIXTURES/row['file']).read_bytes() for row in json.loads((FIXTURES/'manifest.json').read_text())['frames']]
    assert len(frames) == 68
    legacy = [vision.valid_frame_ob(obs_from_jpeg(f), 'r1', 10.) for f in frames]
    vision.use_gates(c.own_image_gates()['values'])
    new = [vision.valid_frame_ob(obs_from_jpeg(f), 'r1', 10.) for f in frames]
    assert sum(not ok for ok in legacy) >= 20        # recorded: 22 of 68 valid views were rejected as invalid
    assert all(new)
    for admit in (vision.valid_frame, vision.valid_frame_ob):
        for level in (0, 128):                         # blank/covered views stay invalid
            flat = cv2.imencode('.jpg', np.full((480, 640, 3), level, np.uint8))[1].tobytes()
            assert admit(obs_from_jpeg(flat), 'r1', 10.) is False


def synthetic_wall(step=True):
    """Band candidate at column 200 (boundary row 250); optional real luminance step across it."""
    from harness import vision_loc_protocol as vp
    real, _ = vp.load_vis3()
    scan = SimpleNamespace(columns=np.array([200]), vb=np.array([[250.]]), vt=np.array([[100.]]))
    vl = SimpleNamespace(mp=SimpleNamespace(undistort=lambda bgr: bgr, detect_boundaries=lambda *a: scan),
                         EDGE=real.EDGE, ColumnObs=real.ColumnObs)
    bgr = np.full((480, 640, 3), 100, np.uint8)
    if step:
        bgr[:250] = 140
        bgr[250:] = 60
    return vl, bgr


def hsv_patch(bgr, s, rows=(120, 160)):
    bgr[rows[0]:rows[1], 195:206] = cv2.cvtColor(np.uint8([[[100, s, 120]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return bgr


def test_observer_keeps_a_real_step_and_drops_a_shading_gradient_with_the_recorded_gates():
    values = c.own_image_gates()['values']
    vl, flat = synthetic_wall(step=False)
    assert observations(vl, flat, object()).informative.tolist() == [True]                 # v1: no step test
    assert observations(vl, flat, object(), values).informative.tolist() == [False]        # recorded gates
    vl, wall = synthetic_wall()
    assert observations(vl, wall, object(), values).informative.tolist() == [True]


def test_observer_saturation_limit_separates_tinted_walls_from_coloured_occluders():
    values = c.own_image_gates()['values']
    vl, wall = synthetic_wall()
    tinted, coloured = hsv_patch(wall.copy(), 100), hsv_patch(wall.copy(), 220)
    assert observations(vl, tinted, object()).informative.tolist() == [False]              # v1: S >= 80 drops a tinted wall
    assert observations(vl, tinted, object(), values).informative.tolist() == [True]
    assert observations(vl, coloured, object(), values).informative.tolist() == [False]    # occluders still dropped
