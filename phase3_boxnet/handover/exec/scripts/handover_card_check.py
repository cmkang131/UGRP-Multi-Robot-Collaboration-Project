"""Build-time check of the two hand-over camera paths on trial 1's 12 px card."""
import copy
import math

import numpy as np

from harness.handover_policy import MagnifiedMarkers


MARKER_PX = 12


class ZoomDetections:
    """Observe the decoded top edges before MagnifiedMarkers maps them to native pixels."""

    def __init__(self, detector, marker_id):
        self.detector = detector
        self.marker_id = marker_id
        self.edges_px = []

    def detectMarkers(self, gray):
        corners, ids, rejected = self.detector.detectMarkers(gray)
        for quad, number in zip(corners, () if ids is None else ids.ravel()):
            if number == self.marker_id:
                a, b = quad.reshape(4, 2)[:2]
                self.edges_px.append(math.dist(a, b))
        return corners, ids, rejected


def check_chassis_poses(expected, native, magnified, metres_per_px, card_offset_m):
    # Pixel centres span 11 intervals. Half a pixel per endpoint allows one pixel
    # of rise and a horizontal span as short as 10 pixels for the nominally level edge.
    yaw_limit = math.atan2(1, MARKER_PX - 2)
    # One native pixel per centre coordinate, plus the chord swept by the rear mount.
    xy_limit = math.sqrt(2) * metres_per_px + 2 * abs(card_offset_m) * math.sin(yaw_limit / 2)
    print(f"r1 centre card (x_m, y_m, yaw_rad): expected={expected} native={native} "
          f"magnified={magnified} xy_tolerance_m={xy_limit:.9f} yaw_tolerance_rad={yaw_limit:.9f} "
          f"metres_per_pixel={metres_per_px:.10f}", flush=True)
    for label, first, second in (("native vs expected", native, expected),
                                 ("magnified vs expected", magnified, expected),
                                 ("native vs magnified", native, magnified)):
        if first is None or second is None:
            raise ValueError(f"{label}: missing r1 centre-card detection")
        xy_error = math.dist(first[:2], second[:2])
        yaw_error = abs(math.remainder(first[2] - second[2], math.tau))
        if not (xy_error <= xy_limit and yaw_error <= yaw_limit):
            raise ValueError(f"{label}: chassis error {xy_error:.9f} m, {yaw_error:.9f} rad")


def check_centre_card(overhead):
    """Call after loading overhead_v1 with the trial 1 map, as in the image."""
    import cv2

    native = overhead.OverheadReader()
    zoom = copy.copy(native)
    witness = ZoomDetections(native.detector, overhead.TOP_ID0)
    zoom.detector = MagnifiedMarkers(witness)

    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, overhead.DICTIONARY))
    marker = cv2.aruco.generateImageMarker(dictionary, overhead.TOP_ID0, MARKER_PX)
    gray = np.full((overhead.HEIGHT, overhead.WIDTH), 255, np.uint8)
    x0, y0 = overhead.WIDTH // 2 - MARKER_PX // 2, overhead.HEIGHT // 2 - MARKER_PX // 2
    gray[y0:y0 + MARKER_PX, x0:x0 + MARKER_PX] = marker
    pictures = {"top": gray}
    native_pose = native.read(pictures).get("r1")
    magnified_pose = zoom.read(pictures).get("r1")

    # The first and last printed pixel centres are x0 and x0+11 (likewise for y).
    half_span = (MARKER_PX - 1) / 2
    dx = x0 + half_span - overhead.WIDTH / 2
    dy = y0 + half_span - overhead.HEIGHT / 2
    scale = (overhead.HEIGHT_M - overhead.BASE_Z - overhead.CARD_AT[2]) / native.f
    # Trial 1's symmetric room has its single camera at arena (0, 0). An old
    # default-arena reader must not move the expected fixture along with itself.
    expected = (dx * scale - overhead.CARD_AT[0], -dy * scale, 0.)

    # A 24-sample marker spans 23 zoom pixels, with one native pixel (2 zoom
    # pixels) of edge-length uncertainty. A native-only passthrough must fail.
    zoom_span = 2 * MARKER_PX - 1
    print(f"r1 decoded top edges before remapping (zoom px)={witness.edges_px} "
          f"expected_span_px={zoom_span} tolerance_px=2", flush=True)
    check_chassis_poses(expected, native_pose, magnified_pose, scale, overhead.CARD_AT[0])
    if not any(abs(edge - zoom_span) <= 2 for edge in witness.edges_px):
        raise ValueError("missing r1 detection at 2x scale")
    return native_pose, magnified_pose
