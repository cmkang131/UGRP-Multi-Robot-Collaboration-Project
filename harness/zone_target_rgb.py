"""Own RGB -> explicit box candidates and per-target skill attention images.

Only the wrist JPEG and OWN ISSUED arm pulses enter perception. Ground fits
are conditional 34 x 40 x 32 mm cuboid hypotheses, never simulator positions.
No crop/rescale or camera change: the skill view retains pixel coordinates,
masks other components, and normalizes the selected cube's hue to cyan for
the frozen v9 manipulation skill. Raw JPEGs and both hashes remain separate.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import math
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from harness import m1_owncam_contract
from harness import zone_color_boxes as boxes
from harness import zone_own_perception_v3_1 as perception
from harness.zone_item_recovery import _overlap
from harness.zone_study_contract import ContractViolation
from harness.zone_target_identity import BOX_KINDS, BOX_SIZE, CueDetection, CueFrame

PROFILE = 'target_cube_attention_v1'


def attention_image(bgr, contour):
    """Keep only this already selected raw-image component, with original S/V."""
    mask = np.zeros(bgr.shape[:2], np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, cv2.FILLED)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hsv[..., 0][mask > 0] = 92
    selected = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    selected[mask == 0] = 0
    ok, data = cv2.imencode('.png', selected)
    if not ok:
        raise ValueError('target attention encoding failed')
    return data.tobytes()


@dataclass(frozen=True)
class TargetView:
    job_id: str
    local_token: str
    detection_id: str
    raw_sha256: str
    observation: dict


class OwnRGBRecognizer:
    def __init__(self, robot_id, static_map):
        if static_map.get('robot_model', 'masterpi_v2') != 'masterpi_v2':
            raise ContractViolation('FINAL_V3_TARGET_RGB_PROJECTION_REQUIRED')
        self.robot_id = robot_id
        self.static = copy.deepcopy(static_map)
        self.frame = None
        self.observation = None
        self.candidates = {}
        self.log = []

    def observe(self, now, obs, report):
        previous = self.frame
        m1_owncam_contract.validate_observation(
            obs, robot_id=self.robot_id,
            previous_frame_id=previous.sequence if previous else None, now=now)
        if (type(obs['frame_id']) is not int or obs['frame_id'] < 0
                or not math.isfinite(float(obs['sim_time'])) or not 0 <= now - obs['sim_time'] <= .25):
            raise ContractViolation('invalid own frame clock')
        raw = base64.b64decode(obs['image'], validate=True)
        bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape != (480, 640, 3):
            raise ContractViolation('target recognizer requires the registered 640x480 wrist frame')
        pose = obs['actuator_state']['servo_pulses']
        information = perception.image_information(bgr)
        candidates, detections, ambiguous = {}, [], set()
        if information['sufficient']:
            floor = boxes.detect_own(bgr, pose, BOX_KINDS, profile=boxes.OWN_PROFILE_ZONE)
            ambiguous.update(floor['clipped_kinds'])
            for kind in BOX_KINDS:
                components, clipped = boxes._colour_components(bgr, kind, boxes.OWN_PROFILE_ZONE)
                if clipped:
                    ambiguous.add(kind)
                for index, component in enumerate(components):
                    x, y, w, h = component['bbox']
                    bbox = (x/640, y/480, (x+w)/640, (y+h)/480)
                    did = f'view-{obs["frame_id"]}-{kind}-{index}'
                    fits = [d for d in floor['detections'] if d['kind'] == kind
                            and tuple(d['pixel_bbox']) == (x, y, w, h) and d['range_class'] == 'near']
                    attention = attention_image(bgr, component['contour'])
                    attention_b64 = base64.b64encode(attention).decode()
                    # A held inference must use this component, not another cube.
                    # Keep the original background luminance for the information
                    # test; only the selected component retains colour.
                    grey = cv2.cvtColor(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                    selected = cv2.imdecode(np.frombuffer(attention, np.uint8), cv2.IMREAD_COLOR)
                    mask = np.zeros(bgr.shape[:2], np.uint8)
                    cv2.drawContours(mask, [component['contour']], -1, 255, cv2.FILLED)
                    grey[mask > 0] = selected[mask > 0]
                    held = perception.judge_held_item(grey, pose, expected_kind='cyan', candidate_kinds=('cyan',))
                    closed = int(pose['1']) < 1900
                    holding = held['answer'] if closed else ('no' if fits else 'unknown')
                    # Floor fitting does not disprove holding. Contradiction is
                    # unknown; only a clear grip-band absence permits resting.
                    if holding != 'yes' and not fits:
                        ambiguous.add(kind)
                        continue
                    if holding == 'yes' and fits:
                        holding = 'unknown'
                    matched = tuple(d.detection_id for d in (previous.detections if previous else ())
                                    if d.kind == kind and _overlap(d.bbox, bbox))
                    xy = self._map_xy(fits[0], report) if len(fits) == 1 else None
                    zone = self._zone(xy, report) if xy is not None and holding == 'no' else None
                    resting = 'yes' if fits and holding == 'no' else 'unknown'
                    detections.append(CueDetection(did, kind, bbox, matched, zone, holding, resting,
                                                   'box', BOX_SIZE))
                    candidates[did] = {'base_xy': None if not fits else fits[0]['estimated_box_center_base_m'][:2],
                                       'map_xy': xy, 'attention_b64': attention_b64,
                                       'attention_sha256': hashlib.sha256(attention).hexdigest(),
                                       'holding_evidence': held, 'floor_fits': fits}
        else:
            ambiguous.update(BOX_KINDS)
        self.frame = CueFrame(self.robot_id, obs['frame_id'], float(obs['sim_time']), obs['sha256'],
                              previous.rgb_sha256 if previous else None, tuple(detections), tuple(sorted(ambiguous)))
        self.observation, self.candidates = copy.deepcopy(obs), candidates
        self.log.append({'frame': asdict(self.frame), 'information': information,
                         'candidates': {k: {n: v for n, v in c.items() if n != 'attention_b64'}
                                        for k, c in candidates.items()}})
        return self.frame

    @staticmethod
    def _map_xy(fit, report):
        if not report.initialized:
            return None
        bx, by = fit['estimated_box_center_base_m'][:2]
        c, s = math.cos(report.yaw_rad), math.sin(report.yaw_rad)
        return [report.x_m+c*bx-s*by, report.y_m+s*bx+c*by]

    def _zone(self, xy, report):
        # Whole cube plus uncertainty inside a static destination slot; never
        # an evaluator's item position or delivery flag.
        if (report.std_xy_m > .035 or report.std_yaw_rad > .035
                or report.last_fix_t is None or report.t_est-report.last_fix_t > 3.):
            return None
        margin = .02 + 3*report.std_xy_m
        for zone, slots in self.static['zone_slots'].items():
            for slot in slots:
                if all(abs(a-b)+margin < .06 for a, b in zip(xy, slot['center_m'])):
                    return zone
        return None

    def target_view(self, job, frame, detection_id):
        if (frame != self.frame or frame.robot_id != job.robot_id
                or detection_id not in self.candidates):
            raise ContractViolation('target view must bind the latest own RGB frame')
        detection = next(d for d in frame.detections if d.detection_id == detection_id)
        if detection.kind != job.kind or detection.kind in frame.ambiguous_kinds:
            raise ContractViolation('target cue is ambiguous or changed kind')
        c = self.candidates[detection_id]
        obs = copy.deepcopy(self.observation)
        obs.update(image=c['attention_b64'], sha256=c['attention_sha256'])
        return TargetView(job.job_id, job.local_token, detection_id, frame.rgb_sha256, obs)
