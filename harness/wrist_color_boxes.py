"""T03 wrist color boxes v1 (DRAFT, no physical acceptance).

The manipulation state machine is the N7 decide body at c1279667 with explicit
kind perception, inheriting v9 motion/recovery and v6 probe validation. This
local copy is intentional: frozen N7/v1-v9 and successful bundle bytes stay
unchanged. All three colors use this same candidate. Legacy cyan v9 is still
available, and its physical results are not inherited by this candidate.
"""
from __future__ import annotations
import base64
import hashlib
from collections.abc import Mapping
from typing import Any
import numpy as np
from harness import m1_color_perception as perception
from harness import m1_contract
from harness import wrist_zone_skill as v1
from harness import wrist_zone_skill_v3 as v3
from harness import wrist_zone_skill_v9 as v9
from harness.m1_color_contract import BOX_KINDS, require_box_kind
from harness.visual_box_skill import _pose, _wait, _clip_int
from harness.visual_arm import forward_grip

PROFILE = 'wrist_color_boxes_v1'


class KindBoxSkill(v9.WristOnlyBoxSkillV9):
    def __init__(self, *, box_kind, **kwargs):
        self.box_kind = require_box_kind(box_kind)
        if kwargs.get('perception_mode', 'markerless') != 'markerless':
            raise ValueError('color boxes require markerless own RGB')
        super().__init__(**kwargs)
        self._face_aligner = perception.KindEdgeYawAligner(self.box_kind)

    def _compare_attachment(self, *args, **kwargs):
        return perception.compare_box_comotion(*args, kind=self.box_kind, **kwargs)

    def decide(self, observation):
        self._face_aligner.frame = observation
        try:
            action = self._decide_color(observation)
        finally:
            self._face_aligner.frame = None
        # v1's own-wrist face-inspection nudges, without entering the old cyan detector.
        waiting = (self.phase == 'approach' and action.get('kind') == 'wait'
                   and self._face_inspection_reached and not self._face_approach and self._face_alignment_waits > 0)
        if not waiting:
            if self._face_approach:
                self._nudge_origin = None
            return action
        if self._nudge_origin is None:
            self._nudge_origin = int(self._last_seen_pose['3'])
        if self.face_nudges < len(v1.FACE_NUDGES_PWM):
            target = _clip_int(self._nudge_origin + v1.FACE_NUDGES_PWM[self.face_nudges], 500, 2200)
            self.face_nudges += 1
            return _pose({3: target})
        return action

    def _decide_color(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        try:
            obs, pose = self._validate_observation(observation)
        except ValueError:
            self._face_aligner.reset_window()
            self.last_target = None
            self.last_face_alignment = {'ready': False, 'normal_xy': None,
                                        'reason': 'INVALID_OWN_FRAME'}
            raise
        self.last_approach_adjustment = None
        if self.phase != "approach":
            self._rolling_view_lock = None
        ground_phase = self.phase in {"approach", "verify_release", "release_ground_left", "release_ground_right", "release_ground_home"}
        box = (perception.observe_ground_box(obs['image'], pose, self.box_kind) if ground_phase
               else {'visible': False, 'reason': 'GROUND_ESTIMATE_NOT_APPLICABLE_WHILE_HELD'})
        target = None
        target_provenance = None
        if self.perception_mode == "markerless" and box.get("visible") is True:
            point = box.get("estimated_box_center_base_m")
            if isinstance(point, (list, tuple)) and len(point) == 3 and np.all(np.isfinite(point)):
                target = np.asarray(point, dtype=float)
                target_provenance = "ground_shape_fit:" + str(box.get("provenance", "unknown"))
        self.last_surface = None
        if self._grasp is not None and self.phase != "approach" and not (self.perception_mode == "markerless" and ground_phase):
            surface = perception.observe_known_box_top(obs["image"], pose, self.box_kind, target_id=self.cargo_id)
            self.last_surface = surface
            if target is None and surface.get("visible") and surface.get("confidence", 0) >= .5:
                target = np.asarray(surface["estimated_surface_patch_base_m"], dtype=float)
                target[2] = surface["estimated_box_center_height_m"]
                target_provenance = "surface_height:" + str(surface.get("provenance", "unknown"))
        self.last_box = dict(box)
        self.last_target = tuple(float(v) for v in target) if target is not None else None
        self.last_target_provenance = target_provenance

        if self.phase == "approach":
            if self._face_aligner is not None:
                # The 4 cm top is too small for reliable face orientation at
                # the initial half-metre range. First obtain a closer RGB
                # view while retaining the observed centre and drive guard.
                if target is not None and np.linalg.norm(target[:2]) <= .405:
                    self._face_inspection_reached = True
                if self._face_inspection_reached:
                    self.last_face_alignment = self._face_aligner.observe(
                        box, tuple(target[:2]) if target is not None else ())
                else:
                    self.last_face_alignment = {"ready": False,
                        "reason": "CLOSER_FACE_INSPECTION_REQUIRED", "normal_xy": None}
            return self._approach(box, target, pose)
        if self.phase == "lower":
            if self._lower_path:
                return _pose(self._lower_path.pop(0))
            self.phase = "close"
            return _pose({1: 1500})
        if self.phase == "close":
            self.phase = "lift"
            if self._lift_path:
                return _pose(self._lift_path.pop(0))
            return self._finish("MISSING_LIFT_PATH")
        if self.phase == "lift":
            if self._lift_path:
                return _pose(self._lift_path.pop(0))
            self.phase = "verify_lift"
            return _wait(0.05)
        if self.phase == "verify_lift":
            self.last_attachment = self._compare_attachment(obs["image"], obs["image"])
            if not self.last_attachment["attached"]:
                return self._finish("VISUAL_LIFT_UNCONFIRMED")
            self._attachment_image = obs["image"]
            self._attachment_pan = int(pose["6"])
            self._probe_results = []
            if not 560 <= self._attachment_pan <= 2440:
                return self._finish("ATTACHMENT_PROBE_PAN_LIMIT")
            self.phase = "attachment_left"
            return _pose({6: self._attachment_pan + 60, 1: 1500})
        if self.phase in {"attachment_left", "attachment_right", "attachment_home",
                          "carry_probe_left", "carry_probe_right", "carry_probe_home"}:
            pan_delta = int(pose["6"]) - int(self._attachment_pan)
            self.last_attachment = self._compare_attachment(
                self._attachment_image, obs["image"], camera_pan_delta_pwm=pan_delta)
            if (self.attachment_home_reference == 'previous_endpoint'
                    and self.phase in {'attachment_home','carry_probe_home'}):
                # All three fresh interventions must show comotion. Compare
                # home to the immediately preceding endpoint so slow grip
                # compliance does not accumulate across the entire sweep.
                # Opposite endpoints must still pass the independent 120-PWM
                # test below; a stationary floor box cannot pass that test.
                anchor_metrics = self.last_attachment
                self.last_attachment = self._compare_attachment(self._probe_last_image,
                    obs['image'], camera_pan_delta_pwm=int(pose['6'])-self._probe_last_pan)
                self.last_attachment['initial_anchor_metrics'] = anchor_metrics
            self._probe_results.append(bool(self.last_attachment["attached"]))
            is_carry_probe = self.phase.startswith("carry_probe")
            if self.phase == "attachment_left":
                self._probe_side_image = obs["image"]
                self.phase = "attachment_right"
                return _pose({6: self._attachment_pan - 60, 1: 1500})
            if self.phase == "carry_probe_left":
                self._probe_side_image = obs["image"]
                self.phase = "carry_probe_right"
                return _pose({6: self._attachment_pan - 60, 1: 1500})
            if self.phase == "attachment_right":
                self._probe_side_pair = self._compare_attachment(
                    self._probe_side_image, obs["image"], camera_pan_delta_pwm=-120)
                self.phase = "attachment_home"
                self._probe_last_image, self._probe_last_pan = obs['image'], int(pose['6'])
                return _pose({6: self._attachment_pan, 1: 1500})
            if self.phase == "carry_probe_right":
                self._probe_side_pair = self._compare_attachment(
                    self._probe_side_image, obs["image"], camera_pan_delta_pwm=-120)
                self.phase = "carry_probe_home"
                self._probe_last_image, self._probe_last_pan = obs['image'], int(pose['6'])
                return _pose({6: self._attachment_pan, 1: 1500})
            # Require the box to remain camera-relative across the complete
            # left-to-right sweep and to recover at home.  Either endpoint can
            # move more than its one-sided bound while a compliant held box
            # yaws, but a detached box traverses far across the two endpoints.
            self.last_attachment["side_pair_metrics"] = self._probe_side_pair
            sequential_failed = (self.attachment_home_reference == 'previous_endpoint'
                                 and not all(self._probe_results))
            if sequential_failed or not self.last_attachment["attached"] or not self._probe_side_pair["attached"]:
                return self._finish("VISUAL_LOAD_DROPPED_OR_OCCLUDED" if is_carry_probe
                                    else "VISUAL_ATTACHMENT_UNCONFIRMED")
            if self._probe_origin_phase == "surface_low_height":
                self._surface_drop_probe_validated = True
            self.held = True
            self._attachment_image = obs["image"]
            self._carry_previous_image = obs["image"]
            self.phase = "carry"
            self._probe_results = []
            self._probe_origin_phase = None
            return _wait(.1)
        if self.phase == "carry":
            return self._carry(obs, pose)
        if self.phase == "release":
            if self._release_path:
                return _pose(self._release_path.pop(0))
            self.phase = "open"
            return _pose(self._required_plan(self._grasp, "grasp"))
        if self.phase == "open":
            self.phase = "retract"
            return _pose({1: 2000})
        if self.phase == "retract":
            self.phase = "verify_release"
            return _pose({**self._inspection_pose, 1: 2000})
        if self.phase == "verify_release":
            if self.perception_mode == "markerless" and target is not None:
                # Ground-fitting one image is conditional on the floor model.
                # Also require the observed box to stay fixed in the base
                # frame across a controlled camera sweep after opening.
                expected = forward_grip(self._required_plan(self._grasp, "grasp"))
                if np.linalg.norm(np.asarray(target[:2])-np.asarray(expected[:2])) <= .045:
                    pan = int(pose["6"])
                    if not 560 <= pan <= 2440:
                        return self._finish("RELEASE_PROBE_PAN_LIMIT")
                    self._release_ground_origin_pan = pan
                    self._release_ground_probe = [tuple(target)]
                    self.phase = "release_ground_left"
                    return _pose({6: pan + 60})
                target = None
            if target is not None and -.01 <= target[2] <= .04:
                return self._finish("VISUAL_RELEASE_CONFIRMED")
            self._release_scan_attempts += 1
            if self._release_scan_attempts > 24:
                return self._finish("VISUAL_RELEASE_UNCONFIRMED")
            elbow = min(2500, int(pose["4"]) + 8)
            if elbow != int(pose["4"]) and self._release_scan_attempts <= 13:
                return _pose({4: elbow})
            offset = ((self._release_scan_attempts - 13) // 2 + 1) * 30
            offset *= -1 if self._release_scan_attempts % 2 else 1
            return _pose({6: _clip_int(self._inspection_pose[6] + offset, 500, 2500)})
        if self.phase in {"release_ground_left", "release_ground_right", "release_ground_home"}:
            expected_pan = self._release_ground_origin_pan + {
                "release_ground_left": 60, "release_ground_right": -60,
                "release_ground_home": 0}[self.phase]
            if abs(int(pose["6"]) - expected_pan) > 2:
                return self._finish("RELEASE_PROBE_POSE_UNCONFIRMED")
            if target is None:
                return self._finish("RELEASE_GROUND_TARGET_UNOBSERVABLE")
            self._release_ground_probe.append(tuple(target))
            # Check every pair, especially opposite sweep endpoints: a
            # camera-following object can otherwise sit within each origin
            # tolerance while traversing twice that amount left to right.
            if any(np.linalg.norm(np.asarray(target[:2])-np.asarray(prior[:2])) > .010
                   for prior in self._release_ground_probe[:-1]):
                return self._finish("RELEASE_OBJECT_NOT_GROUND_STATIONARY")
            if self.phase == "release_ground_left":
                self.phase = "release_ground_right"
                return _pose({6: self._release_ground_origin_pan - 60})
            if self.phase == "release_ground_right":
                self.phase = "release_ground_home"
                return _pose({6: self._release_ground_origin_pan})
            return self._finish("VISUAL_RELEASE_CONFIRMED")
        return {"kind": "finish", "reason": self.reason}


class WristColorBoxDelivery(v9.WristZoneDeliveryV9):
    supported_box_kinds = BOX_KINDS
    color_profile = PROFILE
    box_perception_profile = perception.PROFILE

    def __init__(self, order, *, mode='m1', **kwargs):
        require_box_kind(order.kind)
        super().__init__(order, mode=mode, **kwargs)

    def _new_box(self):
        return KindBoxSkill(box_kind=self.order.kind, robot_id=self.robot_id, cargo_id='small_box_01',
                            **v1.BOX_SKILL_OPTIONS)

    # Conservative v3 stop/probe on a low top. Do not use v4's cyan-only
    # self-occlusion shortcut. This choice is identical for all three kinds.
    _nav_preplace = v3.WristZoneDeliveryV3._nav_preplace

    def confirm_placement(self, obs, est):
        if self.mode == 'm1':
            m1_contract.require_m1_pose_source(est.source, 'judge:confirm_placement')
        check = self._validated or {}
        try:
            digest = hashlib.sha256(base64.b64decode(obs['image'], validate=True)).hexdigest()
        except Exception as exc:
            raise ValueError('placement frame is not a valid image payload') from exc
        if not (obs.get('camera') == 'robot_cam' == check.get('camera') and obs.get('robot_id') == self.robot_id
                and obs.get('frame_id') == check.get('frame_id') and obs.get('sha256') == check.get('sha256') == digest):
            raise ValueError('placement frame is not the last strictly validated own robot_cam frame')
        fit = perception.observe_ground_box(obs['image'], obs['actuator_state']['servo_pulses'], self.order.kind)
        result = {'in_slot': False, 'reason': 'TARGET_KIND_NOT_UNIQUELY_VISIBLE'}
        if fit['visible']:
            bx, by = fit['estimated_box_center_base_m'][:2]
            result = self._slot_verdict(bx, by, est)
        return {**result, 'kind': self.order.kind, 'detector': perception.PROFILE, 'fit_reason': fit['reason'],
                'observation_validated': True, 'frame_id': obs['frame_id'], 'frame_sha256': digest,
                'mode': self.mode, 'counts_as_m1_input': m1_contract.is_m1_pose_source(est.source)}

    def summary(self):
        return {**super().summary(), 'profile': PROFILE, 'box_kind': self.order.kind,
                'physical_acceptance': 'unmeasured'}
