"""b_marker_detect=contrast_v2: fisheye-aware B quad fit (synthetic, no renderer)."""
import cv2
import numpy as np
import pytest
from harness import e2e_b_quad as q
from harness import e2e_rgb_gate as g
from harness.active_camera import SEARCH
from harness.zone_study_contract import ContractViolation
from tests.test_e2e_b_marker_detect import scene, pinhole  # noqa: F401  (autouse fixture)

W, H = 640, 480


def lens():
    return g.lens_valid(W, H)


def distorted_contour(corners_norm):
    """Straight floor edges in normalised coordinates, bent by the real fisheye model."""
    k = q._camera(W, H)[0]
    pts = []
    for a, b in zip(corners_norm, np.roll(corners_norm, -1, axis=0)):
        pts += [a+(b-a)*t for t in np.linspace(0, 1, 60, endpoint=False)]
    px = q.distort(np.asarray(pts)*[k[0, 0], k[1, 1]]+[k[0, 2], k[1, 2]], W, H)
    return np.rint(px).astype(np.int32).reshape(-1, 1, 2)


BENT = np.array([[-.33, -.17], [.33, -.17], [.33, .17], [-.33, .17]])


def test_fisheye_bent_edges_fit_four_corners_at_true_positions():
    contour = distorted_contour(BENT)
    assert lens()[contour[:, 0, 1], contour[:, 0, 0]].all()
    corners, reason, stats = q.fit_quad(contour, lens())
    assert reason == 'quad' and corners.shape == (4, 2) and stats['fit_area_error'] <= .1
    k = q._camera(W, H)[0]
    truth = np.rint(q.distort(BENT*[k[0, 0], k[1, 1]]+[k[0, 2], k[1, 2]], W, H))
    assert max(np.min(np.linalg.norm(corners-t, axis=1)) for t in truth) <= 3


def test_clipped_or_concave_regions_are_not_promoted():
    contour = distorted_contour(BENT*[1.8, 1.8])           # reaches the lens circle / image border
    assert q.fit_quad(contour, lens())[1] in ('image_clipped', 'lens_clipped')
    bite = distorted_contour(BENT).copy()
    cv2.fillPoly(img := np.zeros((H, W), np.uint8), [bite], 255)
    cv2.rectangle(img, (int(bite[:, 0, 0].mean())-70, int(bite[:, 0, 1].min())), (int(bite[:, 0, 0].mean())+70, int(bite[:, 0, 1].min())+100), 0, -1)
    contour = max(cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea)
    assert q.fit_quad(contour, lens())[1] == 'low_solidity'


def test_wall_hue_is_not_floor_blue_and_floor_blue_is():
    hsv = np.zeros((10, 10, 3), np.uint8)
    hsv[:, :5] = (105, 76, 118)   # measured wall pixels (hue 105)
    hsv[:, 5:] = (112, 120, 170)  # measured B floor pixels
    mask = q.floor_blue_mask(hsv, np.zeros((10, 10), bool))
    assert not mask[:, :5].any() and mask[:, 5:].all()


def test_floor_shape_sanity_rejects_slivers_and_huge_regions():
    assert q.floor_shape_ok([[0, 0], [1, 0], [1, .6], [0, .6]])[0]
    assert not q.floor_shape_ok([[0, 0], [3, 0], [3, .1], [0, .1]])[0]
    assert not q.floor_shape_ok([[0, 0], [9, 0], [9, 9], [0, 9]])[0]


def test_v2_is_an_explicit_option_and_off_is_unchanged():
    image = scene()
    assert g.boundary(image, SEARCH, [0, 0, 0]) is None
    with pytest.raises(ContractViolation):
        g.white_markers(image, cv2.cvtColor(image, cv2.COLOR_RGB2HSV), np.ones(image.shape[:2], bool), region_area_px2=1., option='contrast_v3')
    assert 'contrast_v2' in g.MARKER_OPTIONS
    g.ArrivalGate('r1', marker_detect='contrast_v2')
