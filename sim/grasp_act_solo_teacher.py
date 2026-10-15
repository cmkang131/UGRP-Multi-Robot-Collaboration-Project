"""Opt-in solo demonstration teacher; no World, simulator state or evaluation input.

This is a teacher, never a fallback for student execution. The caller starts
the local skill explicitly. A hidden distance cannot start its clock or select
training samples. Shared pair primitives provide IK, issued-arm interpolation,
camera gaze and native wheel pulses; their legacy callers remain unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import math

PROFILE = 'solo_visible_only_v1'
BOX_KINDS = ('cyan', 'red', 'green', 'yellow')
KINDS = (*BOX_KINDS, 'can', 'tile')
MEMORY_S = 5.2
PERIOD_S = .1


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


@dataclass(frozen=True)
class Cargo:
    kind: str
    dims_m: tuple
    mass_kg: float
    grip_z_m: float
    roles: tuple
    # None: the shared box station (MOUNT_X_M + .152). The tile stands closer
    # (tile_low_reach_v1): its 7 mm grip needs a shorter reach than the box
    # calibration covers, see ``TILE_STATION_M`` below.
    station_m: float | None = None
    ik_options: tuple = ()
    # (x0_m, pitch0_deg, slope_deg_per_m): preferred tool pitch as a line of the target x.
    pitch_line: tuple | None = None
    align_tol_m: float = .008


# tile_low_reach_v1 (cause and evidence: experiments/2026-10-14-act-solo-teacher/README.md).
# At the box station (arm radius 15.2 cm) a 7 mm grip target needs servo 5 above
# its 2500 pulse limit for every tool pitch (min 2545 at -55..-60 deg), so no v3
# IK exists from hover to grip. Without the box-calibrated radius envelope the
# whole hover-to-grip path is feasible at body-frame x 0.150..0.185 m (arm radius
# 10.2..13.7 cm); harness/tile_own_skill.py (T05) already uses that region
# (0.176..0.180 m, envelope off). Three further choices make it usable:
# - the grip centre is 9 mm instead of 7 mm: the 14.3 mm pad's lower end stays
#   ~2 mm above the floor (7 mm: 0.5 mm) and the pad still covers the lower 9 mm
#   of the 12 mm side;
# - the tool pitch follows the target x (steeper when closer): the servos stay
#   >= 44 pulses inside their 500..2500 limits over the whole aligned window
#   (T05's fixed -40 candidate is 8 pulses from the limit);
# - the robot stands at x = 0.172 m with +-6 mm alignment tolerance.
# The gripper, the tile and the envelope constant itself stay unchanged.
TILE_STATION_M = .172
TILE_GRIP_Z_M = .009
TILE_PITCH_LINE = (.172, -73., 750.)
TILE_ALIGN_TOL_M = .006


def cargo(kind):
    # Catalogue constants, not live measurements (sim.zone_cargo / zone_arena).
    if kind in BOX_KINDS:
        return Cargo(kind, (.034, .040, .032), .030, .024, ('west',))
    if kind == 'can':
        return Cargo(kind, (.038, .038, .050), .080, .024, ('any',))
    if kind == 'tile':
        return Cargo(kind, (.060, .040, .012), .025, TILE_GRIP_Z_M, ('west', 'east'),
                     station_m=TILE_STATION_M,
                     ik_options=(('calibrated_grasp_only', False),), pitch_line=TILE_PITCH_LINE,
                     align_tol_m=TILE_ALIGN_TOL_M)
    raise ValueError('one-carrier production cargo required')


@dataclass
class InputAudit:
    invisible_measurements: int = 0
    held_world_reads: int = 0
    blocked_hidden: int = 0
    blocked_held: int = 0
    measurements_by_phase: dict = field(default_factory=dict)

    def measure(self, phase, *, visible_n, probe_N, holding, read_relative):
        """Lazy read: hidden/held callbacks are never evaluated.

        Visibility geometry is owned by the perception boundary. This function
        is called before looking up the cargo body pose, including its yaw.
        Evaluation may read full truth in a separate output owner.
        """
        if holding:
            self.blocked_held += 1
            return None
        if probe_N <= 0 or visible_n < math.ceil(probe_N / 3):
            self.blocked_hidden += 1
            return None
        value = read_relative()
        if set(value) != {'xyz', 'yaw'} or len(value['xyz']) != 3:
            raise ValueError('relative visible-target whitelist')
        if not all(math.isfinite(x) for x in (*value['xyz'], value['yaw'])):
            raise ValueError('finite visible measurement required')
        self.measurements_by_phase[phase] = self.measurements_by_phase.get(phase, 0) + 1
        return deepcopy(value)

    def record(self):
        return {**vars(self), 'scope': 'decision input boundary only; evaluation excluded'}


class VisibilityStats:
    """Evaluation-only, time-weighted stage visibility; never selects actions."""
    def __init__(self):
        self.rows = {}
        self.previous = None
        self.blind_s = 0.
        self.max_blind_s = 0.

    def add(self, now, phase, visible):
        if self.previous is not None:
            at, stage, seen = self.previous
            dt = now-at
            if not 0 <= dt <= PERIOD_S * 1.5:
                raise ValueError('visibility requires consecutive control samples')
            row = self.rows.setdefault(stage, {'seconds': 0., 'visible_s': 0., 'max_invisible_s': 0., 'N': 0})
            row['seconds'] += dt
            row['visible_s'] += dt * seen
            row['N'] += 1
            self.blind_s = 0. if seen else self.blind_s+dt
            self.max_blind_s = max(self.max_blind_s, self.blind_s)
            # Stage-local blind runs are separate from the cross-stage maximum.
            row['_blind'] = 0. if seen else row.get('_blind', 0.)+dt
            row['max_invisible_s'] = max(row['max_invisible_s'], row['_blind'])
        self.previous = now, phase, bool(visible)

    def record(self):
        return {'max_invisible_s': self.max_blind_s, 'by_phase': {
            k: {**{a: b for a, b in v.items() if not a.startswith('_')},
                'visible_ratio': v['visible_s']/v['seconds'] if v['seconds'] else None}
            for k, v in self.rows.items()}}


def primitives():
    """Reuse the pair implementation; imports do not construct a simulator."""
    from types import SimpleNamespace
    from harness.grasp_act_contract import command
    from harness.grasp_act_visible_world import command_delta
    from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose, MOUNT_X_M
    from sim.grasp_act_teacher import IssuedArm
    from sim.grasp_act_teacher_v3 import propagate_owned
    from sim.grasp_act_port import duty_wheels
    from sim.grasp_act_gaze import slew
    from sim.grasp_act_visible_gaze import gaze_pose
    from scripts.zone_teacher import ArmSequence, FOLDED
    from sim.masterpi_geometry_v3 import PHYSICAL_V3
    return SimpleNamespace(command=command, delta=command_delta, ik=solve_grip_site_ik,
        pitch=lambda p: tool_pose(p).pitch_deg, station=MOUNT_X_M+.152,
        pad_len=PHYSICAL_V3.finger_pad_length_m,
        Sink=IssuedArm, Arm=ArmSequence, propagate=propagate_owned,
        duty=duty_wheels, gaze=gaze_pose, slew=slew, folded=FOLDED)


class SoloTeacher:
    def __init__(self, kind, role, pwm, *, profile='off', held_object_hidden_v1=False,
                 setdown_lookaround_v1=False, lookaround=None, route=None, ops=None,
                 teacher_stability='off', reach_mode='box_station_v1', rgb_lift_mode='off',
                 solo_lift_negative_probe_v1=False, solo_lift_lookback_margin_v1=False,
                 solo_carry_to_zone_v1=False, carry=None):
        if profile != PROFILE:
            raise ValueError('solo teacher is opt-in; legacy defaults are unchanged')
        if not held_object_hidden_v1:
            raise ValueError('solo_visible_only_v1 requires held_object_hidden_v1')
        if setdown_lookaround_v1 and lookaround is None:
            raise ValueError('active map look-around implementation required')
        if teacher_stability not in ('off', 'align_relook_v1'):
            raise ValueError('unknown teacher stability mode')
        if reach_mode not in ('box_station_v1', 'pad_window_v2'):
            raise ValueError('unknown solo reach mode')
        if rgb_lift_mode not in ('off', 'solo_rgb_lift_v2', 'solo_rgb_lift_v3', 'solo_lift_lookback_v1'):
            raise ValueError('unknown solo RGB lift mode')
        if solo_lift_negative_probe_v1 and (kind not in BOX_KINDS or rgb_lift_mode != 'solo_lift_lookback_v1'):
            raise ValueError('negative probe requires a box and the unchanged lookback judge')
        self.negative_probe = bool(solo_lift_negative_probe_v1)
        if solo_lift_lookback_margin_v1 and (kind not in BOX_KINDS or rgb_lift_mode != 'solo_lift_lookback_v1'):
            raise ValueError('lookback margin requires box cargo and the unchanged lookback judge')
        self.lookback_margin = bool(solo_lift_lookback_margin_v1)
        if solo_carry_to_zone_v1 and (kind not in BOX_KINDS or carry is None or
                rgb_lift_mode != 'solo_lift_lookback_v1' or solo_lift_negative_probe_v1):
            raise ValueError('zone carry requires box, RGB lookback and map controller')
        self.carry = carry if solo_carry_to_zone_v1 else None
        self.zone_advance_m = 0.
        self.zone_visible_t = None
        self.rgb_lift_mode = rgb_lift_mode
        self.teacher_stability, self.reach_mode = teacher_stability, reach_mode
        self.spec = cargo(kind)
        if role not in self.spec.roles:
            raise ValueError('explicit compatible seat token required')
        self.role, self.ops = role, ops or primitives()
        if reach_mode == 'pad_window_v2' and kind != 'tile':
            # Reuse the release teacher's physical-pad window, not the wider
            # calibrated radius envelope. The old +/-8 mm box window reaches
            # x=.1922 (radius .144), outside the calibrated minimum .145 m.
            from harness.visual_arm_v3 import MOUNT_X_M
            from sim.grasp_act_release_teacher import PAD_MID_M, PAD_TOL_M
            self.spec = replace(self.spec, station_m=MOUNT_X_M+PAD_MID_M,
                                align_tol_m=PAD_TOL_M)
        self.sink = self.ops.Sink(pwm)
        self.arm = self.ops.Arm(self.sink, self.sink.pwm)
        self.lookaround = lookaround if setdown_lookaround_v1 else None
        self.route = route
        self.phase, self.phase_t = 'start', None
        self.skill_started = None
        self.skill = 'grasp'
        self.events = []
        self.target, self.seen_t = None, None
        self.previous, self.previous_t = None, None
        self.holding = False
        self.result = None
        self.stable_t = None
        self.grasp_xyz = None
        self.low = self.high = None
        self.verify_t = None
        self.backoff_m = 0.
        self.lookback_m = 0.
        self.lookback_return_m = 0.
        self.lookback_plan = None
        self.ik_rejections = 0
        self.ik_checks = 0
        self.ik_rejection_reasons = {}
        self.aligned_ik_failures = 0
        self.align_relooks = 0
        self._reset_alignment()

    def _reset_alignment(self):
        self.align_integral = [0., 0., 0.]
        self.align_active = [False]*3
        self.align_sign = [0]*3
        self.align_flips = [0]*3
        self.align_t = self.align_best = self.align_progress_t = None

    def _begin_relook(self, now, reason):
        self.align_relooks += 1
        self.events.append({'t': now, 'alignment_recovery': reason})
        self._reset_alignment()
        self.target = self.seen_t = None
        self.aligned_ik_failures = 0
        if self.align_relooks > 2:
            self.result = 'alignment_no_progress'
            self._set('failed', now)
        else:
            self._set('relook', now)
        return self._hold(now)

    def _set(self, phase, now):
        self.events.append({'t': now, 'from': self.phase, 'to': phase})
        self.phase, self.phase_t = phase, now
        self.stable_t = None
        if phase == 'align':
            self._reset_alignment()
        if phase in ('lower', 'lookback_return', 'zone_place_view') and self.skill != 'release':
            self.skill, self.skill_started = 'release', now

    def _hold(self, now):
        return self.ops.command({'t': now, 'wheels': [0.]*4, 'duration_s': [0.]*4,
            'pwm': {str(s): self.sink.pwm[s] for s in (1, 3, 4, 5, 6)}})

    def _drive(self, now, forward=0., left=0., turn=0.):
        wheels, duration = self.ops.duty([3*forward, 3*left, .65*turn])
        if self.teacher_stability == 'align_relook_v1' and self.phase == 'align':
            # Same candidate floor as b16930dc; physical response unmeasured.
            # Fine alignment selects one axis, preserving wheel ratios.
            duration = [max(.04, d) if w else 0. for w, d in zip(wheels, duration)]
        return self.ops.command({**self._hold(now), 'wheels': wheels, 'duration_s': duration})

    def _align_drive(self, now, errors, reachable):
        # b16930dc align_relook_v1, with deadbands inside the solo cargo's
        # tighter readiness window. Route following ends before this law.
        tol = self.spec.align_tol_m
        inner = (tol*.5, tol*.5, .02)
        outer = (tol*.75, tol*.75, .04)
        merit = max(abs(e)/b for e, b in zip(errors, inner))
        if self.align_best is None or merit < self.align_best-.25:
            self.align_best, self.align_progress_t = merit, now
        elif now-self.align_progress_t >= 3.-1e-8:
            return self._begin_relook(now, 'no_visible_error_progress_3s')
        for i, error in enumerate(errors):
            if abs(error) <= inner[i]:
                self.align_active[i] = False
            elif abs(error) >= outer[i]:
                self.align_active[i] = True
            if not self.align_active[i]:
                self.align_integral[i] = 0.
        if not reachable and abs(errors[0]) > .0005:
            self.align_active[0] = True
        axis = next((i for i in (2, 1, 0) if self.align_active[i]), None)
        if axis is None:
            return self._hold(now)
        sign = 1 if errors[axis] > 0 else -1
        old = self.align_sign[axis]
        self.align_flips[axis] = self.align_flips[axis]+1 if old and sign != old else 0
        self.align_sign[axis] = sign
        if self.align_flips[axis] >= 4:
            return self._begin_relook(now, 'alternating_error_sign_4')
        if old and sign != old:
            self.align_integral[axis] = 0.
        dt = 0. if self.align_t is None else max(0., min(.2, now-self.align_t))
        self.align_t = now
        for i in range(3):
            if i != axis:
                self.align_integral[i] = 0.
        limit = (.025, .025, .03)[axis]
        self.align_integral[axis] = max(-limit, min(limit,
            self.align_integral[axis]+(.45, .45, .4)[axis]*errors[axis]*dt))
        effort = (.9, .9, .8)[axis]*errors[axis]+self.align_integral[axis]
        lo, hi = ((-.05, .08), (-.06, .06), (-.1, .1))[axis]
        drive = [0., 0., 0.]
        drive[axis] = max(lo, min(hi, effort))
        return self._drive(now, *drive)

    def _scan_gaze(self, age):
        # Stationary search only. No map goal, spawn anchor or hidden pose.
        pan = (1000, 1500, 2000, 2500, 1500, 500)[int(age/.6) % 6]
        gaze = {**self.ops.folded, 3: 500 if int(age/3.6) % 2 == 0 else 820, 4: 2500, 6: pan}
        self.sink.pwm.update(self.ops.slew(self.sink.pwm, gaze))
        self.arm.commanded.update(self.sink.pwm)

    def _relook(self, measurement, now):
        age = now-self.phase_t
        if age >= 3.6-1e-8 and measurement is not None:
            # _target received this tick's fresh visible measurement. Never
            # resume from a remembered target or a hidden world coordinate.
            self._set('align', now)
        else:
            self._scan_gaze(age)
        return self._hold(now)

    def remember_applied(self, value):
        self.previous = deepcopy(self.ops.command(value))

    def context(self, now):
        # Called from an explicit skill instruction, before a perception result.
        return {'skill': self.skill, 'object_kind': self.spec.kind, 'role': self.role,
                'skill_elapsed_s': max(0., now-self.skill_started) if self.skill_started is not None else 0.,
                'local_skill_sample': not self.negative_probe and self.phase not in
                    ('start', 'lookaround', 'complete', 'failed', 'carry_prepare', 'carry_to_zone')}

    def _target(self, measurement, now, dt):
        if self.target is not None and self.previous is not None:
            self.target['xyz'] = self.ops.propagate(self.target['xyz'], self.previous, dt)
            self.target['yaw'] = wrap(self.target['yaw']-self.ops.delta(self.previous, dt)[2])
        if self.holding:
            if measurement is not None:
                raise ValueError('held target measurement forbidden')
            self.target = None
        elif measurement is not None:
            if set(measurement) != {'xyz', 'yaw'}:
                raise ValueError('teacher accepts relative visible target only')
            self.target, self.seen_t = deepcopy(measurement), now
        if self.seen_t is not None and now-self.seen_t > MEMORY_S:
            self.target = None

    def _queue(self, pose, now, duration, settle=.1):
        self.arm.queue(pose, now, duration=duration, settle=settle)

    def _pick_geometry(self, target):
        x, y, z = target['xyz']
        options = dict(self.spec.ik_options)
        if self.spec.pitch_line is not None:
            x0, pitch0, slope = self.spec.pitch_line
            options['preferred_pitch_deg'] = max(-90., min(-50., pitch0+slope*(x-x0)))
        low = self.ops.ik((x, y, z), **options)
        pitch = self.ops.pitch(low)
        # The pad is pad_len long along the tool axis: its lowest point is below
        # the pad centre by half of that times sin(pitch). Necessary condition
        # only (finger plate and wrist clearance are not modelled here).
        if z-self.ops.pad_len/2*math.sin(math.radians(abs(pitch))) < -1e-9:
            raise ValueError('pad would reach below the floor at this grip height')
        options['preferred_pitch_deg'] = pitch
        high = self.ops.ik((x, y, .095), **options)
        descent = [self.ops.ik((x, y, .095+(z-.095)*i/8), **options) for i in range(1, 9)]
        return low, high, descent

    def _seek(self, measurement, now):
        # On lost visibility, move only the gaze from bounded command memory.
        if self.target is not None:
            gaze = self.ops.gaze(self.target['xyz'], self.sink.pwm, visible=measurement is not None)
        else:
            self._scan_gaze(now-self.skill_started)
            gaze = None
        if gaze is not None:
            self.sink.pwm.update(self.ops.slew(self.sink.pwm, gaze))
            self.arm.commanded.update(self.sink.pwm)
        if measurement is None:
            self.stable_t = None
            return self._hold(now)
        x, y, _ = self.target['xyz']
        station = self.spec.station_m or self.ops.station
        angle = 0. if self.role == 'any' else wrap(self.target['yaw']+(math.pi if self.role == 'east' else 0.))
        gx, gy = x-station*math.cos(angle), y-station*math.sin(angle)
        if self.phase == 'approach' and math.hypot(gx, gy) <= .08:
            self._set('align', now)
        if self.phase == 'approach' and self.teacher_stability == 'align_relook_v1':
            return self._route_drive(now, gx, gy, angle, x, y, station)
        reachable = False
        self.ik_checks += 1
        try:
            self._pick_geometry(self.target)
            reachable = True
        except ValueError as exc:
            self.ik_rejections += 1
            reason = str(exc)
            self.ik_rejection_reasons[reason] = self.ik_rejection_reasons.get(reason, 0)+1
        aligned = math.hypot(gx, gy) <= self.spec.align_tol_m and abs(angle) <= .04
        self.aligned_ik_failures = self.aligned_ik_failures+1 if aligned and not reachable else 0
        if self.aligned_ik_failures >= 3:
            self.result = 'visible_target_ik_unreachable'
            self._set('failed', now)
            return self._hold(now)
        if aligned and reachable:
            self.stable_t = now if self.stable_t is None else self.stable_t
            if now-self.stable_t >= .3-1e-8:
                # Freeze ONLY the currently visible target for the canonical
                # last segment. No geometry is refreshed during grasp/lift.
                self.grasp_xyz = tuple(self.target['xyz'])
                self.low, self.high, self.descent = self._pick_geometry(self.target)
                self._queue({**self.high, 1: 2000}, now, .8)
                self._set('hover', now)
            return self._hold(now)
        self.stable_t = None
        if self.teacher_stability == 'align_relook_v1' and self.phase == 'align':
            return self._align_drive(now, (gx, gy, angle), reachable)
        return self._route_drive(now, gx, gy, angle, x, y, station)

    def _route_drive(self, now, gx, gy, angle, x, y, station):
        if self.route is not None:
            # Route callback sees only a body-frame goal + already visible data.
            forward, left, turn = self.route((gx, gy, angle), self.context(now))
        else:
            forward, left, turn = .9*(x-station), .9*y, .8*angle
        clip = lambda v, lo, hi: max(lo, min(hi, v))
        return self._drive(now, clip(forward, -.05, .08), clip(left, -.06, .06), clip(turn, -.1, .1))

    def step(self, now, *, measurement=None, rgb_holding='unknown', own_rgb=None,
             place_visible=False):
        if self.previous_t is not None and not 0 < now-self.previous_t <= .15+1e-8:
            raise ValueError('strictly increasing 10 Hz command clock required')
        dt = 0. if self.previous_t is None else now-self.previous_t
        if self.skill_started is None:
            self.skill_started = now
            self._queue({**self.ops.folded, 6: self.sink.pwm[6]}, now, .5)
            self._set('fold', now)
        if self.lookaround is not None and self.previous is not None:
            self.lookaround.issue(self.previous, dt)
        if self.phase == 'backoff' and self.previous is not None:
            self.backoff_m -= self.ops.delta(self.previous, dt)[0]
        if self.phase == 'lookback' and self.previous is not None:
            self.lookback_m -= self.ops.delta(self.previous, dt)[0]
        if self.phase == 'lookback_return' and self.previous is not None:
            self.lookback_return_m += self.ops.delta(self.previous, dt)[0]
        if self.phase == 'zone_place_advance' and self.previous is not None:
            self.zone_advance_m += self.ops.delta(self.previous, dt)[0]
        self._target(measurement, now, dt)
        idle = self.arm.tick(now)
        value = self._hold(now)
        if self.result is not None:
            pass
        elif now-self.phase_t > (180 if self.phase == 'carry_to_zone' else 60):
            self.result = 'phase_timeout'
            self._set('failed', now)
        elif self.phase == 'fold' and idle:
            self._set('approach', now)
        elif self.phase in ('approach', 'align'):
            value = self._seek(measurement, now)
        elif self.phase == 'relook':
            value = self._relook(measurement, now)
        elif self.phase == 'hover' and idle:
            for pose in self.descent:
                self._queue(pose, now, .15, .04)
            self._set('descent', now)
        elif self.phase == 'descent' and idle:
            self.holding = True  # conservative: hide from close, including verification
            self.target = None
            self._queue({1: 1500}, now, .8, .3)
            self._set('close', now)
        elif self.phase == 'close' and idle:
            if self.negative_probe:
                # Diagnostic intervention only: release at the pickup pose,
                # BEFORE raising. Keep the held-input boundary conservative.
                self._queue({1: 2000}, now, .5, .3)
                self._set('negative_probe_open', now)
            else:
                self._queue(self.high, now, 1.2, .3)
                self._set('lift', now)
        elif self.phase == 'negative_probe_open' and idle:
            self._queue(self.high, now, 1.2, .3)
            self._set('lift', now)
        elif self.phase == 'lift' and idle:
            self.verify_t = None
            self._set('lift_settle' if self.rgb_lift_mode == 'solo_lift_lookback_v1' else 'verify_lift', now)
        elif self.phase == 'lift_settle' and now-self.phase_t >= 3.2-1e-8:
            # Hold the existing upright lift for the unchanged 3 s evaluation
            # window, then inspect the original site. No evaluation enters here.
            from sim.grasp_act_solo_lookback import plan_lookback
            if self.lookback_margin:
                from sim.grasp_act_solo_lookback_margin import plan_with_margin as plan_lookback
            try:
                self.lookback_plan = plan_lookback(self.spec.kind,
                    {1: 1500, **self.low}, self.sink.pwm)
            except ValueError:
                self.result = 'lookback_geometry_unavailable'
                self._set('failed', now)
            else:
                self._queue(self.lookback_plan['pwm'], now, .8, .3)
                self._set('lookback_pose', now)
        elif self.phase == 'lookback_pose' and idle:
            self._set('lookback', now)
        elif self.phase == 'lookback':
            if self.lookback_m < self.lookback_plan['backoff_m']:
                value = self._drive(now, -.05)
            else:
                self._set('lookback_settle', now)
        elif self.phase == 'lookback_settle' and now-self.phase_t >= .5-1e-8:
            self._set('verify_lift', now)
        elif self.phase in ('verify_lift', 'hold'):
            # RGB-only recognizer + completed own close/raise commands.
            if rgb_holding not in ('yes', 'no', 'unknown'):
                raise ValueError('own RGB evidence must be yes/no/unknown')
            if self.negative_probe and rgb_holding == 'yes':
                # Preserve the verdict as a false positive; never act out a
                # successful set-down or travel back with an empty gripper.
                self.result = 'negative_probe_false_positive'
                self._set('failed', now)
            elif rgb_holding == 'yes':
                self.verify_t = now if self.verify_t is None else self.verify_t
                if self.phase == 'verify_lift' and now-self.verify_t >= 1.-1e-8:
                    self._set('hold', now)
                elif self.phase == 'hold' and now-self.phase_t >= 3.-1e-8:
                    if self.carry is not None:
                        from harness.visual_arm_v3 import forward_grip
                        self.carry.start(now, forward_grip({1: 1500, **self.low})[:2])
                        self._queue(self.high, now, .8, .2)
                        self._set('carry_prepare', now)
                    elif self.rgb_lift_mode == 'solo_lift_lookback_v1':
                        self._set('lookback_return', now)
                    else:
                        self._queue(self.low, now, .8, .2)
                        self._set('lower', now)
            else:
                self.verify_t = None
                # v2/v3 need completion + a 3 s RGB sample + the existing 1 s
                # continuous yes window. Timeout still fails closed.
                verify_limit = 5. if self.rgb_lift_mode != 'off' else 3.
                if self.phase == 'hold' or now-self.phase_t >= verify_limit:
                    # No hidden truth recovery or silent scripted retry.
                    self.result = 'rgb_lift_unconfirmed' if self.phase == 'verify_lift' else 'rgb_hold_lost'
                    self._set('failed', now)
        elif self.phase == 'carry_prepare' and idle:
            self._set('carry_to_zone', now)
        elif self.phase == 'carry_to_zone':
            drive, arrived, failure = self.carry.step(now)
            if failure:
                self.result = failure
                self._set('failed', now)
            elif arrived:
                self._set('zone_place_view', now)
            else:
                value = self._drive(now, *drive)
        elif self.phase == 'zone_place_view':
            self.zone_visible_t = (now if self.zone_visible_t is None else self.zone_visible_t) if place_visible else None
            if self.zone_visible_t is not None and now-self.zone_visible_t >= .3-1e-8:
                self.zone_advance_m = 0.
                self._set('zone_place_advance', now)
            elif now-self.phase_t >= 3.:
                self.result = 'destination_floor_not_visible'
                self._set('failed', now)
        elif self.phase == 'zone_place_advance':
            if self.zone_advance_m < self.carry.advance_m:
                value = self._drive(now, .05)
            else:
                # Flat authored zone floor, same body-relative low arm pose.
                # No held cargo world position or measured arm state is read.
                self._queue(self.low, now, .8, .2)
                self._set('lower', now)
        elif self.phase == 'lookback_return':
            if self.lookback_return_m < self.lookback_m:
                value = self._drive(now, .05)
            else:
                self._queue(self.high, now, .8, .2)
                self._queue(self.low, now, .8, .2)
                self._set('lower', now)
        elif self.phase == 'lower' and idle:
            self._queue({1: 2000}, now, .5, .2)
            self._set('open', now)
        elif self.phase == 'open' and idle:
            self.holding = False
            self._queue(self.high, now, .8)
            self._queue(self.ops.folded, now, .8)
            self._set('retract', now)
        elif self.phase == 'retract' and idle:
            self.backoff_m = 0.
            self._set('backoff', now)
        elif self.phase == 'backoff':
            if self.backoff_m < .15:
                value = self._drive(now, -.05)
            elif self.lookaround is not None:
                self.lookaround.start(now, self.sink.pwm[6])
                self._set('lookaround', now)
            else:
                self.result = 'command_complete'
                self._set('complete', now)
        elif self.phase == 'lookaround':
            value, done = self.lookaround.step(now, self.sink.pwm, own_rgb)
            self.sink.pwm.update({int(s): p for s, p in value['pwm'].items()})
            self.arm.commanded.update(self.sink.pwm)
            if done:
                self.result = 'command_complete'
                self._set('complete', now)
        # A queued arm update takes effect in the returned full PWM snapshot.
        value['pwm'] = {str(s): self.sink.pwm[s] for s in (1, 3, 4, 5, 6)}
        self.previous, self.previous_t = deepcopy(value), now
        return value, self.result == 'command_complete'

    def diagnostic(self):
        return {'profile': PROFILE, 'phase': self.phase, 'command_result': self.result,
            'holding_belief': self.holding, 'ik_rejections': self.ik_rejections,
            'ik_checks': self.ik_checks, 'ik_rejection_reasons': dict(self.ik_rejection_reasons),
            'teacher_stability': self.teacher_stability, 'reach_mode': self.reach_mode,
            'rgb_lift_mode': self.rgb_lift_mode,
            'negative_probe': self.negative_probe,
            'solo_lift_negative_probe_v1': self.negative_probe,
            'solo_lift_lookback_margin_v1': self.lookback_margin,
            'solo_carry_to_zone_v1': self.carry is not None,
            'carry': self.carry.record() if self.carry is not None else None,
            'gate_eligible': not self.negative_probe and self.carry is None,
            'lookback_commanded_backoff_m': self.lookback_m,
            'lookback_commanded_return_m': self.lookback_return_m,
            'lookback_plan': self.lookback_plan,
            'alignment_relooks': self.align_relooks,
            'events': self.events, 'held_object_hidden_v1': True,
            'held_interval': 'close command through completed open command',
            'setdown_lookaround_v1': self.lookaround is not None,
            'student_execution': False, 'physical_success': None,
            'done_semantics': 'own command sequence and RGB confirmation only; separate evaluator scores physics'}
