"""Pure XML/profile tests. No MuJoCo compile, step, renderer or shared lock."""
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from sim.masterpi_camera_profile import CAMERA_LOCAL_POS_M, CAMERA_LOCAL_QUAT_WXYZ
from sim.masterpi_camera_review_v1 import (
    POSITION_M, PROFILE_ID, QUAT_WXYZ, optical_tool_pitch_deg, quat_matrix, record, transform_xml,
)


def fixture_xml():
    return f'''<mujoco><worldbody><body name="r3__gripper">
      <camera name="r3__robot_cam" pos="{' '.join(map(str, CAMERA_LOCAL_POS_M))}"
        quat="{' '.join(map(str, CAMERA_LOCAL_QUAT_WXYZ))}" focalpixel="619.519 622.165" resolution="640 480"/>
      <geom name="r3__v3_camera_lens" fromto=".05 0 .011 .067 0 .0136" size=".007" group="5" mass="0" contype="0" conaffinity="0"/>
      <geom name="r3__left_finger" pos=".08685 0 0" size=".00715 .0045 .0035" contype="2" conaffinity="3"/>
      <camera name="observer" pos="1 2 3" fovy="45"/>
    </body></worldbody><option timestep=".00025"/></mujoco>'''


def test_drawing_axes_are_right_handed_and_face_along_tool():
    r = quat_matrix(QUAT_WXYZ)
    np.testing.assert_allclose(-r[:, 2], [1, 0, 0])
    np.testing.assert_allclose(r[:, 0], [0, -1, 0])
    assert np.linalg.det(r) == pytest.approx(1)
    assert optical_tool_pitch_deg(CAMERA_LOCAL_QUAT_WXYZ) == pytest.approx(7.46, abs=.01)


def test_drawing_pixel_derivation_is_not_sim_fitted():
    assert POSITION_M[0] == pytest.approx(.052982, abs=.000001)
    assert POSITION_M[2] == pytest.approx(.028153, abs=.000001)
    assert record()['runtime_admitted'] is False


def test_only_explicit_camera_and_massless_visuals_change():
    original = fixture_xml()
    before = ET.fromstring(original)
    after = ET.fromstring(transform_xml(original, profile_id=PROFILE_ID))
    for a, b in zip(before.iter(), after.iter()):
        if a.get('name') == 'r3__robot_cam':
            assert {k: v for k, v in a.attrib.items() if k not in ('pos', 'quat')} == {
                k: v for k, v in b.attrib.items() if k not in ('pos', 'quat')}
        elif a.get('name') == 'r3__v3_camera_lens':
            assert a.get('fromto') != b.get('fromto')
        else:
            assert a.attrib == b.attrib
    assert original == fixture_xml()


@pytest.mark.parametrize('bad', ['wrong_parent', 'colliding_housing', 'different_mount', 'no_camera'])
def test_unexpected_baselines_are_refused(bad):
    xml = fixture_xml()
    if bad == 'wrong_parent':
        xml = xml.replace('r3__gripper', 'r3__robot')
    elif bad == 'colliding_housing':
        xml = xml.replace('mass="0"', 'mass="0.01"')
    elif bad == 'different_mount':
        xml = xml.replace('0.067 0.0 0.0136', '0.06 0.0 0.02')
    else:
        xml = xml.replace('r3__robot_cam', 'r3__nav_cam')
    with pytest.raises(ValueError):
        transform_xml(xml, profile_id=PROFILE_ID)


def test_unknown_profile_is_refused():
    with pytest.raises(ValueError):
        transform_xml(fixture_xml(), profile_id='default')


def test_carry_selection_excludes_transition_and_lowering(tmp_path):
    import json
    from harness.zone_pair_highpose import HIGH
    from scripts.review_masterpi_camera import carry_frames
    (tmp_path/'robots/r3').mkdir(parents=True)
    (tmp_path/'student_record.json').write_text(json.dumps({'events': [
        {'event': 'state', 't': 1., 'state': 'lift'},
        {'event': 'state', 't': 2., 'state': 'carry'},
        {'event': 'state', 't': 3., 'state': 'lower'}]}))
    frames = [{'sim_time': t, 'commanded_servo': {str(k): v for k, v in HIGH.items()}}
              for t in (1.9, 2., 2.5, 3.)]
    frames[2]['commanded_servo']['3'] = 500
    (tmp_path/'robots/r3/frames.jsonl').write_text('\n'.join(map(json.dumps, frames)))
    assert [f['sim_time'] for f in carry_frames(tmp_path)] == [2.]


def test_cyan_mask_uses_full_frame_and_valid_lens_denominators():
    from scripts.review_masterpi_camera import cyan_metrics
    black = np.zeros((480, 640, 3), dtype=np.uint8)
    a = cyan_metrics(black)
    assert a['full_fraction'] == a['valid_fraction'] == 0
    cyan = black.copy()
    cyan[:] = [255, 255, 0]  # BGR cyan
    b = cyan_metrics(cyan)
    assert b['full_fraction'] == b['valid_fraction'] == 1
    assert 0 < b['valid_pixels'] < b['full_pixels'] == 640*480
