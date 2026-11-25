"""The image's centre-card gate, with recorded geometry and an optional real ArUco run."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "exec")]
from handover import layout
from harness.handover_policy import MagnifiedMarkers
from scripts.handover_card_check import check_centre_card, check_chassis_poses


EXPECTED = (.03851640625, .00248359375, 0.)
METRES_PER_PX = .0049671875
FIX2_MAGNIFIED = (.039101760684286425, .00015584297930056556, -.04164257909858842)


def raster_cv():
    # ID 40's payload from trial 1's printed card, with its black border and 2 px per module.
    payload = np.uint8([[0, 0, 0, 1], [0, 1, 1, 1], [0, 0, 0, 1], [1, 0, 0, 0]])
    marker = np.pad(255 * payload, 1).repeat(2, axis=0).repeat(2, axis=1)

    def square_corners(gray):
        # Measure the square in each actual input raster independently of the crop transform.
        y, x = np.nonzero(gray < 128)
        if not len(x):
            return [], None, ()
        left, right, top, bottom = x.min(), x.max(), y.min(), y.max()
        quad = np.float32([[(left, top), (right, top), (right, bottom), (left, bottom)]])
        return [quad], np.int32([[40]]), ()

    cv = Mock()
    cv.aruco.DICT_4X4_50 = 0
    cv.aruco.generateImageMarker.return_value = marker
    cv.aruco.ArucoDetector.return_value.detectMarkers.side_effect = square_corners
    return cv


class CameraFixture(unittest.TestCase):
    def setUp(self):
        # Other suites import overhead_v1 with the default arena. Load the reader afresh
        # with the same map-at-import setup as check_image and the trial driver.
        folder = self.enterContext(tempfile.TemporaryDirectory())
        scene = Path(folder) / "map.json"
        scene.write_text(json.dumps(layout.map_config(layout.trials()[1])))
        spec = importlib.util.spec_from_file_location("trial1_overhead", ROOT / "exec/harness/overhead_v1.py")
        self.overhead = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {"UGRP_MAP_SCENE": str(scene)}):
            spec.loader.exec_module(self.overhead)

    def test_same_raster_and_calibrated_chassis_on_both_paths(self):
        cv = raster_cv()
        with patch.dict(sys.modules, {"cv2": cv}), redirect_stdout(io.StringIO()):
            native, zoom = check_centre_card(self.overhead)
        self.assertEqual(self.overhead.CAMERAS, (("top", (0., 0.)),))
        self.assertEqual((self.overhead.DICTIONARY, self.overhead.TOP_ID0, self.overhead.N_TOP),
                         ("DICT_4X4_50", 40, 2))
        cv.aruco.generateImageMarker.assert_called_once_with(cv.aruco.getPredefinedDictionary.return_value, 40, 12)
        inputs = cv.aruco.ArucoDetector.return_value.detectMarkers.call_args_list
        gray = inputs[0].args[0]
        self.assertEqual(gray.shape, (960, 1280))
        # Independent full-frame hash from the archived printed card at the FIX2 coordinates.
        self.assertEqual(hashlib.sha256(gray.tobytes()).hexdigest(),
                         "7b935a69ed4fe3d2b4368ac26c28d35f3998318471390624a4ca0f135b89249f")
        np.testing.assert_allclose(native, EXPECTED, rtol=0, atol=1e-12)
        np.testing.assert_allclose(zoom, native, rtol=0, atol=1e-12)

    def test_default_arena_camera_cannot_validate_the_trial1_fixture(self):
        with (patch.object(self.overhead, "CAMERAS", (("top", (2.175, -.85)),)),
              patch.dict(sys.modules, {"cv2": raster_cv()}), redirect_stdout(io.StringIO()),
              self.assertRaisesRegex(ValueError, "native vs expected")):
            check_centre_card(self.overhead)

    @unittest.skipUnless(importlib.util.find_spec("cv2"), "OpenCV unavailable locally; mandatory in-image check")
    def test_image_fixture_with_installed_aruco(self):
        import cv2
        self.addCleanup(cv2.setNumThreads, cv2.getNumThreads())
        cv2.setNumThreads(1)
        check_centre_card(self.overhead)

    def test_native_success_cannot_mask_a_magnification_bypass(self):
        # Both paths would report the ideal pose if the magnifier simply passed its input through.
        def passthrough(wrapper, image):
            return wrapper.detector.detectMarkers(image)

        with (patch.dict(sys.modules, {"cv2": raster_cv()}),
              patch.object(MagnifiedMarkers, "detectMarkers", passthrough),
              redirect_stdout(io.StringIO()) as log, self.assertRaisesRegex(ValueError, "at 2x scale")):
            check_centre_card(self.overhead)
        self.assertIn("zoom px)=[11.0]", log.getvalue())


class ChassisTolerance(unittest.TestCase):
    def test_reported_fix2_pose_is_within_the_pixel_budget(self):
        self.assertGreater(abs(FIX2_MAGNIFIED[2]), .02)
        with redirect_stdout(io.StringIO()) as log:
            check_chassis_poses(EXPECTED, EXPECTED, FIX2_MAGNIFIED, METRES_PER_PX, -.041)
        self.assertIn("xy_tolerance_m=0.011109387 yaw_tolerance_rad=0.099668652", log.getvalue())

    def test_missing_wrong_and_disagreeing_poses_fail_with_diagnostics(self):
        x, y, _ = EXPECTED
        card_only = (x - .041, y, 0.)
        for label, native, zoom in (
            ("native vs expected", None, EXPECTED),
            ("magnified vs expected", EXPECTED, None),
            ("native vs expected", card_only, card_only),
            ("magnified vs expected", EXPECTED, (x + 3 * METRES_PER_PX, y, 0.)),
            ("magnified vs expected", EXPECTED, (x, y, math.pi / 2)),
            ("native vs magnified", (x, y, -.06), (x, y, .06)),
            ("native vs magnified", (x - .008, y, 0.), (x + .008, y, 0.)),
        ):
            with (self.subTest(native=native, zoom=zoom), redirect_stdout(io.StringIO()) as log,
                  self.assertRaisesRegex(ValueError, label)):
                check_chassis_poses(EXPECTED, native, zoom, METRES_PER_PX, -.041)
            self.assertIn(f"native={native} magnified={zoom}", log.getvalue())
            self.assertIn("yaw_tolerance_rad=", log.getvalue())
