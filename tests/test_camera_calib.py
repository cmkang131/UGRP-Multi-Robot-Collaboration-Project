"""camera_calib=measured_v1 (default off): offline board calibration, versioned+hashed file, runtime toggle (no renderer, no sim)."""
import json, math, shutil
from pathlib import Path
import numpy as np
import pytest
from harness import camera_calib as cc
from harness import active_camera as ac
from harness.active_camera import SEARCH, LOOK_AHEAD

FILE = Path(cc.FILE)


@pytest.fixture(autouse=True)
def _off():
    cc.set_mode('off'); yield; cc.set_mode('off')


def test_default_off_is_nominal_fk():
    assert cc.mode() == 'off'
    assert ac.pitch(SEARCH) == pytest.approx(-18.08, abs=1e-6)
    assert cc.status()['calibrated_hits'] == 0


def test_file_hash_pin_and_schema():
    data = cc.load()
    assert data['schema'] == 'ugrp.camera_calib_measured.v1' and data['option'] == 'measured_v1'
    assert {tuple(p['servo_pulses_1_3_4_5_6']) for p in data['postures']} >= {cc.key(SEARCH), cc.key(LOOK_AHEAD)}
    for p in data['postures']:  # a real fit: sub-pixel reprojection, held-out ground error far below nominal FK's
        assert p['reprojection_rms_px'] < 1.0
        g = p['ground_error']
        assert g['holdout_measured_v1']['median_cm'] < 1.0 < g['holdout_nominal_fk']['median_cm']
        assert p['n_holdout'] >= 5


def test_hash_mismatch_refused(tmp_path):
    bad = tmp_path/'c.json'; bad.write_bytes(FILE.read_bytes()+b' ')
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        cc.load(bad)


def test_on_applies_measured_extrinsics_and_off_restores():
    nominal = ac.transform(SEARCH)
    cc.set_mode('measured_v1')
    on = ac.transform(SEARCH)
    assert ac.pitch(SEARCH) == pytest.approx(-18.25, abs=.05) and on[0][2] < nominal[0][2] and on[0][0] == pytest.approx(.0768, abs=.002)  # E2E-world fit: 4.8 cm nearer the base, 2 mm lower, 0.17 deg down
    assert np.allclose(np.linalg.det(on[1]), 1., atol=1e-9) and np.allclose(on[1].T@on[1], np.eye(3), atol=1e-9)
    assert cc.status()['calibrated_hits'] >= 2 and cc.status()['nominal_fallbacks'] == 0
    cc.set_mode('off')
    assert np.allclose(ac.transform(SEARCH)[0], nominal[0]) and np.allclose(ac.transform(SEARCH)[1], nominal[1])


def test_masks_stay_on_nominal_fk():
    cc.set_mode('measured_v1')
    o_cal, _ = ac.goal_camera(SEARCH, 'camera_v3')
    o_mask, _ = ac.mask_camera(SEARCH, 'camera_v3')
    assert o_mask[0] == pytest.approx(0.12524423, abs=1e-6) and o_cal[0] < 0.08


def test_uncalibrated_posture_falls_back_counted():
    cc.set_mode('measured_v1')
    odd = dict(SEARCH); odd[6] = 1537
    assert np.allclose(ac.transform(odd)[0], ac.transform(odd, calibrated=False)[0])
    st = cc.status()
    assert st['nominal_fallbacks'] == 1 and cc.key(odd) in [tuple(k) for k in st['uncalibrated_postures']]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError): cc.set_mode('measured_v2')


def test_projection_caches_do_not_leak_between_modes():
    from harness import e2e_rgb_vo as vo
    uv = np.array([[320., 300.]])
    off = vo.ground(dict(SEARCH), uv)[0]
    cc.set_mode('measured_v1')
    on = vo.ground(dict(SEARCH), uv)[0]
    cc.set_mode('off')
    again = vo.ground(dict(SEARCH), uv)[0]
    assert np.linalg.norm(on-off) > .05 and np.allclose(off, again)


def test_cone_view_planner_ground_projection_uses_calibration():
    from harness import e2e_b_standoff as S
    b = S.load_cone_board(); pose = [3.2, -2.1, 0.]
    off = S.project_floor(b['cones'], pose)[0]
    cc.set_mode('measured_v1')
    on = S.project_floor(b['cones'], pose)[0]
    assert np.nanmax(np.abs(on-off)) > 5.
    cc.set_mode('off')
    kept, n, found = S.plan_standoffs(cones=True, top=3)
    assert n['admitted'] > 0 and kept and all(k['min_cone_height_px'] >= S.CONE_CFG['min_blob_px'] for k in kept)
