"""Real-trial evaluation: ceiling camera calibration/reading on synthetic pictures, and the metric script."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
cv2 = pytest.importorskip('cv2')

from harness import overhead_v1 as ov  # noqa: E402
from real_robot import overhead_real as orl  # noqa: E402
import importlib.util as ilu  # noqa: E402

spec = ilu.spec_from_file_location('real_trial_metrics', ROOT / 'scripts' / 'real_trial_metrics.py')
rtm = ilu.module_from_spec(spec); spec.loader.exec_module(rtm)

W, H = 1280, 960
K = np.array([[700., 0, W / 2 + 7], [0, 700., H / 2 - 5], [0, 0, 1]])
DIST = np.array([-0.08, 0.02, 0.001, -0.001, 0.])


def _camera_pose():
    # 2.5 m above (2.0, -0.9), looking down, tilted 2 deg and turned 1 deg (a real mount is never exact)
    R0 = np.array([[1., 0, 0], [0, -1, 0], [0, 0, -1]])                    # image x = arena +x, image y = arena -y
    tilt, _ = cv2.Rodrigues(np.array([math.radians(2), math.radians(-1), math.radians(1)]))
    R = tilt @ R0
    C = np.array([2.0, -0.9, 2.5])
    return cv2.Rodrigues(R)[0].ravel(), -R @ C


def _paint(img, dictionary, marker_id, corners_world, rvec, tvec, inner=0.75):
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    px = 200
    mk = cv2.aruco.generateImageMarker(d, marker_id, int(px * inner))
    card = np.full((px, px), 255, np.uint8)
    o = (px - mk.shape[0]) // 2
    card[o:o + mk.shape[0], o:o + mk.shape[0]] = mk
    # map the marker's own corners (not the card's) exactly: a homography is only exact at the 4 points it is
    # built from, and the lens distortion bends everything in between
    cw = np.asarray(corners_world, float); c = cw.mean(axis=0)
    inner_world = c + (cw - c) * (mk.shape[0] / px)
    dst, _ = cv2.projectPoints(inner_world, rvec, tvec, K, DIST)
    a, b = o, o + mk.shape[0]
    Hm = cv2.getPerspectiveTransform(np.float32([[a, a], [b, a], [b, b], [a, b]]), dst.reshape(4, 2).astype(np.float32))
    warped = cv2.warpPerspective(card, Hm, (W, H), borderValue=0)
    mask = cv2.warpPerspective(np.full((px, px), 255, np.uint8), Hm, (W, H)) > 0
    img[mask] = warped[mask]


def _square(cx, cy, z, side, yaw):
    # corners in reading order: top-left, top-right, bottom-right, bottom-left; top edge points along yaw
    f, l = np.array([math.cos(yaw), math.sin(yaw)]), np.array([-math.sin(yaw), math.cos(yaw)])
    h = side / 2
    pts = [(-h, h), (h, h), (h, -h), (-h, -h)]   # (along f, along l) -> top edge from left to right = +f
    return [[cx + a * f[0] + b * l[0], cy + a * f[1] + b * l[1], z] for a, b in pts]


def _floor_scene(rvec, tvec, cards):
    img = np.full((H, W), 128, np.uint8)
    for i, (x, y) in cards.items():
        _paint(img, orl.FLOOR_DICT, i, _square(x, y, 0., 0.20, 0.), rvec, tvec)
    return img


def test_pose_and_robot_reading_on_a_tilted_distorted_camera():
    rvec, tvec = _camera_pose()
    cards = {0: (0.6, -2.3), 1: (3.4, -2.3), 2: (3.4, 0.5), 3: (0.6, 0.5), 4: (2.0, -0.9)}
    rv, tv, rms, used = orl.calibrate_pose(_floor_scene(rvec, tvec, cards), K, DIST, cards)
    assert rms < 1.0 and sorted(used) == sorted(cards)
    cam = orl.Camera(K, DIST, rv, tv)
    assert np.allclose(cam.center, [2.0, -0.9, 2.5], atol=0.02)

    img = np.full((H, W), 128, np.uint8)
    truth = {'r1': (1.2, -1.7, 0.4), 'r2': (2.9, 0.1, -2.0)}
    for rid, (x, y, yaw) in truth.items():
        cx, cy = x + ov.CARD_AT[0] * math.cos(yaw), y + ov.CARD_AT[0] * math.sin(yaw)
        _paint(img, orl.ROBOT_DICT, ov.TOP_ID0 - 1 + int(rid[1:]), _square(cx, cy, orl.CARD_PLANE_Z, ov.CARD_M, yaw),
               rvec, tvec)
    _paint(img, orl.FLOOR_DICT, orl.SYNC_CARD_ID, _square(0.9, 0.2, 0., 0.2, 0.), rvec, tvec)
    poses, sync = orl.RealOverheadReader(cam).read(img)
    assert sync and set(poses) == set(truth)
    for rid, (x, y, yaw) in truth.items():
        px, py, pyaw, side = poses[rid]
        assert math.dist((px, py), (x, y)) < 0.01
        assert abs(math.degrees(math.atan2(math.sin(pyaw - yaw), math.cos(pyaw - yaw)))) < 2.5   # ~20 px marker: 1.6 deg p95 over 75 poses
        assert abs(side - ov.CARD_M * 0.75) < 0.005


def test_pose_needs_four_floor_cards():
    rvec, tvec = _camera_pose()
    cards = {0: (0.6, -2.3), 1: (3.4, -2.3), 2: (3.4, 0.5)}
    with pytest.raises(ValueError, match='at least 4'):
        orl.calibrate_pose(_floor_scene(rvec, tvec, cards), K, DIST, cards)


def _trial_folder(tmp_path, events, operator, overhead, orders=None):
    trial = {'trial_id': 't', 'kind': 'coop', 'cap_s': 900, 'release_reach_m': 0.2,
             'signs': {'12': [0.9, -0.1, 1.1, 0.1], '13': [1.9, -0.1, 2.1, 0.1]},
             'orders': orders or [{'id': 'o1', 'kind': 'red', 'sign': 12, 'count': 1, 'after': None},
                                  {'id': 'o2', 'kind': 'cyan', 'sign': 13, 'count': 1, 'after': 'o1'}]}
    (tmp_path / 'trial.json').write_text(json.dumps(trial))
    (tmp_path / 'operator.json').write_text(json.dumps(operator))
    (tmp_path / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
    (tmp_path / 'overhead.jsonl').write_text('\n'.join(json.dumps(r) for r in overhead))
    return tmp_path


def _overhead():
    rows = []
    for k in range(0, 1201):
        t = 100 + k * 0.5
        rows.append({'t': t, 'frame': k, 'sync': k == 2,
                     'poses': {'r1': [0.8, 0.0, 0.0, 0.064] if t >= 400 else [0.0, 0.0, 0.0, 0.064],
                               'r2': [1.8, 0.0, 0.0, 0.064]}})
    return rows


def test_metrics_in_order_trial(tmp_path):
    ev = [{'t': 100, 'event': 'start'},
          {'t': 400, 'event': 'release_done', 'robot': 'r1', 'item': 'red_1', 'sign': 12},
          {'t': 500, 'event': 'release_done', 'robot': 'r2', 'item': 'cyan_1', 'sign': 13},
          {'t': 520, 'event': 'finished', 'robot': 'r1'}, {'t': 530, 'event': 'finished', 'robot': 'r2'}]
    op = {'final': {'red_1': {'kind': 'red', 'sign': 12}, 'cyan_1': {'kind': 'cyan', 'sign': 13}}, 'phone_sync_s': 3.0}
    out = rtm.score(_trial_folder(tmp_path, ev, op, _overhead()))
    assert out['R0'] == 1.0 and out['order_violations'] == 0 and out['completion_s'] == 430
    assert out['disagreements'] == 0 and out['clock']['phone_offset_s'] == 2.0
    assert out['motion']['robots']['r2']['seen_fraction'] == 1.0


def test_metrics_order_violation_and_misplacement(tmp_path):
    ev = [{'t': 100, 'event': 'start'},
          {'t': 400, 'event': 'release_done', 'robot': 'r1', 'item': 'red_1', 'sign': 12},
          {'t': 300, 'event': 'release_done', 'robot': 'r2', 'item': 'cyan_1', 'sign': 13},
          {'t': 520, 'event': 'finished', 'robot': 'r1'}]
    op = {'final': {'red_1': {'kind': 'red', 'sign': None}, 'cyan_1': {'kind': 'cyan', 'sign': 13}}}
    out = rtm.score(_trial_folder(tmp_path, ev, op, _overhead()))
    # red box ended at no sign (operator) -> o1 unfilled; o2 placed while o1 unfilled -> violation, not counted
    assert out['R0'] == 0.0 and out['order_violations'] == 1
    assert out['completion_s'] == 900 and not out['all_finished']   # r2 never finished
    assert out['disagreements'] == 1                                  # ceiling + log say sign 12, operator says none


def test_pick1_handover_error_in_station_frame(tmp_path):
    trial = {'trial_id': 'p', 'kind': 'pick1', 'cap_s': 150, 'stations': {'red_1': {'x': 1.0, 'y': 2.0, 'yaw': math.pi / 2}}}
    (tmp_path / 'trial.json').write_text(json.dumps(trial))
    (tmp_path / 'operator.json').write_text(json.dumps({'final': {}, 'attempts': [{'lifted': True, 'held_3s': True}]}))
    ev = [{'t': 10, 'event': 'start'}, {'t': 40, 'event': 'handover', 'robot': 'r1', 'item': 'red_1'}]
    (tmp_path / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in ev))
    # robot 5 mm short (along) and 8 mm to the right of the station, turned 2 deg; one misread frame
    rows = [{'t': 39.6 + 0.1 * k, 'poses': {'r1': [1.008 if k != 3 else 1.3, 1.995, math.pi / 2 + math.radians(2), .064]}}
            for k in range(9)]
    (tmp_path / 'overhead.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    out = rtm.score(tmp_path)
    h = out['handover'][0]
    assert out['pick'] == {'success': 1, 'attempts': 1}
    assert h['along_mm'] == -5.0 and h['lateral_mm'] == -8.0 and abs(h['yaw_deg'] - 2.0) < 1e-6
