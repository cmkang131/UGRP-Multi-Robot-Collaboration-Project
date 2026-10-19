"""Frozen prereg + render-preflight consistency for the 2026-10-19 v230_fwd24 mode."""
import importlib.util
import pathlib

import pytest

from harness import e2ewarp_nav_gate as gate
from harness import e2ewarp_selfnav as sn

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG = ROOT / 'experiments/2026-10-19-nav-v230-fwd24/PREREG.md'
RENDER = ROOT / 'experiments/2026-10-19-nav-v230-fwd24/render_check.py'


def load_render_check():
    spec = importlib.util.spec_from_file_location('nav_v230_render_check', RENDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_approved_mode_is_v230_fwd24_with_the_frozen_constants():
    mode = gate.GATE_MODES[gate.GATE_MODE_V230_FWD24]
    assert mode['zone_profile'] == 'gpu_calib_v230'
    assert mode['acquisition_mode'] == sn.ACQUISITION_FORWARD_THEN_SEARCH
    assert mode['forward_cap_m'] == gate.FORWARD_ACQUISITION_CAP_M == 2.4
    assert mode['zone_min_component'] == 600
    assert gate.GATE_MODES[gate.GATE_MODE_V1]['forward_cap_m'] == 0.0
    assert gate.DEFAULT_GATE_MODE == gate.GATE_MODE_V1
    assert sn.GPU_CALIB_V230['val'] == (30.0, 230.0)
    assert sn.GPU_CALIB_V230['hue_cv'] == (110.0, 114.0)
    assert sn.GPU_CALIB_V230['sat_min'] == 100.0
    assert sn.GPU_CALIB_V230['min_pixels'] == 600


def test_prereg_and_render_check_freeze_the_approved_conditions():
    assert PREREG.is_file() and RENDER.is_file()
    pre = PREREG.read_text()
    assert 'FROZEN' in pre and 'V 30–230' in pre and '2.4 m' in pre
    assert 'detections == 0' in pre and 'min_component 600' in pre
    assert 'pooling 금지' in pre and 'calibration_source_sha' in pre
    module = load_render_check()
    assert module.FORWARD_CAP_M == gate.FORWARD_ACQUISITION_CAP_M
    assert module.MIN_COMPONENT_PX == sn.GPU_CALIB_V230['min_pixels']
    assert module.SPAWN_X == pytest.approx(-0.8982)
    # ② needs >=3 zone-free poses and ③ >=4 poses on the 2.4 m leg.
    assert len(module.ZONE_FREE_POSES) >= 4
    assert len(module.PATH_X) >= 4
    assert module.SPAWN_X + module.FORWARD_CAP_M == pytest.approx(1.5018)
    assert max(module.PATH_X) <= module.SPAWN_X + module.FORWARD_CAP_M
    assert min(module.PATH_X) == pytest.approx(module.SPAWN_X)
    compile(RENDER.read_text(), str(RENDER), 'exec')


def test_render_check_poses_record_is_json_safe():
    module = load_render_check()
    out = module.poses_record({'a': {'r1': [1, 2, 3, 0.1], 'r2': [4, 5, 6, 0.2]}})
    assert out == {'a': {'r1': [1.0, 2.0, 3.0, 0.1],
                         'r2': [4.0, 5.0, 6.0, 0.2]}}
