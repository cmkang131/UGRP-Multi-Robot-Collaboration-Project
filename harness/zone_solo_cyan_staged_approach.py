"""S2 staging/final-approach separation; own RGB reactive STOP, no peer pose.

Nav2 stop-model semantics on an image-plane observation source. A monocular
image does not provide obstacle range: the stop zone is conservatively the
whole visible image, not an invented metric distance. Orange appearance is the
unchanged PR398/v48 peer candidate, not a ground-truth identity classifier.
"""
import copy
import math
import cv2
import numpy as np
from harness.zone_solo_cyan_side_scan import APPEARANCE
from harness.zone_solo_cyan_visibility import pixel_rays, robot_boxes, shadow_depths

OPTION = 'staging_rgb_monitor_v1'
FINAL_STATES = frozenset(('align', 'real_pregrasp', 'hover', 'blind_descent',
                         'grasp', 'lift', 'relook_pickup', 'lower', 'released'))
PARAMS = dict(source_timeout_s=2., min_points=4, frame_interval_s=.25,
              stop_zone='entire undistorted image outside command-geometry self mask',
              unknown_is_obstacle=False, appearance=APPEARANCE)


def moving(a):
    return a['kind'] in ('drive', 'mecanum') and any(a.get(k, 0) for k in ('forward', 'left', 'turn'))


def observed_peer_pixels(rgb, camera, servo, cache):
    from harness import vision_loc_protocol as vp
    bgr = vp.load_vis3()[0].mp.undistort(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, tuple(APPEARANCE['hsv_lower']), tuple(APPEARANCE['hsv_upper']))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8)) > 0
    key = (tuple(sorted(servo.items())), camera.origin.tobytes(), camera._rot.tobytes())
    if key not in cache:
        rays = pixel_rays(camera, np.arange(640)[None, :], np.arange(480)[:, None])
        cache[key] = np.minimum.reduce(list(shadow_depths(camera.origin, rays, robot_boxes(servo, camera)).values()))
    raw = int(mask.sum())
    mask &= ~np.isfinite(cache[key])
    return dict(points=int(mask.sum()), raw_orange_pixels=raw,
                self_masked_pixels=raw-int(mask.sum()))


class Monitor:
    def __init__(self):
        self.last_t = -math.inf
        self.last = None
        self.cache = {}
        self.audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS),
                          final_states=sorted(FINAL_STATES), frames=[], checks=[],
                          gt_inputs=False, peer_messages=False, passed=0, stopped=0,
                          uncertified_navigation_issued=0)

    def observe(self, now, rgb, camera, servo, image_sha):
        if now < self.last_t + PARAMS['frame_interval_s'] - 1e-8:
            return
        if camera is None:
            return  # Invalid source is distinct from a fresh empty observation.
        row = dict(t=now, image_sha256=image_sha,
                   **observed_peer_pixels(rgb, camera, servo, self.cache))
        self.last_t, self.last = now, row
        self.audit['frames'].append(row)

    def assess(self, now):
        valid = self.last is not None and 0 <= now-self.last_t <= PARAMS['source_timeout_s']
        points = self.last['points'] if valid else 0
        stop = not valid or points >= PARAMS['min_points']
        return dict(t=now, stop=stop, source_valid=valid, observed_points=points,
                    reason='RGB_SOURCE_TIMEOUT' if not valid else
                    ('OBSERVED_PEER_APPEARANCE' if stop else 'NO_OBSERVED_PEER'),
                    image_sha256=self.last['image_sha256'] if valid else None,
                    free_space_claim=False)
