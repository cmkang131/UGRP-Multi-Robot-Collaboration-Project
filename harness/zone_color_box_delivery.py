"""Explicit color search/clip adapter; the sealed cyan controller is unchanged."""
import base64
import math
import numpy as np

from harness import visual_arm as va
from harness.m1_color_delivery import ColorBoxDeliveryMixin, ColorSharedPoseDelivery
from harness.zone_own_deliver import (
    _DeliverController as LegacyDeliverController, NEAR_CLIP_AHEAD_M,
    NEAR_CLIP_MIN_PX, NEAR_CLIP_DARK_MAX, NEAR_CLIP_RIM_PX, NEAR_CLIP_LOWER_FRACTION,
)


def bottom_clipped_box_px(image_b64: str, kind: str, *, profile='legacy_cyan_v1') -> int:
    """Requested-kind pixels (explicit profile HSV) in the lower image that touch the fisheye image edge below them.

    The wrist fisheye leaves black corners/rim; a box too close to fit is cut by that rim, not by the
    rectangular image border that ``zone_color_boxes`` checks (fixture: smoke v1 s700 r3 frame 172).
    """
    import cv2

    from harness.zone_color_boxes import OWN_ZONE_CYAN_HSV
    from harness.m1_color_contract import validate_box_profile
    validate_box_profile(profile, kind, 'own_rgb_bay')
    try:
        frame = cv2.imdecode(np.frombuffer(base64.b64decode(image_b64, validate=True), np.uint8), cv2.IMREAD_COLOR)
    except (ValueError, TypeError):
        return 0
    if frame is None or frame.ndim != 3:
        return 0
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cyan = np.zeros(hsv.shape[:2], bool)
    for low, high in OWN_ZONE_CYAN_HSV:
        cyan |= cv2.inRange(hsv, np.asarray(low, np.uint8), np.asarray(high, np.uint8)) > 0
    if profile == 'm1_color_boxes_v1':
        from harness.m1_color_perception import color_mask
        cyan = color_mask(frame, kind) > 0
    outside = frame.max(axis=2) < NEAR_CLIP_DARK_MAX
    rim_below = np.zeros_like(outside)
    for k in range(1, NEAR_CLIP_RIM_PX + 1):
        rim_below[:-k] |= outside[k:]
    hit = cyan & rim_below
    hit[:int(frame.shape[0] * NEAR_CLIP_LOWER_FRACTION)] = False
    return int(np.count_nonzero(hit))


class ColorDeliverController(LegacyDeliverController, ColorSharedPoseDelivery):
    """Reuse guarded legs/slot/retreat logic; explicitly select color perception.

    LegacyDeliverController.__init__ delegates to ColorSharedPoseDelivery via
    this instance's MRO. No process-wide factory or import is replaced.
    """

    def _search_detect(self, obs, report):
        n = len(self.cyan)
        ColorBoxDeliveryMixin._search_detect(self, obs, report)
        # Order sheet: the item stands in this coarse pickup slot, so a target seen elsewhere is not it.
        self.cyan[n:] = [d for d in self.cyan[n:] if self._in_slot(d['map_xy'])]
        if len(self.cyan) == n and report.initialized:
            pan = math.radians((int(obs['actuator_state']['servo_pulses'].get('6', va.BASE_CENTER)) - va.BASE_CENTER)
                               / va.PULSE_PER_DEGREE)
            ahead = (report.x_m + NEAR_CLIP_AHEAD_M * math.cos(report.yaw_rad + pan),
                     report.y_m + NEAR_CLIP_AHEAD_M * math.sin(report.yaw_rad + pan))
            if self._in_slot(ahead):
                px = bottom_clipped_box_px(obs['image'], self.box_kind, profile=self.box_profile)
                if px >= NEAR_CLIP_MIN_PX:
                    self.near_clipped.append({'t': round(report.t_est, 3), 'frame_id': int(obs['frame_id']), 'px': px})
