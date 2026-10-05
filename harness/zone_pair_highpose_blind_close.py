"""v98 blind final approach: confirm the resting beam at the hover, then descend and close without a beam view.

Why. At the fixed floor grasp posture (servo 1269/2052/2494/1500) the own wrist camera sees 0 beam pixels, so the
pre-close beam track (``beam_track.estimate``) returns None there and ``preclose_check`` refused every close with
``BEAM_UNCERTAIN`` -> ``PREGRASP_NOT_READY`` (DEV probe raise_high_align at 3358372e, r1, 54.1 SIM s). The camera
placement and field of view stay as they are (AGENTS.md). Offline replay of that run's own frames:

* standoff (inspect posture 508/2432/1320): full standoff fit, std 15 mm / 1 degree;
* hover (807/1897/2187, tool z 95 mm): 27k beam-colour points; the unchanged track check passes (footprint
  support 1.0, cross-section 38.5 mm); lateral centre of the beam band 0.06 mm from the fixed station line;
* grasp (1269/2052/2494, tool z 24 mm): 0 beam pixels, estimate None.
  The hover is the LAST calibrated posture where the beam is visible (the descent steps in between have no
  measured camera model; pixels were last seen at tool z ~29 mm).

Method (look-then-move / pre-grasp observation, then an open-loop final approach; see the experiment note's
reference section). Minimal change to the existing descent:

1. The open descent stops at the hover (+ ``HOVER_SETTLE_S``). There the UNCHANGED pre-close check runs
   (``CommandGuard.preclose_check``: own pose report, frame gate, same camera commands, visual beam track
   estimate, stationary beam clearance). On success the hover check also requires the beam band's lateral
   centre on the fixed grasp station line within ``HOVER_LATERAL_TOL_M`` (= the align tolerance). Both must pass
   on ``HOVER_CONFIRM_FRAMES`` (2) consecutive distinct own frames, as the align stop does; any failing frame resets
   the count. The blind window is armed on the resting beam track from the latest passing frame. The longitudinal position is not observable at the hover (band
   clipped); it comes from the standoff fit and the align stage, with zero base motion since.
2. The fixed descent path (hover -> grasp, 7 x 0.12 s, vertical 71 mm, no base motion) is queued and the
   unchanged close readiness / close barrier follows. At the grasp posture the track returns the propagated
   standoff hypothesis instead of a visual patch check, only while the blind window holds:
   confirmed at the hover in this segment, every issued command since then inside the fixed path envelope
   (no base motion, no pan change, no off-path arm pulse, no gripper reopen), still at the grasp posture,
   within ``BLIND_MAX_S`` of the confirming frame, descent within ``BLIND_MAX_DROP_M`` / ``BLIND_MAX_XY_M``,
   and the track hypothesis itself within its frozen age (30 s) and sigma (50 mm / 3 degrees) bounds.
   Otherwise the close is refused with a ``BLIND_*`` code.

Inputs: own RGB (hover frame), the measured camera model of the fixed hover posture, own issued commands.
No ground truth, contact or success flag, no shared camera. A partner nudge of the beam during the blind window
is not detectable before the close; post-close own-grip detection with a partner signal is deferred (grip
monitor stays log-only, registry ``grip_monitor``).
"""
from __future__ import annotations

import functools
import math

import numpy as np

from harness import owncam_pair_beam as v1
from harness import zone_pair_beam_track as resting
from harness.zone_final_pair_vision import ALIGN_TOL_X_M, ALIGN_TOL_Y_M, GRASP_RADIUS_M, grasp_postures
from harness.zone_pair_grasp import CLOSE_WAIT_S, FIX_STD_XY_M, FIX_STD_YAW_RAD
from harness.zone_pair_grasp_entry_v6c import FINAL_DESCENT_SETTLE_S

PROFILE = 'zone_pair_blind_final_approach_v98'
JOINTS = (3, 4, 5, 6)               # camera/arm posture; finger PWM (1) does not move the camera
OPEN_PWM = 2000                     # = study.OPEN (gripper open, run_m2_pair/study_owncam_pair_beam)
HOVER_SETTLE_S = FINAL_DESCENT_SETTLE_S     # same rule as the final descent: a lagging frame is not a pose view
HOVER_CONFIRM_MAX_S = 1.               # bounded retries on new own frames (input-validity transients)
HOVER_CONFIRM_FRAMES = 2               # consecutive passing distinct own frames, as the align stop (aligned_streak >= 2)
DESCENT_STEP_S = .12                   # V3Controller fixed descent step
CLOSE_RAMP_S = .5                      # gripper close queue duration (HighController._wait_close)
GRID_SLACK_S = .5                      # control grid / GO offset slack
HOVER_LATERAL_TOL_M = ALIGN_TOL_Y_M    # 3 mm, the align stop tolerance; measured 0.06 mm (one sample)
BLIND_MAX_DROP_M = .075                # commanded drop 71.1 mm
BLIND_MAX_XY_M = .002                  # commanded horizontal change 0.02 mm
PULSE_TOL = 2                          # ArmSequence rounds interpolated pulses


def _tool(servo):
    from harness import visual_arm_v3 as arm
    return arm.tool_pose(servo)


# Every refusal name this module can produce (controller failure = 'PREGRASP_' + code). Evaluation-side cause
# classification of these names: scripts/run_pair_highpose.failure_cause (v98 only).
HOVER_CODES = tuple('PREGRASP_HOVER_'+k for k in ('UNCONFIRMED', 'NOT_VISUAL', 'POSE_NOT_COMMANDED', 'LATERAL_SHIFT'))
BLIND_CODES = tuple('PREGRASP_BLIND_'+k for k in (
    'NOT_CONFIRMED', 'BASE_MOVED', 'PAN_MOVED', 'ARM_OFF_PATH', 'GRIPPER_REOPENED', 'UNKNOWN_COMMAND',
    'SEGMENT_CHANGED', 'WINDOW_EXPIRED', 'DISTANCE_EXCEEDED', 'TRACK_UNCERTAIN'))


def limits():
    """Blind limits derived from the fixed postures and the inherited close timing (no new tuning)."""
    hover, path = grasp_postures()
    h, g = _tool(hover), _tool(path[-1])
    descent_s = len(path)*DESCENT_STEP_S+FINAL_DESCENT_SETTLE_S
    return {'blind_max_s': descent_s+CLOSE_WAIT_S+CLOSE_RAMP_S+GRID_SLACK_S,
            'blind_max_s_terms': {'descent_s': descent_s, 'close_wait_s': CLOSE_WAIT_S,
                                  'close_ramp_s': CLOSE_RAMP_S, 'grid_slack_s': GRID_SLACK_S},
            'anchor_max_age_s': resting.MAX_AGE_S, 'track_std_xy_max_m': FIX_STD_XY_M,
            'track_std_yaw_max_rad': FIX_STD_YAW_RAD,
            'blind_max_drop_m': BLIND_MAX_DROP_M, 'blind_max_xy_m': BLIND_MAX_XY_M,
            'commanded_drop_m': h.z_m-g.z_m, 'commanded_xy_m': math.hypot(h.x_m-g.x_m, h.y_m-g.y_m),
            'base_motion_m': 0., 'hover_lateral_tol_m': HOVER_LATERAL_TOL_M,
            'hover_settle_s': HOVER_SETTLE_S, 'hover_confirm_max_s': HOVER_CONFIRM_MAX_S,
            'hover_confirm_frames': HOVER_CONFIRM_FRAMES}


def record():
    hover, path = grasp_postures()
    return {'profile': PROFILE, 'confirm_posture': {str(k): hover[k] for k in JOINTS},
            'blind_posture': {str(k): path[-1][k] for k in JOINTS}, 'limits': limits(),
            'inputs': 'own RGB at the hover + measured hover camera model + own issued commands',
            'not_inputs': 'ground truth, contact/success flags, shared top camera',
            'grip_loss_after_close': 'log-only (own-grip detection + partner signal deferred)'}


@functools.lru_cache(maxsize=1)
def _blind_posture():
    return tuple(sorted(grasp_postures()[1][-1].items()))


def at_posture(servo, pose):
    pose = dict(pose)
    try:
        return all(int(servo[k]) == int(pose[k]) for k in JOINTS)
    except (KeyError, TypeError, ValueError):
        return False


def station_lateral_m(patch, beam):
    """Beam band centreline offset from the fixed grasp station line (y = 0 at x = GRASP_RADIUS_M), own frame.

    Same footprint as the frozen track check; 2-98 % across-axis span beyond the tracked grip, as
    ``zone_pair_grasp_entry_v6c.cross_section``. None without enough in-footprint points.
    """
    if patch is None or beam is None:
        return None
    h = beam['axis_heading_rad']
    u, n_hat = np.array([math.cos(h), math.sin(h)]), np.array([-math.sin(h), math.cos(h)])
    grip = np.asarray(beam['grip_base_m'], float)
    rel = np.asarray(patch, float)-grip
    a, n = rel @ u, rel @ n_hat
    pad = 2*(beam['std_xy_m']+beam['std_yaw_rad']*.60)
    inside = (a > 0.) & (a <= .57+pad) & (np.abs(n) <= .02+pad)
    if inside.sum() < v1.MIN_POINTS:
        return None
    lo, hi = np.percentile(n[inside], [2, 98])
    centre = grip+(lo+hi)/2*n_hat
    if abs(u[0]) < 1e-6:
        return None
    return float(centre[1]+(GRASP_RADIUS_M-centre[0])*u[1]/u[0])


def _envelope(hover, path):
    rows = [hover, *path]
    return {k: (min(p[k] for p in rows)-PULSE_TOL, max(p[k] for p in rows)+PULSE_TOL) for k in (3, 4, 5)}


def off_window(row, servo, window):
    """BLIND_* code if this issued command leaves the fixed descent / close envelope, else None."""
    kind = row.get('kind')
    if kind == 'hold':
        return None
    if kind in ('drive', 'mecanum'):
        return 'BLIND_BASE_MOVED' if any(row.get(k, 0.) for k in ('forward', 'left', 'turn')) else None
    if kind == 'look':
        return None if row.get('pan_pulse') == window['pan'] else 'BLIND_PAN_MOVED'
    if kind == 'arm':
        sid, pulse = int(row['servo_id']), row['pulse']
        if sid == 1:
            return 'BLIND_GRIPPER_REOPENED' if pulse >= OPEN_PWM and servo.get(1, OPEN_PWM) < OPEN_PWM else None
        if sid == 6:
            return None if pulse == window['pan'] else 'BLIND_PAN_MOVED'
        lo, hi = window['envelope'].get(sid, (math.inf, -math.inf))
        return None if lo <= pulse <= hi else 'BLIND_ARM_OFF_PATH'
    return 'BLIND_UNKNOWN_COMMAND'


class BlindTrack:
    """Mixin before the v98 measured resting beam track; the frozen track code is unchanged underneath."""
    blind_window = None
    blind_code = None
    blind_patch = None
    last_visual = None

    def _partial_points(self, obs, servo):
        pts, reason = super()._partial_points(obs, servo)
        self.blind_patch = pts
        return pts, reason

    def observe_standoff(self, obs, servo, segment):
        ok = super().observe_standoff(obs, servo, segment)
        if ok:
            self.blind_window = None        # a new anchor needs a new hover confirmation
        return ok

    def command(self, row, servo):
        super().command(row, servo)
        window = self.blind_window
        if window is not None and window['disarmed'] is None:
            code = off_window(row, servo, window)
            if code is not None:
                window['disarmed'] = {'code': code, 't': row.get('t'), 'row': dict(row)}

    def begin_hover_check(self):
        self.blind_window, self.blind_code, self.last_visual = None, None, None

    def estimate(self, now, obs, servo, segment):
        self.blind_patch = None
        got = super().estimate(now, obs, servo, segment)
        if got is not None:
            self.last_visual = {'sim_s': now, 'frame_id': obs['frame_id'], 'sha256': obs.get('sha256'),
                                'servo': {k: servo.get(k) for k in (1, *JOINTS)}, 'patch': self.blind_patch,
                                'beam': {k: got[k] for k in ('grip_base_m', 'axis_heading_rad', 'std_xy_m',
                                                             'std_yaw_rad')}}
            return {**got, 'evidence': 'visual'}
        if not at_posture(servo, _blind_posture()):
            return None                     # not the blind posture: the frozen visual verdict stands
        code, value = self._blind(now, segment)
        self.blind_code = code
        return value

    def _blind(self, now, segment):
        w = self.blind_window
        if w is None:
            return 'BLIND_NOT_CONFIRMED', None
        if w['disarmed'] is not None:
            return w['disarmed']['code'], None
        if segment != w['segment'] or self.segment != w['segment']:
            return 'BLIND_SEGMENT_CHANGED', None
        blind_s = now-w['confirmed_at_s']
        if not 0. <= blind_s <= w['limits']['blind_max_s']:
            return 'BLIND_WINDOW_EXPIRED', None
        if w['drop_m'] > BLIND_MAX_DROP_M or w['xy_m'] > BLIND_MAX_XY_M:
            return 'BLIND_DISTANCE_EXCEEDED', None
        b = self.beam                       # already advanced to ``now`` by the frozen estimate
        if (b is None or self.segment != segment or not 0 <= now-b['anchor_time_s'] <= resting.MAX_AGE_S
                or not 0 <= b['std_xy_m'] <= FIX_STD_XY_M or not 0 <= b['std_yaw_rad'] <= FIX_STD_YAW_RAD):
            return 'BLIND_TRACK_UNCERTAIN', None
        return None, {**b, 'grip_base_m': list(b['grip_base_m']), 'evidence': 'blind_after_hover_confirmation',
                      'blind_profile': PROFILE, 'blind_s': blind_s, 'blind_confirmed_frame_id': w['frame_id'],
                      'blind_confirmed_sha256': w['sha256'], 'blind_confirmed_at_s': w['confirmed_at_s'],
                      'blind_drop_m': w['drop_m'], 'blind_xy_m': w['xy_m'],
                      'blind_hover_lateral_m': w['lateral_m']}

    def confirm(self, now, obs, servo, segment, hover, path):
        """Arm the blind window after a passing hover pre-close check; returns None or a HOVER_* code."""
        v = self.last_visual
        if v is None or v['frame_id'] != obs['frame_id'] or v['sim_s'] != now:
            return 'HOVER_NOT_VISUAL'
        if not at_posture(servo, hover) or servo.get(1) != OPEN_PWM:
            return 'HOVER_POSE_NOT_COMMANDED'
        lateral = station_lateral_m(v['patch'], self.beam)
        if lateral is None or abs(lateral) > HOVER_LATERAL_TOL_M:
            return 'HOVER_LATERAL_SHIFT'
        h, g = _tool(hover), _tool(path[-1])
        self.blind_window = {'profile': PROFILE, 'segment': segment, 'confirmed_at_s': float(obs['sim_time']),
                             'confirm_tick_s': now, 'frame_id': obs['frame_id'], 'sha256': obs.get('sha256'),
                             'hover': {k: hover[k] for k in JOINTS}, 'grasp': {k: path[-1][k] for k in JOINTS},
                             'envelope': _envelope(hover, path), 'pan': hover[6],
                             'drop_m': h.z_m-g.z_m, 'xy_m': math.hypot(h.x_m-g.x_m, h.y_m-g.y_m),
                             'lateral_m': lateral, 'beam_at_confirm': dict(v['beam']), 'limits': limits(),
                             'disarmed': None}
        return None

    def window_record(self):
        w = self.blind_window
        if w is None:
            return None
        return {k: w[k] for k in ('profile', 'segment', 'confirmed_at_s', 'frame_id', 'sha256', 'drop_m',
                                  'xy_m', 'lateral_m', 'beam_at_confirm', 'disarmed')}

    def reference_record(self, now):
        """Read-only age of the resting-beam reference the hover check stands on (review delta3 P2-1).

        The reference is the standoff anchor: a hover partial image never renews its time or sigma (frozen
        ``RestingBeamTrack.estimate``), so every wait at the hover ages it. The frozen track refuses an estimate older
        than ``resting.MAX_AGE_S`` (30 s, unchanged); this record only makes that refusal visible in the log.
        """
        b = self.beam
        if b is None:
            return {'anchor_time_s': None, 'age_s': None, 'max_age_s': resting.MAX_AGE_S, 'expired': None}
        age = float(now)-float(b['anchor_time_s'])
        return {'anchor_time_s': b['anchor_time_s'], 'age_s': round(age, 4), 'max_age_s': resting.MAX_AGE_S,
                'expired': not 0 <= age <= resting.MAX_AGE_S}


def adopt(guard, controller):
    """Give the v98 guard's resting beam track the blind window; hand the controller the same object."""
    track = guard.beam_track
    if not isinstance(track, resting.RestingBeamTrack) or isinstance(track, BlindTrack):
        raise TypeError(f'v98 blind close expects one resting beam track, got {type(track).__name__}')
    track.__class__ = type('BlindFinalApproachTrack', (BlindTrack, type(track)), {})
    controller.blind_track = track
    return track


class HoverConfirm:
    """Controller mixin placed right after ``HighController`` (before ``V3Controller``).

    ``_queue_open_descent`` is V3Controller's (same alignment bound, fixed postures, log) with the descent split at
    the hover; ``_pregrasp_descend`` runs the hover check before the parent's unchanged descend/close path.
    """

    def _queue_open_descent(self, now):
        from scripts import run_m2_pair as m2
        bx, by = self.grip_base
        if abs(bx-GRASP_RADIUS_M) > ALIGN_TOL_X_M+1e-9 or abs(by) > ALIGN_TOL_Y_M+1e-9:
            return self.fail('V3_GRIP_OUTSIDE_FIXED_POSTURE', now)
        try:
            self.hover, path = grasp_postures()
        except Exception as exc:
            return self.fail(f'IK_UNAVAILABLE:{exc}', now)
        self.grasp_pose, self.blind_path = path[-1], path
        self.log(self.rid, 'v3_grasp_target', now, observed_grip=list(self.grip_base),
                 commanded_target=[GRASP_RADIUS_M, 0.], source='fixed calibrated posture; own RGB alignment')
        self.arm.queue({**self.hover, 1: m2.study.OPEN}, now, duration=1.)
        self.arm.until += HOVER_SETTLE_S
        self.blind_phase, self.blind_hover_started = 'hover', None
        self.blind_hover_streak, self.blind_hover_last_frame = 0, None
        self.set('pregrasp_descend', now, blind_phase='hover', profile=PROFILE)

    def _pregrasp_descend(self, now, arm_idle):
        if getattr(self, 'blind_phase', None) != 'hover':
            return super()._pregrasp_descend(now, arm_idle)
        if not arm_idle:
            return
        if self.blind_hover_started is None:
            self.blind_hover_started = now
        track, own = self.blind_track, self.port.own
        obs = self.look(now)
        track.begin_hover_check()
        code = None if self.preclose_check(now, obs) else 'PREGRASP_HOVER_UNCONFIRMED'
        if code is None:
            refused = track.confirm(now, obs, dict(own.servo), self.seg, self.hover, self.blind_path)
            code = None if refused is None else 'PREGRASP_'+refused
        if code is None:
            if obs['frame_id'] != self.blind_hover_last_frame:      # a repeated frame is not a new confirmation
                self.blind_hover_streak += 1
        else:
            self.blind_hover_streak = 0
        self.blind_hover_last_frame = obs['frame_id']
        checks = self._grasp_pose_checks(now)
        reference = getattr(track, 'reference_record', None)
        self.log(self.rid, 'blind_hover_check', now, ok=code is None, code=code, frame_id=obs['frame_id'],
                 sha256=obs.get('sha256'), checks=checks, failed_checks=[k for k, v in checks.items() if not v],
                 streak=self.blind_hover_streak, need=HOVER_CONFIRM_FRAMES,
                 window=track.window_record(), reference=None if reference is None else reference(now),
                 profile=PROFILE)
        if code is not None:
            # A failed frame cancels a readiness already sent at once (v98 re-fix hover@k+1 barrier, review delta3
            # P1-1): the channel would otherwise keep it for its whole TTL and the partner alone could get the GO.
            withdraw = getattr(self, 'hover_barrier_withdraw', None)
            if withdraw is not None:
                withdraw(now, obs, code)
            if now-self.blind_hover_started < HOVER_CONFIRM_MAX_S:
                return                      # retry on a later own frame, bounded
            return self.fail(code, now)
        if self.blind_hover_streak < HOVER_CONFIRM_FRAMES:
            return                          # the window stays armed from the latest passing frame; next frame decides
        gate = getattr(self, 'hover_barrier_gate', None)
        if gate is not None and not gate(now, obs):
            return                          # v98 re-fix re-grasp: hover@k+1 pair barrier (zone_pair_highpose_refix)
        for pose in self.blind_path:
            self.arm.queue(pose, now, duration=DESCENT_STEP_S, settle=0.)
        self.arm.until += FINAL_DESCENT_SETTLE_S
        self.blind_phase = 'descend'
        self.log(self.rid, 'blind_descent_queued', now, steps=len(self.blind_path),
                 drop_m=track.blind_window['drop_m'], until_s=self.arm.until, profile=PROFILE)
