"""b_marker_detect=partial_known_size_v1 + boundary_views=standoff_fullquad_v1 (synthetic, no renderer, no sim)."""
import math
import cv2
import numpy as np
import pytest
from harness import e2e_b_partial as P
from harness import e2e_b_standoff as S
from harness import e2e_boundary_views as V
from harness.active_camera import SEARCH
from harness.e2e_rgb_gate import lens_valid
from harness.zone_study_contract import ContractViolation

W, H = 640, 480
HALF = (.4, .7)
BLUE = (25, 70, 215)  # RGB, hue ~120 (> 109 wall/floor split)


def render(center, yaw, pose=(0., 0., 0.), half=HALF, servo=SEARCH):
    """Board of known size at (center, yaw) in the ROBOT frame, drawn through the real fisheye model, lens-clipped."""
    edge = np.vstack([P.rect_corners(center, yaw, half)[i]+(P.rect_corners(center, yaw, half)[(i+1) % 4]-P.rect_corners(center, yaw, half)[i])
                      * np.linspace(0, 1, 200, endpoint=False)[:, None] for i in range(4)])
    uv, ok = P._project_robot(edge, servo, W, H)
    img = np.full((H, W, 3), 120, np.uint8)
    if ok.sum() >= 3:
        mask = np.zeros((H, W), np.uint8); cv2.fillPoly(mask, [np.rint(uv[ok]).astype(np.int32).reshape(-1, 1, 2)], 1)
        img[mask.astype(bool)] = BLUE
    img[~lens_valid(W, H)] = 0
    return img


def run(img):
    return P.detect_partial(img, SEARCH, (0., 0., 0.))


@pytest.mark.parametrize('center,yaw_deg', [((.9, .45), 0), ((1.0, .5), 4), ((.95, -.5), -5)])
def test_partial_patch_pose_recovered_within_tolerance(center, yaw_deg):
    got = run(render(np.array(center), math.radians(yaw_deg)))
    assert len(got) == 1 and got[0]['complete'] is False and got[0]['estimated_from_partial'] is True
    assert np.linalg.norm(np.array(got[0]['center_robot_m'])-center) < .06
    yaw_err = abs((got[0]['yaw_robot_rad']-math.radians(yaw_deg)+math.pi/2) % math.pi-math.pi/2)
    assert math.degrees(yaw_err) < 4


def test_single_straight_edge_is_under_constrained_and_rejected():
    # A huge region (side >> board) shows one straight edge only: x, yaw of a 0.8x1.4 board are not pinned.
    img = render(np.array([2.0, 0.]), 0., half=(.9, 3.))
    diag = {}
    assert P.detect_partial(img, SEARCH, (0., 0., 0.), diagnostics=diag) == []
    assert all(p['reason'] != 'accepted' for p in diag['patches'])


def test_wrong_size_region_is_not_accepted_as_b():
    img = render(np.array([1.2, 0.]), 0., half=(.15, .2))  # a small blue patch, not a 0.8x1.4 board
    assert run(img) == []


def test_no_blue_no_estimate():
    assert run(np.full((H, W, 3), 120, np.uint8)) == []


def test_default_board_size_is_the_static_map_size():
    assert P.board_half_extents() == HALF


# ---- standoff_fullquad_v1 -------------------------------------------------------------------
def test_old_close_view_is_clipped_and_planned_view_has_all_four_corners():
    b = S.load_board()
    close = S.view_check([3.5, -2.1, 0.], b)  # 0.8 m from the board edge, facing it: the e2e11 viewpoint class
    assert close['ok'] is False and close['reason'] in ('outline_clipped', 'outline_off_image', 'outline_not_projectable'), close
    best, n, total = S.plan_standoffs(b, top=5)
    assert best and total > 0
    for v in best:
        chk = S.view_check(v['pose'], b)
        assert chk['ok'] and chk['corners_projected'] == 4 and chk['margin_px'] >= S.CFG['margin_px']
        uv = np.array(chk['corners_px'])
        assert lens_valid(W, H)[uv[:, 1].astype(int), uv[:, 0].astype(int)].all()
        assert S.static_costmap(b['map']).pose_clear(v['pose'])


def test_wall_between_robot_and_board_is_rejected():
    b = S.load_board()
    # pickup side of the divider (x=2.2), facing the board: wall hides the floor behind it
    assert S.view_check([1.4, -0.8, math.atan2(-2.1+.8, 4.6-1.4)], b)['reason'] == 'wall_occludes_board'


def test_standoff_option_names_and_choose_view_uses_fixed_heading():
    assert V.request({'source': 'own', 'kind': 'B', 'center_m': [4.6, -2.1]}, False, option=V.STANDOFF_OPTION) in (True, False)
    with pytest.raises(ValueError):
        V.request(None, False, option='nope')
    from harness.public_navigation.costmap import Costmap
    raw = np.zeros((80, 80), np.uint8); cm = Costmap(raw, (0., -4.), .1)
    plan = lambda costmap, pose, xy: [np.asarray(pose[:2]), np.asarray(xy)]
    view = V.choose_view(cm, [1., -1., 0.], [4.6, -2.1], plan, standoff=[(2.0, -1.0, 1.234)])
    assert view['heading'] == 1.234 and np.allclose(view['target'], [2., -1.])
    ring = V.choose_view(cm, [1., -1., 0.], [4.6, -2.1], plan)
    assert abs(ring['heading']-1.234) > 1e-3  # default rings still face the candidate


def test_only_one_edge_visible_is_under_constrained():
    diag = {}
    assert P.detect_partial(render(np.array([.9, 0.]), 0.), SEARCH, (0., 0., 0.), diagnostics=diag) == []
    assert diag['patches'][0]['reason'] == 'under_constrained'
