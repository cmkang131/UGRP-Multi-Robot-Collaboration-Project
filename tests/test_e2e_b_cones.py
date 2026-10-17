"""b_marker_style=corner_cones_v1 + b_marker_detect=cones_v1 / b_cone_accept=on_v1 (synthetic, no renderer, no sim)."""
import json, math
from pathlib import Path
import cv2
import numpy as np
import pytest
from harness import e2e_b_cones as C
from harness.active_camera import SEARCH
from harness.e2e_rgb_gate import ArrivalGate, boundary, lens_valid
from harness.zone_study_contract import ContractViolation
from sim.zone_arena import apply_b_marker_style, digest

W, H = 640, 480
LIME = (140, 242, 13)
MAP = Path(__file__).resolve().parents[1]/'maps/zones_e2e'
BASE = json.loads((MAP/'zone_wide_door_e2e_b80_v1.json').read_text())
STATIC = json.loads((MAP/'zone_wide_door_e2e_b80_cones_v1.json').read_text())
LAYOUT = C.layout_from_static(STATIC)


def b_pose(center, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.asarray(center)+LAYOUT['local']@np.array([[c, s], [-s, c]])


def render(center, yaw, *, drop=(), servo=SEARCH):
    img = np.full((H, W, 3), 120, np.uint8)
    for i, base in enumerate(b_pose(center, yaw)):
        if i in drop: continue
        ang = np.linspace(0, 2*np.pi, 24, endpoint=False)
        ring = np.column_stack([base[0]+.09*np.cos(ang), base[1]+.09*np.sin(ang), np.zeros(24)])
        pts = np.vstack([ring, [base[0], base[1], .30]])
        uv, ok = C.project_points(pts, servo)
        if ok.sum() < 20: continue
        cv2.fillConvexPoly(img, cv2.convexHull(np.rint(uv[ok]).astype(np.int32)), LIME)
    img[~lens_valid(W, H)] = 0
    return img


def test_map_option_default_off_and_hash():
    assert apply_b_marker_style(BASE, 'off') is BASE and 'landmarks' not in BASE
    built = apply_b_marker_style(BASE, 'corner_cones_v1')
    assert built['version'] == BASE['version']+1 and digest(built) != digest(BASE)
    assert {k: v for k, v in STATIC.items() if k != 'parent_map'} == {**built, 'map_id': STATIC['map_id']}
    assert STATIC['parent_map']['sha256'] == digest(BASE)
    with pytest.raises(ValueError): apply_b_marker_style(BASE, 'bad')
    # cones outside B, clear of the west entry (robot-width gap), inside the perimeter
    x0, x1, y0, y1 = BASE['bounds_m']
    for lm in STATIC['landmarks']:
        x, y = lm['position_m']
        assert x0 < x < x1-.1 and y0 < y < y1 and (abs(x-4.6) > .4 and abs(y+2.1) > .7)


def test_cone_hue_distinct():
    hsv = cv2.cvtColor(np.uint8([[LIME]]), cv2.COLOR_RGB2HSV)[0, 0]
    assert C.CFG['hsv_lo'][0] <= hsv[0] <= C.CFG['hsv_hi'][0]
    others = {'wall': (59, 71, 84), 'B floor': (25, 70, 215), 'A orange': (242, 115, 25), 'yellow cargo': (235, 199, 25),
              'green cargo': (38, 158, 51), 'cyan cargo': (51, 166, 179), 'C purple': (178, 51, 217)}
    for name, rgb in others.items():
        h, s, v = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_RGB2HSV)[0, 0]
        assert not (C.CFG['hsv_lo'][0] <= h <= C.CFG['hsv_hi'][0] and s >= C.CFG['hsv_lo'][1]), name


@pytest.mark.parametrize('center,yaw_deg', [((2.8, 0.), 0), ((3.1, .1), 8), ((3.0, -.1), -8)])
def test_pose_recovered_from_projection(center, yaw_deg):
    fit = C.detect_cones(render(np.array(center), math.radians(yaw_deg)), SEARCH, (0., 0., 0.), LAYOUT)
    assert fit is not None and fit['complete'] and fit['n_cones'] >= 3
    assert np.linalg.norm(np.array(fit['center_robot_m'])-center) < .08
    yaw_err = abs((fit['yaw_robot_rad']-math.radians(yaw_deg)+math.pi/2) % math.pi-math.pi/2)
    assert math.degrees(yaw_err) < 4


def test_three_cones_ok_two_ambiguous_none_rejected():
    c = np.array([2.8, 0.])
    assert C.detect_cones(render(c, 0., drop=(3,)), SEARCH, (0., 0., 0.), LAYOUT) is not None
    d = {}
    assert C.detect_cones(render(c, 0., drop=(2, 3)), SEARCH, (0., 0., 0.), LAYOUT, diagnostics=d) is None
    assert d['cone_fit_reason'] in ('two_cones_ambiguous', 'fewer_than_two_cones')
    assert C.detect_cones(np.full((H, W, 3), 120, np.uint8), SEARCH, (0., 0., 0.), LAYOUT) is None


def test_shape_and_residual_gates():
    img = np.full((H, W, 3), 120, np.uint8)
    cv2.rectangle(img, (300, 200), (420, 215), LIME, -1)  # wide lime strip: not a vertical cone
    d = {}
    assert C.find_cones(img, SEARCH, diagnostics=d) == [] and d['cone_rejects']
    pts = b_pose(np.array([2.8, 0.]), 0.)
    pts[0] += [.3, -.3]  # one cone displaced 0.4 m: no consistent 4-cone layout, 3-subset still fits
    fit, reason, info = C.fit_layout(pts, LAYOUT)
    assert fit is not None and fit['n_cones'] == 3
    pts[1] += [-.3, .3]
    assert C.fit_layout(pts, LAYOUT)[0] is None


def test_boundary_and_gate_toggle():
    img = render(np.array([2.8, 0.]), 0.)
    assert boundary(img, SEARCH, [0., 0., 0.], marker_detect='cones_v1') is None  # accept off: diagnostics only
    got = boundary(img, SEARCH, [0., 0., 0.], marker_detect='cones_v1', cone_accept='on_v1')
    assert got is not None and got['source'] == 'cones_v1' and got['complete']
    assert boundary(img, SEARCH, [0., 0., 0.], marker_detect='contrast_v2', cone_accept='on_v1') is None
    ArrivalGate('r1', marker_detect='cones_v1', cone_accept='on_v1')
    with pytest.raises(ContractViolation): ArrivalGate('r1', marker_detect='contrast_v2', cone_accept='on_v1')


def test_range_error_vs_pixel_noise():
    """Monte Carlo: base-pixel +-0.5 px noise -> ground-plane error by range (informational bound)."""
    rng = np.random.default_rng(0)
    from harness.active_camera import goal_camera
    from harness.floor_goal import floor_intersections
    origin, axes = goal_camera(SEARCH, 'camera_v3')
    out = {}
    for r in (1., 2., 3.):
        uv, ok = C.project_points(np.array([[r, 0., 0.]]), SEARCH)
        errs = []
        for _ in range(100):
            p, v = floor_intersections(C._rays(uv+rng.normal(0, .5, (1, 2)), W, H), origin, axes, max_range_m=6)
            if v[0]: errs.append(np.linalg.norm(p[0, :2]-[r, 0]))
        out[r] = float(np.median(errs))
    assert out[1.] < .06 and out[1.] < out[2.] < out[3.]
