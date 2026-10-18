"""Pure-RGB zone/arrival detector tests (no simulator, no engine)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        'own_rgb_zone_visdet', ROOT / 'harness' / 'own_rgb_zone_visdet.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_camera(m):
    w, h, fx, fy = 320, 240, 240.0, 240.0
    cx, cy = 160.0, 120.0
    # camera frame (x right, y down, z forward) -> robot frame (x fwd, y left, z up)
    rot = np.array([[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]])
    return m.CameraModel(kind='pinhole', width=w, height=h, fx=fx, fy=fy,
                         cx=cx, cy=cy, rotation=rot,
                         translation_m=(0.0, 0.0, 0.20))


def paint_floor_rect(m, camera, rect, hue=112, sat=200, val=200):
    """Render a blue floor rectangle (robot frame x0,x1,y0,y1) into an RGB frame."""
    rays = camera.ray_grid()
    origin = camera.origin()
    h, w = camera.height, camera.width
    hsv = np.zeros((h, w, 3), np.uint8)
    hsv[..., 0] = 0
    hsv[..., 1] = 0
    hsv[..., 2] = 170
    scale = -origin[2] / rays[..., 2]
    x = origin[0] + scale * rays[..., 0]
    y = origin[1] + scale * rays[..., 1]
    inside = ((scale > 0) & (x >= rect[0]) & (x <= rect[1])
              & (y >= rect[2]) & (y <= rect[3]))
    hsv[inside, 0] = hue
    hsv[inside, 1] = sat
    hsv[inside, 2] = val
    bgr = importlib.import_module('cv2').cvtColor(hsv, importlib.import_module('cv2').COLOR_HSV2BGR)
    rgb = importlib.import_module('cv2').cvtColor(bgr, importlib.import_module('cv2').COLOR_BGR2RGB)
    return rgb, inside


def test_off_by_default_and_no_engine_imports():
    m = load_module()
    camera = make_camera(m)
    rgb, _ = paint_floor_rect(m, camera, (1.2, 1.8, -0.3, 0.3))
    det = m.detect(rgb, camera)
    assert det.status == 'off'
    reporter = m.ZoneArrivalReporter(camera)
    out = reporter.observe(rgb)
    assert out['status'] == 'off' and out['destination_arrived'] is False
    import ast
    import sys
    source = (ROOT / 'harness' / 'own_rgb_zone_visdet.py').read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
    assert not imported & {'mujoco', 'mujoco_warp', 'warp', 'sim', 'harness'}, imported
    assert 'mujoco' not in sys.modules
    assert 'warp' not in sys.modules


def test_far_zone_detected_with_metric_evidence():
    m = load_module()
    camera = make_camera(m)
    rgb, _ = paint_floor_rect(m, camera, (1.2, 1.8, -0.3, 0.3))
    det = m.detect(rgb, camera, enabled=True)
    assert det.status == 'observed', det.reason
    assert det.pixels >= 600
    assert 1.1 <= det.nearest_range_m <= 1.35
    assert 0.45 <= det.extent_m <= 0.85
    assert det.paint_reaches_bottom_band is False
    assert det.arrival_ready is False
    assert det.bottom_norm < 0.95


def test_near_zone_marks_arrival_evidence():
    m = load_module()
    camera = make_camera(m)
    rgb, inside = paint_floor_rect(m, camera, (0.40, 0.85, -0.3, 0.3))
    assert inside.sum() >= 600
    det = m.detect(rgb, camera, enabled=True)
    assert det.status == 'observed', det.reason
    assert det.bottom_norm >= 0.98, det.bottom_norm
    assert det.paint_reaches_bottom_band is True
    assert det.arrival_ready is True


def test_exclude_mask_hides_held_pixels():
    m = load_module()
    camera = make_camera(m)
    rgb, inside = paint_floor_rect(m, camera, (1.2, 1.8, -0.3, 0.3))
    det = m.detect(rgb, camera, enabled=True, exclude_mask=inside)
    assert det.status == 'unknown'
    assert det.reason == 'destination_colour_absent'


def test_reporter_debounces_arrival():
    m = load_module()
    camera = make_camera(m)
    rgb_near, _ = paint_floor_rect(m, camera, (0.40, 0.85, -0.3, 0.3))
    rgb_far, _ = paint_floor_rect(m, camera, (1.2, 1.8, -0.3, 0.3))
    rep = m.ZoneArrivalReporter(camera, enabled=True, confirm_frames=3,
                                lost_frames=2)
    for _ in range(2):
        out = rep.observe(rgb_near)
        assert out['destination_arrived'] is False
    out = rep.observe(rgb_near)
    assert out['destination_arrived'] is True
    assert out['handoff_ready'] is False  # owner adapter decides handoff
    for _ in range(2):
        out = rep.observe(rgb_far)
    assert out['destination_arrived'] is False


def test_large_floor_component_rejected_by_extent_cap():
    m = load_module()
    camera = make_camera(m)
    # A blue region spanning several metres of floor (like the GPU-rendered
    # floor appearance) must not be accepted as the authored zone patch.
    rgb, _ = paint_floor_rect(m, camera, (0.40, 6.0, -3.0, 3.0))
    det = m.detect(rgb, camera, enabled=True)
    assert det.status == 'unknown'
    assert det.reason in ('destination_extent_not_zone', 'destination_too_far')


def test_gpu_profile_separates_dark_zone_from_bright_floor_blue():
    m = load_module()
    camera = make_camera(m)
    # Calibrated GPU zone-B paint is darker than the bright pickup-room floor
    # (see zone-appearance-calib.json: zone V~77-86, pickup floor V~135).
    zone_rgb, _ = paint_floor_rect(m, camera, (1.2, 1.8, -0.3, 0.3),
                                   hue=112, sat=190, val=85)
    floor_rgb, _ = paint_floor_rect(m, camera, (1.2, 1.8, -0.3, 0.3),
                                    hue=110, sat=205, val=135)
    zone = m.detect(zone_rgb, camera, enabled=True,
                    appearance='gpu_calib_v1')
    floor_cpu = m.detect(floor_rgb, camera, enabled=True,
                         appearance='cpu_v1')
    floor_gpu = m.detect(floor_rgb, camera, enabled=True,
                         appearance='gpu_calib_v1')
    assert zone.status == 'observed', zone.reason
    assert floor_cpu.status == 'observed'      # CPU profile accepts it
    assert floor_gpu.status == 'unknown'       # GPU profile rejects it
    assert floor_gpu.reason in ('destination_colour_absent',
                                'destination_component_small')


def test_unknown_appearance_profile_is_rejected():
    m = load_module()
    camera = make_camera(m)
    rgb, _ = paint_floor_rect(m, camera, (1.2, 1.8, -0.3, 0.3))
    try:
        m.detect(rgb, camera, enabled=True, appearance='nope')
    except ValueError as exc:
        assert 'UNKNOWN_APPEARANCE_PROFILE' in str(exc)
    else:
        raise AssertionError('unknown profile must raise')
