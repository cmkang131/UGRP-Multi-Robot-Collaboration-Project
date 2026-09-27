"""M1 memory_v3 controller. Frozen v2 and OFF controllers remain selectable.

Interim tag source only until PR #227 supplies vision measurement diagnostics.
Grasp and place require new own-camera evidence after entering their gates;
failed verification stops instead of falling through to the skill.
"""
from __future__ import annotations

import math

from harness.m1_owncam_delivery import CLOSER_VIEW_STANDOFF_M, MAX_GATE_LOOKS, M1OwnCamDelivery
from harness.m1_owncam_memory import M1OwnCamDeliveryMem, _RecordingDetector
from harness.owncam_drive import CARRY_POSTURE, SEARCH_POSE, WIDE_LOOK_PANS
from harness.owncam_drive_mem_v3 import LegDriverMemV3
from harness.owncam_landmark_tags import TagLandmarkProvider
from harness.owncam_memory_v3 import OwnCamMemoryV3
from harness.owncam_pose_guard_v3 import OwnCamPoseSourceV3, PoseGuardV3
from harness.owncam_pose_source import PoseLimits, check_limits

SCHEMA = 'ugrp.m1_owncam_memory.v3'
BLIND_SPOT_RETREAT_M = .45
BOUNDARY_LIMITS = PoseLimits(.05, .035, max_age_s=.25)
RELEASE_POSITION_TOL_M = .03
RELEASE_YAW_TOL_RAD = .04


class M1OwnCamDeliveryMemV3(M1OwnCamDeliveryMem):
    def __init__(self, static_map, params, **kwargs):
        super().__init__(static_map, params, **kwargs)
        guard = PoseGuardV3()
        self.memory = OwnCamMemoryV3(static_map, params, robot_id=self.robot_id, guard=guard,
                                     provider=TagLandmarkProvider(static_map, params), on_event=self._memory_event)
        self.pose = OwnCamPoseSourceV3(static_map, params, seed=self.seed, guard=guard)
        self.pose.detector = _RecordingDetector(self.pose.detector)
        self.verification = {}
        self.blind_spot_retry = False

    def on_frame(self, now, obs, rgb):
        report = super().on_frame(now, obs, rgb)
        evidence = self.memory.guard.evidence or {}
        raw = self.pose.last_raw_report
        self.memory.event(now, 'pose_consistency',
                          evidence=dict(evidence), raw_std_xy_m=raw.std_xy_m if raw.initialized else None,
                          effective_std_xy_m=report.std_xy_m if report.initialized else None)
        return report

    def _start_leg(self, goal, *, loaded):
        self.leg = LegDriverMemV3(self.memory, self.pose.loc, self.map, self.params, loaded=loaded,
                                  goal_xy=goal, door_xy=self.door_xy, keepouts=self._keepouts(),
                                  initial_servo=dict(self.servo), seed=self.seed)
        self.leg.exclude_tracks = (self.target_track_id,) if self.target_track_id else ()
        if loaded:
            self.leg.drive_pose = dict(CARRY_POSTURE)
        self.leg_goal = tuple(goal)

    def _search_decide(self, now):
        target = self.memory.best_target(self.box_kind, now)
        if target is not None:
            return self._approach_target(now, target, 'own_rgb_search_memory')
        far = self.memory.best_far(self.box_kind, now, exclude=self.closer_done_tracks)
        if far is not None:
            self.closer_done_tracks.append(far.track_id)
            # A far target is an obstacle too. Stop outside its uncertainty support
            # plus the robot footprint; do not plan into the newly inflated box.
            clearance = self.params['map']['robot_clearance_m']
            standoff = max(CLOSER_VIEW_STANDOFF_M, .03 + 2*far.sigma_m() + clearance + .10)
            self._event(now, 'search_closer_view', track=far.record(now), standoff_m=standoff)
            self.phase = 'search_leg'
            self._start_leg((float(far.x[0]) - standoff, float(far.x[1])), loaded=False)
            return self._hold()
        result = super()._search_decide(now)
        if self.outcome == 'SEARCH_NOT_FOUND' and not self.blind_spot_retry:
            # A second pass moves the near blind floor strip into the camera FOV.
            # It is bounded, uses the same static planner, and never edits the map.
            self.blind_spot_retry = True
            self.outcome = None
            self.viewpoints = [(x - BLIND_SPOT_RETREAT_M, y) for x, y in self.viewpoints]
            self.view_index = -1
            self.revisit = True  # force full sweeps; stale coverage cannot suppress this pass
            self._event(now, 'blind_spot_search', viewpoints=self.viewpoints)
            return super()._search_decide(now)
        return result

    def _abandon_target(self, now, status):
        # No v2 MAX_ABANDON escape into an unverified grasp.
        if self.abandoned >= 1:
            self.outcome = 'TARGET_UNVERIFIED'
            self._event(now, 'target_unverified', status=status)
            return {'mode': 'done', 'outcome': self.outcome}
        self.abandoned += 1
        if self.target_track_id is not None:
            self.memory.rejected_targets.add(self.target_track_id)
        tr = self.memory.track(self.target_track_id)
        if tr is not None and tr.state == 'claimed':
            tr.state = 'tentative'
        self.memory.claimed = None
        self._event(now, 'target_abandoned', status=status, track=None if tr is None else tr.record(now))
        self.target_track_id, self.target_xy = None, None
        self.skill, self.approach_choice, self.order_record = None, None, None
        self.reverify_done = False
        self.leg = None
        return self._search_decide(now)

    def _approach_target(self, now, track, why):
        self.reverify_done = False
        self.verification.clear()
        return super()._approach_target(now, track, why)

    def _start_skill(self, now):
        # Arrival is verified by LegDriverMemV3. Require a new box look here too.
        if not self.reverify_done:
            self.reverify_done = True
            self.leg = None
            self.phase = 'reverify_sweep'
            self.verification['target'] = {'since': float(now)}
            self._start_sweep(now, 'search', SEARCH_POSE, WIDE_LOOK_PANS, SEARCH_POSE, 'target_reverify_v3')
            return self._hold()
        since = self.verification.get('target', {}).get('since', now)
        rv = self.memory.reverify(self.target_track_id, now, since=since)
        if rv['status'] != 'fresh':
            return self._abandon_target(now, rv['status'])
        return super()._start_skill(now)

    def _approach_leg(self, now):
        cmds, outcome = self._drive_leg(now)
        if outcome is None:
            return {'mode': 'tick', 'commands': cmds}
        if outcome != 'arrived':
            self.outcome = 'APPROACH_LEG_' + outcome
            return {'mode': 'done', 'outcome': self.outcome}
        return self._start_skill(now)

    def _after_sweep(self, now):
        if self.phase == 'reverify_sweep':
            return self._start_skill(now)
        return super()._after_sweep(now)

    def _gate_look(self, now, reason, obs, *, loaded):
        # Manipulation-boundary verification always performs a full own look.
        if reason in ('preplace', 'verify_grasp_v3', 'verify_place_v3'):
            self.gate_modes.append({'t': now, 'reason': reason, 'mode': 'full'})
            return M1OwnCamDelivery._gate_look(self, now, reason, obs, loaded=loaded)
        return super()._gate_look(now, reason, obs, loaded=loaded)

    def _boundary_gate(self, now, kind):
        gate = self.verification.setdefault(kind, {'since': float(now), 'looks': 0})
        obs = self.last_obs
        if obs is None or not -1e-8 <= now - float(obs['sim_time']) <= .25 + 1e-8:
            return {'mode': 'capture'}
        rep = self.pose.report(now)
        pose_ok = (not check_limits(rep, now, BOUNDARY_LIMITS)
                   and -1e-8 <= now - rep.t_est <= .25 + 1e-8
                   and self.memory.look_fix_since(gate['since'])
                   and self.memory.look_fix_fresh(now, (rep.x_m, rep.y_m)))
        if kind == 'grasp':
            rv = self.memory.reverify(self.target_track_id, now, since=gate['since'])
            observation_ok = rv['status'] == 'fresh'
        else:
            self.slot_record = self.memory.slot_state(now, self.slot_xy, self._slot_half(),
                                                      exclude=[self.target_track_id], since=gate['since'])
            if self.slot_record['state'] == 'occupied':
                self.outcome = 'SLOT_OCCUPIED_IN_MEMORY'
                return {'mode': 'done', 'outcome': self.outcome}
            # Loaded LOOK cannot see the slot floor. Verify release readiness
            # using evidence available at the restored lift-top posture. This
            # does NOT certify an empty slot or successful placement; the frozen
            # skill still requires its post-release own-RGB look-back.
            evidence = self._release_evidence(now, obs, rep)
            gate['release_evidence'] = evidence
            observation_ok = evidence['ready'] and evidence['observed_at'] >= gate['since']
        if pose_ok and observation_ok:
            self._event(now, 'boundary_verified', boundary=kind, since=gate['since'],
                        **({'release_evidence': evidence, 'slot_state': self.slot_record['state'],
                            'empty_slot_verified': self.slot_record['state'] == 'free'} if kind == 'place' else {}))
            return None
        if gate['looks'] >= MAX_GATE_LOOKS:
            self.outcome = kind.upper() + '_UNVERIFIED'
            return {'mode': 'done', 'outcome': self.outcome}
        gate['looks'] += 1
        return self._gate_look(now, 'verify_' + kind + '_v3', obs, loaded=kind == 'place')

    def _release_evidence(self, now, obs, rep):
        row = {'ready': False, 'observed_at': float(obs['sim_time']),
               'frame_id': obs.get('frame_id'), 'source': 'own_rgb_release_posture'}
        sk = self.skill
        if sk is None or sk.phase != 'pre_release' or not sk.box.held or sk.box.phase != 'carry':
            return {**row, 'reason': 'not_carrying_at_release'}
        if not rep.initialized or not all(math.isfinite(v) for v in (rep.x_m, rep.y_m, rep.yaw_rad)):
            return {**row, 'reason': 'no_release_pose'}
        expected = sk.box.lift_top_pose()
        issued = obs.get('actuator_state', {}).get('servo_pulses', {})
        if any(issued.get(str(k)) != v for k, v in expected.items()):
            return {**row, 'reason': 'release_posture_not_restored'}
        distance = math.dist((rep.x_m, rep.y_m), sk._preplace_goal())
        yaw = abs(math.atan2(math.sin(rep.yaw_rad), math.cos(rep.yaw_rad)))
        if distance > RELEASE_POSITION_TOL_M or yaw > RELEASE_YAW_TOL_RAD:
            return {**row, 'reason': 'outside_release_pose', 'distance_m': distance, 'yaw_rad': yaw}
        # Non-consuming comparison: the normal reanchor/probe path owns the
        # skill's observation sequence and attachment anchor updates.
        check = sk.box._compare_attachment(sk.box._attachment_image, obs['image'])
        return {**row, 'ready': bool(check.get('attached')), 'reason': check['reason'],
                'attachment': check, 'issued_posture': dict(issued), 'distance_m': distance}

    def _skill(self, now):
        sk = self.skill
        # Verify at the entry to the grasp controller, before any approach/lower
        # macro. The frozen skill then performs its own visual lock/attachment checks.
        if sk is not None and sk.phase == 'grasp' and not self.verification.get('grasp', {}).get('passed'):
            result = self._boundary_gate(now, 'grasp')
            if result is not None:
                return result
            self.verification['grasp']['passed'] = True
        if sk is not None and sk.phase == 'pre_release':
            self.verification.setdefault('place', {'since': float(now), 'looks': 0})
            # A look changes the held camera's posture. Complete the existing
            # strict reanchor / bounded pan probe before checking readiness.
            # These branches return before the frozen skill can begin release.
            obs = self.last_obs
            if self.probe is not None or self.reanchor_needed:
                leg_busy = self.leg is not None and self.leg.state in ('look_arm', 'look_pan', 'posture_back')
                if (obs is None or not -1e-8 <= now - float(obs['sim_time']) <= .25 + 1e-8
                        or obs['frame_id'] == self.last_skill_frame or leg_busy):
                    return {'mode': 'capture'}
                return M1OwnCamDelivery._skill(self, now)
            result = self._boundary_gate(now, 'place')
            if result is not None:
                return result
            self.slot_checked = True
        return super()._skill(now)

    def summary(self):
        return {**super().summary(), 'schema': SCHEMA, 'verification_v3': self.verification,
                'blind_spot_retry_v3': self.blind_spot_retry}
