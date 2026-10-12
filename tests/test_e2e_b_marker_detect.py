"""B white-mark detection toggle: synthetic own-RGB fixtures, no renderer.

Colours are the values measured on retrieved e2e10 r1 frames: 30 %-alpha blue B
over a two-tone checker floor, and 35 %-alpha white slot marks on top.
"""
import cv2
import numpy as np
import pytest
from harness import e2e_rgb_gate as g
from harness.active_camera import SEARCH
from harness.zone_study_contract import ContractViolation

LIGHT, DARK, FLOOR = (88, 110, 168), (63, 85, 145), (120, 118, 115)
WHITE = np.array([212, 220, 240])  # shaded white implied by the measured blends


@pytest.fixture(autouse=True)
def pinhole(monkeypatch):
    # Same fixed calibration stubs as test_e2e_goal_route: extraction is real.
    monkeypatch.setattr(g, 'goal_camera', lambda *a: (np.array([0., 0., 1.]), np.diag([1., -1., -1.])))
    monkeypatch.setattr(g, 'project_envelopes', lambda *a: np.zeros((240, 320), bool))


def scene(marks='translucent', gain=1.):
    image = np.zeros((240, 320, 3), np.uint8); image[:] = FLOOR
    cv2.rectangle(image, (60, 60), (150, 200), LIGHT, -1)   # floor tone reaches the B edge
    cv2.rectangle(image, (151, 60), (260, 200), DARK, -1)
    for x in (100, 180, 225):
        under = np.array(LIGHT if x < 150 else DARK)
        colour = (255, 255, 255) if marks == 'opaque' else tuple(int(v) for v in .35*WHITE+.65*under)
        if marks != 'none': cv2.rectangle(image, (x-7, 125), (x+7, 135), colour, -1)
    return np.clip(image.astype(np.float32)*gain, 0, 255).astype(np.uint8)


def test_translucent_marks_fail_fixed_thresholds_and_pass_contrast():
    image = scene()
    diag = {}
    assert g.boundary(image, SEARCH, [0, 0, 0], diagnostics=diag) is None
    assert [c.get('white_islands') for c in diag['contours'] if 'white_islands' in c] == [0]
    found = g.boundary(image, SEARCH, [0, 0, 0], marker_detect=g.MARKER_OPTION)
    assert found and found['white_markers'] == 3 and len(found['polygon']) == 4


@pytest.mark.parametrize('gain', [.7, 1.3])
def test_contrast_rule_survives_global_exposure_gain(gain):
    found = g.boundary(scene(gain=gain), SEARCH, [0, 0, 0], marker_detect=g.MARKER_OPTION)
    assert found and found['white_markers'] == 3


def test_two_tone_floor_without_marks_is_not_a_boundary():
    diag = {}
    assert g.boundary(scene('none'), SEARCH, [0, 0, 0], diagnostics=diag, marker_detect=g.MARKER_OPTION) is None
    assert [c['white_islands'] for c in diag['contours'] if 'white_islands' in c] == [0]


def test_opaque_tape_marks_pass_both_and_off_is_unchanged():
    image = scene('opaque')
    assert g.boundary(image, SEARCH, [0, 0, 0])['white_markers'] == 3
    assert g.boundary(image, SEARCH, [0, 0, 0], marker_detect=g.MARKER_OPTION)['white_markers'] == 3
    for img in (image, scene()):
        assert g.boundary(img, SEARCH, [0, 0, 0]) == g.boundary(img, SEARCH, [0, 0, 0], marker_detect='off')


def test_unknown_marker_option_is_refused():
    with pytest.raises(ContractViolation): g.ArrivalGate('r1', option=g.OPTION, marker_detect='otsu')
    with pytest.raises(ContractViolation): g.boundary(scene(), SEARCH, [0, 0, 0], marker_detect='otsu')
    assert g.ArrivalGate('r1', option=g.OPTION).marker_detect == 'off'
    from harness.e2e_live_mapping import make_goal
    with pytest.raises(ValueError, match='UNKNOWN_B_MARKER_DETECT'):
        make_goal('r1', 61001, None, b_marker_detect='otsu')
