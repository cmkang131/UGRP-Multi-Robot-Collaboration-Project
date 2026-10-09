"""Optics and separation contracts only; no simulation/render or success gate."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from sim import masterpi_camera_review_v1 as v1
from sim import masterpi_camera_review_v3 as v3
from scripts.review_masterpi_camera_v2 import plan as previous_plan
from scripts.review_masterpi_camera_v3 import plan, VARIANTS, camera


def test_pitch_convention_and_provenance_do_not_claim_measured_calibration():
    assert v3.POSITION_M == v1.POSITION_M
    assert v1.optical_tool_pitch_deg(v3.QUAT_WXYZ) == pytest.approx(10.)
    assert np.linalg.det(v1.quat_matrix(v3.QUAT_WXYZ)) == pytest.approx(1.)
    r = v3.record()
    assert not r['runtime_admitted'] and not r['default_changed']
    assert r['source_label'] == '사용자 실물 관찰 기반 목표'
    assert not r['setdown_relook_candidate']['implemented']
    with pytest.raises(ValueError):
        v3.transform_xml('<mujoco/>', profile_id='default')


def test_xml_only_camera_and_massless_visuals_change():
    pytest.importorskip('mujoco')
    from sim.masterpi_model_v3 import build_v3_xml
    before = ET.fromstring(build_v3_xml())
    after = ET.fromstring(v3.transform_xml(ET.tostring(before, encoding='unicode'), profile_id=v3.PROFILE_ID))
    assert len(list(before.iter())) == len(list(after.iter()))
    for a, b in zip(before.iter(), after.iter()):
        assert a.tag == b.tag
        if a.get('name') == 'robot_cam':
            np.testing.assert_allclose(np.fromstring(b.get('quat'), sep=' '), v3.QUAT_WXYZ)
        elif a.get('name', '').startswith('v3_camera_'):
            assert a.get('mass') == b.get('mass') == '0'
            assert a.get('contype') == b.get('contype') == '0'
        else:
            assert a.attrib == b.attrib


def test_fixed_contact_commands_unchanged_and_candidate_uses_archived_rays():
    from sim import masterpi_camera_profile as old
    from types import SimpleNamespace
    model = SimpleNamespace(camera=lambda _: SimpleNamespace(id=0),
        cam_pos=np.zeros((1,3)), cam_quat=np.zeros((1,4)),
        cam_resolution=np.zeros((1,2)), cam_sensorsize=np.zeros((1,2)),
        cam_intrinsic=np.zeros((1,4)))
    assert plan() == previous_plan()
    assert VARIANTS == ('baseline', 'drawing_v1', 'sdk_sample_v2', 'user_v3')
    camera(model, 'user_v3')
    np.testing.assert_allclose(model.cam_pos[0], v3.POSITION_M)
    np.testing.assert_allclose(model.cam_quat[0], v3.QUAT_WXYZ)
    np.testing.assert_allclose(model.cam_intrinsic[0], old.mujoco_pixel_intrinsic(640,480))


def test_real_area_counts_pixels_not_bounding_box_or_success():
    import cv2
    path = Path(__file__).resolve().parents[1]/'experiments/2026-10-06-robot-camera-review/audit_real_archive.py'
    spec = importlib.util.spec_from_file_location('archive_camera_audit', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    hsv = np.zeros((480,640,3), np.uint8)
    hsv[400:,200:400] = [108,160,145]  # observed blue interior hue
    hsv[350:,400:600] = [83,255,75]   # adjacent green must not count as blue
    result = module.color_area(cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR), 'blue')
    assert result['bottom_component_pixels'] == 16000
    assert result['bottom_component_fraction'] == pytest.approx(16000/(640*480))
    assert 'success' not in result
