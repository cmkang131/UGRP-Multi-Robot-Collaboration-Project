"""pairact hybrid carry (default OFF): learned near field + code carry + learned place.

The P5 student (``harness/pairact_student_eval.py``) drives approach -> alignment -> READY ->
grasp -> 3 s joint hold. When both robots' own done flags switch the student to the release
segment (the worker's ``release_instruction`` event, own signals only), this module takes over
the carry and door passage with a self-sensor cooperative drive, and hands control back to the
student at the set-down start (``lower``). Interfaces I1-I11 of
``experiments/2026-10-21-pairact-r1/HYBRID_SWITCH_RULE.md`` (dsh/pairact-r1-armN):

  I1 HybridSegmentArbiter       per robot, segment state machine, own signals only
  I2 PairCarrySync              harness/pair_carry_sync.py, tasks 'carry' and 'place'
  I3 SelfSensorPairCarry        leader (navigator) plans a virtual beam pose, both track it
  I4 FormationMessage           leader -> follower: virtual beam pose/velocity, seq, observed_at_s
  I5 PoseTrustGate              own dead-reckoning uncertainty; fail closed (SELF_POSE_UNCERTAIN)
  I6 NavZoneSensor / MapRoute   'nav' (own camera zone detection, nav r5/v5 detector) or 'map'
  I7 shadow                     worker op 'shadow' (dsh/pairact-p5-student-hybrid): the student
                                watches, its own issued history receives the real code commands
  I8 hand-back                  arrived (own judgement) + place GO -> STUDENT_PLACE
  I9 runner flag                scripts/run_grasp_act_teacher.py hybrid_carry=<config> (default None)
  I10 audit                     HybridRun.summary(): code_segment_s, executed ratio, events, 0 GT
  I11 import audit              tests/test_hybrid_carry.py (no simulator truth/evaluator import)

Inputs of the code segment: own camera JPEG, own applied commands (odometry), partner messages.
No GT pose, contact, evaluator value, teacher or partner raw pose is accepted by any method.

Carry modes:
  'nav' (default): no static map. The navigator robot's own camera detects zone B
        (GpuCalibZoneDetector of the pinned nav tree, ``NAV_SHA``) and projects the component
        bottom onto the floor (``ground_point_robot``). The door is passed by aiming at the zone
        component centre as in nav r5 (no separate door detector exists [확인 필요]).
  'map': static door/zone coordinates (pair_carry_teacher_warp.carry_route) + own odometry from
        the episode start pose. REFUSED until the owner (창민) approves static-map use for pair
        carry: ``MAP_MODE_APPROVAL_SHA256`` must be set in code to the sha256 of the committed
        approval record.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import subprocess
from pathlib import Path

from harness.pair_carry_sync import PairCarrySync
from harness.pair_carry_teacher_warp import (Params, body_command, carry_route, compose, inverse, make_command,
                                             relative, wrap)

MODE = 'pairact_r1_hybrid_carry_v2'   # v2: loaded-odometry calibration (gain + latency + bias) with fit provenance
CARRY_MODES = ('nav', 'map')
DEFAULT_CARRY_MODE = 'nav'
# Nav detector tree: dsh/nav-v5-recal (contains nav r5 e11efbeb9 and the v5 hue profiles).
NAV_SHA = 'ceacd474b9e03110c1b35c0cd0fc2cca40594ec9'
# Static-map use for pair carry is not approved (2026-10-21). Set to the sha256 of the committed
# approval record only after the owner's decision; until then 'map' raises MapModeNotApproved.
MAP_MODE_APPROVAL_SHA256 = None

SEGMENTS = ('STUDENT_GRASP', 'CARRY_SYNC', 'CODE_CARRY', 'PLACE_SYNC', 'STUDENT_PLACE', 'DONE', 'ABORT')
_NEXT = {'STUDENT_GRASP': ('CARRY_SYNC',), 'CARRY_SYNC': ('CODE_CARRY',), 'CODE_CARRY': ('PLACE_SYNC',),
         'PLACE_SYNC': ('STUDENT_PLACE',), 'STUDENT_PLACE': ('DONE',), 'DONE': (), 'ABORT': ()}
STUDENT_SEGMENTS = ('STUDENT_GRASP', 'STUDENT_PLACE')

CONFIG_KEYS = {'mode', 'carry_mode', 'navigator', 'calibration', 'calibration_provenance', 'formation', 'limits',
               'nav', 'map', 'shadow_predict'}
GAIN_KEYS = ('forward_m_per_pct_s', 'lateral_m_per_pct_s', 'yaw_deg_per_pct_s')
BIAS_KEYS = ('forward_bias_m_per_s', 'lateral_bias_m_per_s', 'yaw_bias_deg_per_s')
CALIBRATION_KEYS = set(GAIN_KEYS) | set(BIAS_KEYS) | {'latency_ticks'}
MAX_LATENCY_TICKS = 10
# Loaded-state odometry fit (root scripts/fit_loaded_odom.py -> scripts/make_hybrid_config.py). The calibration
# block and the two sigma growth rates may come ONLY from that tool: the config carries the tool's
# values_sha256 and validate_config recomputes it, so a hand-filled or edited number is refused.
FIT_SCHEMA = 'ugrp.pairact.loaded_odom_fit.v1'
PROVENANCE_KEYS = {'schema', 'fit_sha256', 'values_sha256', 'fit_quality', 'seeds', 'sources', 'tool'}
FIT_QUALITIES = ('per_tick', 'aggregate_coarse')
SIGMA_FIT_KEYS = ('sigma_xy_per_m', 'sigma_yaw_per_rad')
# Fit data may come only from pilot (8343000-8343039) and P2 smoke worlds 1/11/17 of the r13 cases
# (seed = 8420000 + world). Never training, validation or held-out seeds.
FIT_SEEDS = frozenset(range(8343000, 8343040)) | frozenset({8420001, 8420011, 8420017})
PURPOSES = ('hybrid_n', 'teacher_smoke')
FORMATION_KEYS = {'beam_half_m', 'station_m'}
LIMIT_KEYS = {'carry_budget_s', 'v_max', 'w_max', 'hold_settle_s', 'settle_s', 'message_ttl_s',
              'stretch_pause_m', 'stretch_fail_m', 'stretch_fail_s', 'sigma_xy_max_m', 'sigma_yaw_max_deg',
              'sigma_xy_per_m', 'sigma_yaw_per_rad', 'acquire_budget_s', 'reobserve_wait_s', 'heading_tol_deg'}
NAV_KEYS = {'source', 'sha', 'profile', 'hfov_deg', 'bearing_convention', 'arm_ground_m', 'advance_m',
            'confirm_ticks', 'door_detector'}
MAP_KEYS = {'approval'}
ROLE_OFFSET_SIGN = {'teal': -1., 'blue': 1.}   # teal end at -x of the beam frame, blue at +x
PCT = 100.                                      # normalized wheel duty -> percent (calibration unit)
DT = .1                                         # runner control period (SIM s)


class MapModeNotApproved(PermissionError):
    pass


def _positive(d, keys, what):
    for k in keys:
        v = d[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError(f'{what}.{k} must be a positive number (measured value, no default)')


def calibration_values_sha256(calibration, limits):
    """Canonical hash of the fitted numbers (same function in root scripts/make_hybrid_config.py)."""
    payload = {'calibration': {k: calibration[k] for k in sorted(CALIBRATION_KEYS)},
               'sigma': {k: limits[k] for k in SIGMA_FIT_KEYS}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _hex64(v):
    return isinstance(v, str) and len(v) == 64 and all(c in '0123456789abcdef' for c in v)


def validate_calibration(cal):
    for k in GAIN_KEYS:
        v = cal[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError(f'calibration.{k} must be a positive fitted number')
    for k in BIAS_KEYS:
        v = cal[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f'calibration.{k} must be a finite fitted number')
    lat = cal['latency_ticks']
    if type(lat) is not int or not 0 <= lat <= MAX_LATENCY_TICKS:
        raise ValueError(f'calibration.latency_ticks must be an int in [0, {MAX_LATENCY_TICKS}]')


def validate_provenance(cfg, purpose):
    """The [확인 필요] refusal of the template is lifted only by the fit tool's output."""
    prov = cfg['calibration_provenance']
    if not isinstance(prov, dict) or set(prov) != PROVENANCE_KEYS or prov['schema'] != FIT_SCHEMA:
        raise ValueError('calibration_provenance must be the fit tool block ' + str(sorted(PROVENANCE_KEYS)))
    if not _hex64(prov['fit_sha256']) or not _hex64(prov['values_sha256']):
        raise ValueError('calibration_provenance needs the fit file sha256 and the values sha256')
    if prov['values_sha256'] != calibration_values_sha256(cfg['calibration'], cfg['limits']):
        raise ValueError('calibration/sigma numbers differ from the fit tool output (values_sha256); '
                         'regenerate with scripts/make_hybrid_config.py, never edit by hand')
    if prov['fit_quality'] not in FIT_QUALITIES:
        raise ValueError(f'unknown fit quality {prov["fit_quality"]!r}')
    if purpose == 'hybrid_n' and prov['fit_quality'] != 'per_tick':
        raise ValueError('hybrid_n (student) runs need a per_tick loaded-odometry fit; aggregate_coarse is '
                         'allowed only for the teacher near-field smoke')
    seeds = prov['seeds']
    if (not isinstance(seeds, list) or not seeds or any(type(x) is not int for x in seeds)
            or not set(seeds) <= FIT_SEEDS):
        raise ValueError('fit seeds must be pilot 8343000-8343039 / smoke 8420001,8420011,8420017 only')


def validate_config(cfg, *, approval_root=None, purpose='hybrid_n'):
    """Exact hybrid config. Every number is owner-supplied or fit-tool output; nothing is defaulted silently."""
    if purpose not in PURPOSES:
        raise ValueError(f'unknown hybrid purpose {purpose!r}')
    if not isinstance(cfg, dict) or set(cfg) != CONFIG_KEYS or cfg['mode'] != MODE:
        raise ValueError('hybrid carry config must be exactly ' + str(sorted(CONFIG_KEYS)))
    if cfg['carry_mode'] not in CARRY_MODES:
        raise ValueError(f'unknown carry mode {cfg["carry_mode"]!r}')
    if cfg['navigator'] not in ROLE_OFFSET_SIGN:
        raise ValueError('navigator is a beam-end role (teal/blue)')
    if type(cfg['shadow_predict']) is not bool:
        raise ValueError('shadow_predict must be a bool')
    if purpose == 'teacher_smoke' and cfg['shadow_predict']:
        raise ValueError('teacher near-field smoke has no student worker: shadow_predict must be false')
    for key, keys in (('calibration', CALIBRATION_KEYS), ('formation', FORMATION_KEYS), ('limits', LIMIT_KEYS)):
        if not isinstance(cfg[key], dict) or set(cfg[key]) != keys:
            raise ValueError(f'{key} must be exactly {sorted(keys)}')
        if key == 'calibration':
            validate_calibration(cfg[key])
        else:
            _positive(cfg[key], keys, key)
    validate_provenance(cfg, purpose)
    if cfg['carry_mode'] == 'nav':
        nav = cfg['nav']
        if not isinstance(nav, dict) or set(nav) != NAV_KEYS or cfg['map'] is not None:
            raise ValueError('nav mode needs exactly the nav block and map=null')
        if nav['sha'] != NAV_SHA:
            raise ValueError(f'nav detector tree must be pinned {NAV_SHA}')
        _positive(nav, ('hfov_deg', 'arm_ground_m', 'advance_m', 'confirm_ticks'), 'nav')
        if nav['door_detector'] is not None:
            raise NotImplementedError('no own-camera door detector is pinned yet; door passage follows the zone '
                                      'centre (nav r5). [확인 필요]')
    else:
        require_map_approval(cfg['map'], approval_root=approval_root)
        if cfg['nav'] is not None:
            raise ValueError('map mode needs nav=null')
    return cfg


def require_map_approval(block, *, approval_root=None):
    """'map' (static door/zone coordinates) needs the owner's approval pinned in code."""
    if MAP_MODE_APPROVAL_SHA256 is None:
        raise MapModeNotApproved('carry_mode "map" uses static map coordinates; refused until the owner (창민) '
                                 'approves static-map use for pair carry (MAP_MODE_APPROVAL_SHA256 is None)')
    if not isinstance(block, dict) or set(block) != MAP_KEYS:
        raise ValueError('map block must be exactly {"approval": <committed record path>}')
    path = Path(block['approval'])
    if approval_root is not None and not path.is_absolute():
        path = Path(approval_root) / path
    if hashlib.sha256(path.read_bytes()).hexdigest() != MAP_MODE_APPROVAL_SHA256:
        raise MapModeNotApproved('map approval record differs from the pinned MAP_MODE_APPROVAL_SHA256')
    return True


# ------------------------------------------------------------------ geometry / odometry

def role_offset(role, formation):
    """Robot pose in the beam frame (beam centre origin, x along teal -> blue)."""
    sign = ROLE_OFFSET_SIGN[role]
    d = formation['beam_half_m'] + formation['station_m']
    return (sign*d, 0., 0. if sign < 0 else math.pi)


def wheel_body(command):
    """Own issued command -> body effort in percent-seconds (forward, left, turn).

    Inverse of grasp_act_contract.wheel_mix (f-l-t, f+l+t, f+l-t, f-l+t)."""
    w = [float(v)*PCT*float(dt) for v, dt in zip(command['wheels'], command['duration_s'])]
    if len(w) != 4:
        raise ValueError('four own wheel pulses required')
    return sum(w)/4., (-w[0] + w[1] + w[2] - w[3])/4., (-w[0] + w[1] - w[2] + w[3])/4.


class OwnOdometry:
    """Dead reckoning from the robot's OWN applied commands (fitted loaded-state calibration).

    v2: the body moves ``latency_ticks`` control ticks after the command is issued, and a moving
    tick (non-zero delayed command) adds the fitted per-axis bias. Both come from the fit tool."""

    def __init__(self, calibration, *, sigma_xy_per_m, sigma_yaw_per_rad, pose=(0., 0., 0.)):
        self.cal = dict(calibration)
        self.pose = tuple(pose)
        self.k_xy, self.k_yaw = float(sigma_xy_per_m), float(sigma_yaw_per_rad)
        self.sigma_xy = self.sigma_yaw = 0.
        self.distance_m = self.turn_rad = 0.
        self.pending = [(0., 0., 0.)]*int(self.cal.get('latency_ticks', 0))

    def step(self, command):
        self.pending.append(wheel_body(command))
        f, l, t = self.pending.pop(0)
        dx, dy = f*self.cal['forward_m_per_pct_s'], l*self.cal['lateral_m_per_pct_s']
        dth = math.radians(t*self.cal['yaw_deg_per_pct_s'])
        if f or l or t:
            dx += self.cal.get('forward_bias_m_per_s', 0.)*DT
            dy += self.cal.get('lateral_bias_m_per_s', 0.)*DT
            dth += math.radians(self.cal.get('yaw_bias_deg_per_s', 0.)*DT)
        self.pose = compose(self.pose, (dx, dy, dth))
        ds = math.hypot(dx, dy)
        self.distance_m += ds; self.turn_rad += abs(dth)
        self.sigma_xy += self.k_xy*ds + .5*ds*self.sigma_yaw
        self.sigma_yaw += self.k_yaw*abs(dth) + self.k_xy*ds
        return self.pose


class PoseTrustGate:
    """I5: own dead-reckoning uncertainty limit. No re-anchoring source exists in the code
    segment (no map, no GT), so exceeding the limit fails closed."""

    def __init__(self, limits):
        self.xy_max, self.yaw_max = limits['sigma_xy_max_m'], math.radians(limits['sigma_yaw_max_deg'])

    def check(self, odometry):
        if odometry.sigma_xy > self.xy_max or odometry.sigma_yaw > self.yaw_max:
            return 'SELF_POSE_UNCERTAIN'
        return None


# ------------------------------------------------------------------ I6 sensing

def load_nav_module(source, sha=NAV_SHA, *, git=subprocess.check_output):
    """Import harness/e2ewarp_selfnav.py from the pinned nav tree (no simulator import)."""
    head = git(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != sha:
        raise ValueError(f'nav tree {source} at {head} != pinned {sha}')
    if git(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('nav tree must be clean')
    path = Path(source) / 'harness' / 'e2ewarp_selfnav.py'
    spec = importlib.util.spec_from_file_location('_hybrid_nav_selfnav', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NavZoneSensor:
    """Own camera -> zone B point in the robot frame (x forward, y left), or None.

    detector(jpeg) -> [{'kind': 'zone_B', 'bbox': (l, t, r, b), 'bearing_deg', ...}] and
    project(u, v) -> (x, y) | None are the pinned nav tree's GpuCalibZoneDetector and
    ground_point_robot. Bearing sign follows the detector convention; the floor point is used
    for direction and range, so the convention only matters for the log."""

    def __init__(self, detector, project):
        self.detector, self.project = detector, project

    @classmethod
    def from_config(cls, nav):
        m = load_nav_module(nav['source'], nav['sha'])
        detector = m.GpuCalibZoneDetector(profile=nav['profile'], hfov_deg=nav['hfov_deg'],
                                          bearing_convention=nav['bearing_convention'])
        return cls(detector, m.ground_point_robot)

    def __call__(self, jpeg):
        found = [d for d in self.detector(jpeg) if d.get('kind') == 'zone_B']
        if not found:
            return None
        left, top, right, bottom = found[0]['bbox']
        point = self.project((left + right - 1)/2., bottom - 1)
        if point is None:
            return None
        return dict(point=(float(point[0]), float(point[1])), detection=found[0])


# ------------------------------------------------------------------ I4 messages

class MessageBus:
    """In-process leader -> follower channel with seq and observed_at_s (no delay model)."""

    def __init__(self):
        self.last, self.seq, self.log = None, 0, []

    def send(self, sender, now, payload, plan_version=1):
        self.seq += 1
        msg = dict(sender=sender, seq=self.seq, observed_at_s=float(now), plan_version=plan_version, **payload)
        self.last = msg
        self.log.append({k: msg[k] for k in ('sender', 'seq', 'observed_at_s', 'phase')})
        return msg

    def receive(self, now, ttl):
        if self.last is None or now - self.last['observed_at_s'] > ttl + 1e-9:
            return None
        return dict(self.last)


# ------------------------------------------------------------------ I3 leader planner

class VirtualBeamPlanner:
    """Leader side: virtual beam pose V in the common handover beam frame B0.

    nav: carry_hold -> acquire (rotate V in place until the zone is confirmed) -> approach
    (turn the navigator's forward to the zone point, then advance; arm when the zone bottom is
    within arm_ground_m, then advance advance_m along the armed direction) -> zone_settle.
    map: carry_hold -> route waypoints (carry_route) -> zone_settle."""

    def __init__(self, cfg, nav_offset, *, route=None):
        self.cfg, self.lim = cfg, cfg['limits']
        self.nav_offset = nav_offset
        self.V, self.vel = (0., 0., 0.), (0., 0., 0.)
        self.phase, self.phase_t, self.t0 = 'carry_hold', None, None
        self.zone, self.seen, self.last_seen_t = None, 0, None
        self.armed = None
        self.route, self.route_i = list(route or ()), 0
        self.acquire_turn = 0.
        self.outcome = None
        self.events = []

    def _set(self, phase, now):
        self.events.append(dict(t=now, event='phase', frm=self.phase, to=phase))
        self.phase, self.phase_t = phase, now

    def _move_to(self, target, dt):
        v, w = self.lim['v_max'], self.lim['w_max']
        dx, dy = target[0] - self.V[0], target[1] - self.V[1]
        dist, dyaw = math.hypot(dx, dy), wrap(target[2] - self.V[2])
        step = min(dist, v*dt)
        vx, vy = (dx/dist*step/dt, dy/dist*step/dt) if dist > 1e-9 else (0., 0.)
        wz = max(-w, min(w, dyaw/dt))
        self.vel = (vx, vy, wz)
        self.V = (self.V[0] + vx*dt, self.V[1] + vy*dt, wrap(self.V[2] + wz*dt))
        return dist < 1e-3 and abs(dyaw) < math.radians(.5)

    def nav_pose(self):
        return compose(self.V, self.nav_offset)

    def observe(self, now, zone_point, nav_pose_est):
        """zone_point: leader own-frame floor point (NavZoneSensor) or None."""
        if zone_point is None:
            self.seen = 0
            return
        self.seen += 1
        self.last_seen_t = now
        self.zone = compose(nav_pose_est, (zone_point['point'][0], zone_point['point'][1], 0.))[:2]
        self.zone_range = math.hypot(*zone_point['point'])

    def step(self, now, dt):
        lim = self.lim
        if self.t0 is None:
            self.t0, self.phase_t = now, now
        self.vel = (0., 0., 0.)
        if self.outcome is not None:
            return self.outcome
        if now - self.t0 > lim['carry_budget_s']:
            self.outcome = 'abort:code_carry_timeout'
            return self.outcome
        if self.phase == 'carry_hold':
            if now - self.phase_t >= lim['hold_settle_s'] - 1e-9:
                self._set('route' if self.cfg['carry_mode'] == 'map' else 'acquire', now)
        elif self.phase == 'acquire':
            if self.zone is not None and self.seen >= self.cfg['nav']['confirm_ticks']:
                self._set('approach', now)
            elif self.acquire_turn >= 2*math.pi or now - self.phase_t > lim['acquire_budget_s']:
                self.outcome = 'abort:zone_not_found'
            else:
                w = lim['w_max']
                self.vel = (0., 0., w)
                self.V = (self.V[0], self.V[1], wrap(self.V[2] + w*dt))
                self.acquire_turn += w*dt
        elif self.phase == 'approach':
            if self.last_seen_t is None or now - self.last_seen_t > lim['reobserve_wait_s']:
                if self.armed is None and self.last_seen_t is not None and now - self.last_seen_t > 2*lim['reobserve_wait_s']:
                    self.outcome = 'abort:zone_lost'
                    return self.outcome
                if self.armed is None:
                    return None            # hold V and wait for a fresh detection
            nav = self.nav_pose()
            if self.armed is None:
                bearing = math.atan2(self.zone[1] - nav[1], self.zone[0] - nav[0])
                yaw = wrap(bearing - self.nav_offset[2])
                if abs(wrap(yaw - self.V[2])) > math.radians(lim['heading_tol_deg']):
                    self._move_to((self.V[0], self.V[1], yaw), dt)
                else:
                    u = (math.cos(bearing), math.sin(bearing))
                    self._move_to((self.V[0] + u[0], self.V[1] + u[1], yaw), dt)
                    if self.last_seen_t == now and self.zone_range <= self.cfg['nav']['arm_ground_m']:
                        self.armed = dict(t=now, origin=self.V[:2], u=u, yaw=yaw)
                        self.events.append(dict(t=now, event='armed', range_m=self.zone_range))
            else:
                a = self.armed
                done = (self.V[0] - a['origin'][0])*a['u'][0] + (self.V[1] - a['origin'][1])*a['u'][1]
                if done >= self.cfg['nav']['advance_m'] - 1e-6:
                    self._set('zone_settle', now)
                else:
                    left = self.cfg['nav']['advance_m'] - done
                    self._move_to((self.V[0] + a['u'][0]*left, self.V[1] + a['u'][1]*left, a['yaw']), dt)
        elif self.phase == 'route':
            if self.route_i >= len(self.route):
                self._set('zone_settle', now)
            else:
                tag, target = self.route[self.route_i]
                if self._move_to(target, dt):
                    self.events.append(dict(t=now, event='waypoint', tag=tag))
                    self.route_i += 1
        elif self.phase == 'zone_settle':
            if now - self.phase_t >= lim['settle_s'] - 1e-9:
                self.outcome = 'arrived'
        return self.outcome


# ------------------------------------------------------------------ I3 per-robot tracker

class FormationTracker:
    """Both robots: track compose(V, own offset) from the own odometry estimate."""

    def __init__(self, robot_id, role, cfg, odometry, *, wheel_fn=None):
        self.robot_id, self.role, self.cfg = robot_id, role, cfg
        self.offset = role_offset(role, cfg['formation'])
        self.odom = odometry
        self.base = None            # own odometry pose at handover (B0 = compose(base, inverse(offset)))
        self.wheel_fn = wheel_fn
        self.params = Params()

    def start(self):
        self.base = self.odom.pose

    def pose_b0(self):
        """Own pose in the handover beam frame B0."""
        return compose(self.offset, relative(self.base, self.odom.pose))

    def beam_estimate(self):
        return compose(self.pose_b0(), inverse(self.offset))

    def command(self, now, V, vel, pwm, *, hold=False):
        if hold:
            return make_command(now, pwm, (0., 0., 0.), params=self.params, wheel_fn=self.wheel_fn)
        target = compose(V, self.offset)
        rx, ry = target[0] - V[0], target[1] - V[1]
        ff = (vel[0] - vel[2]*ry, vel[1] + vel[2]*rx, vel[2])
        drive = body_command(self.pose_b0(), target, ff, params=self.params)
        return make_command(now, pwm, drive, params=self.params, wheel_fn=self.wheel_fn)


# ------------------------------------------------------------------ I1 arbiter

class HybridSegmentArbiter:
    def __init__(self, robot_id):
        self.robot_id, self.segment, self.events = robot_id, 'STUDENT_GRASP', []

    def to(self, segment, now, reason):
        if segment == 'ABORT':
            if self.segment in ('DONE', 'ABORT'):
                return
        elif segment not in _NEXT[self.segment]:
            raise ValueError(f'{self.robot_id}: illegal hybrid transition {self.segment} -> {segment}')
        self.events.append(dict(t=now, robot_id=self.robot_id, frm=self.segment, to=segment, reason=reason))
        self.segment = segment

    @property
    def student_controls(self):
        return self.segment in STUDENT_SEGMENTS


# ------------------------------------------------------------------ pair run

class HybridRun:
    """One episode. The runner calls, every tick (one robot frame each):

      student_controls()                     -> bool (both arbiters agree)
      after_student_tick(now, issued, applied)  student segments: watch the release switch, odometry
      code_tick(now, jpegs)                  code segments: {rid: command} (also odometry, sync)
      summary()                              I10 audit fields
    """

    def __init__(self, cfg, roles, *, sensor=None, static_map=None, wheel_fn=None, start_poses=None,
                 purpose='hybrid_n'):
        validate_config(cfg, purpose=purpose)
        self.purpose = purpose
        if sorted(roles.values()) != ['blue', 'teal']:
            raise ValueError('one robot per beam end required')
        self.cfg, self.roles = cfg, dict(roles)
        self.lim = cfg['limits']
        self.leader = next(r for r, role in roles.items() if role == cfg['navigator'])
        self.follower = next(r for r in roles if r != self.leader)
        if cfg['carry_mode'] == 'nav' and sensor is None:
            raise ValueError('nav mode needs the own-camera zone sensor')
        self.sensor = sensor
        if cfg['carry_mode'] == 'map' and (static_map is None or start_poses is None):
            raise ValueError('map mode needs the static map and the episode start poses')
        self.static_map, self.start_poses = static_map, start_poses
        self.arbiters = {r: HybridSegmentArbiter(r) for r in roles}
        self.odometry = {r: OwnOdometry(cfg['calibration'], sigma_xy_per_m=self.lim['sigma_xy_per_m'],
                                        sigma_yaw_per_rad=self.lim['sigma_yaw_per_rad']) for r in roles}
        self.trackers = {r: FormationTracker(r, roles[r], cfg, self.odometry[r], wheel_fn=wheel_fn) for r in roles}
        self.gate = PoseTrustGate(self.lim)
        self.carry_sync = PairCarrySync('carry', tuple(roles), plan_version=1, report_ttl_s=self.lim['message_ttl_s'])
        self.place_sync = PairCarrySync('place', tuple(roles), plan_version=1, report_ttl_s=self.lim['message_ttl_s'])
        self.bus = MessageBus()
        self.planner = None
        self.pwm = {}
        self.seq = {r: 0 for r in roles}
        self.stretch_since = None
        self.code_t0 = self.code_t1 = None
        self.ticks = dict(student=0, code=0, shadow=0)
        self.outcome = None
        self.events = []
        self.gt_inputs_to_code = 0

    # -- helpers
    def segment(self):
        segs = {a.segment for a in self.arbiters.values()}
        return segs.pop() if len(segs) == 1 else 'MIXED'

    def student_controls(self):
        return all(a.student_controls for a in self.arbiters.values())

    def _abort(self, now, reason):
        self.outcome = 'abort:' + reason if not reason.startswith('abort:') else reason
        for a in self.arbiters.values():
            a.to('ABORT', now, reason)
        self.events.append(dict(t=now, event='abort', reason=reason))

    def _report(self, sync, now, ready, reason):
        for r in self.roles:
            self.seq[r] += 1
            sync.report(r, plan_version=1, epoch=sync.epoch, sequence=self.seq[r], ready=ready[r],
                        observed_at_s=now, received_at_s=now, frame_id=f'{sync.task_id}:{r}:{self.seq[r]}',
                        reason=reason)
        return sync.authorize(now)

    # -- student segments
    def after_student_tick(self, now, issued, applied):
        """issued: worker issue() rows (segment/done/stage per robot); applied: commands executed."""
        self.ticks['student'] += 1
        for r, cmd in applied.items():
            self.odometry[r].step(cmd)
            self.pwm[r] = {int(k): int(v) for k, v in cmd['pwm'].items()}
        if self.segment() == 'STUDENT_GRASP' and all(issued[r]['segment'] == 'release' for r in self.roles):
            for a in self.arbiters.values():
                a.to('CARRY_SYNC', now, 'own_release_instruction (both own done flags 3 s)')
            self.events.append(dict(t=now, event='hold_complete_own'))

    # -- code segments
    def _start_code(self, now):
        for t in self.trackers.values():
            t.start()
        if self.cfg['carry_mode'] == 'nav':
            # nav plans in the handover beam frame: only drift since the handover matters
            for o in self.odometry.values():
                o.sigma_xy = o.sigma_yaw = 0.
        nav_offset = role_offset(self.cfg['navigator'], self.cfg['formation'])
        route = None
        if self.cfg['carry_mode'] == 'map':
            require_map_approval(self.cfg['map'])
            route = map_route_b0(self.static_map, self.start_poses[self.leader], self.odometry[self.leader].pose,
                                 {r: self.trackers[r].offset for r in self.roles}, self.trackers[self.leader].offset)
        self.planner = VirtualBeamPlanner(self.cfg, nav_offset, route=route)
        self.code_t0 = now

    def code_tick(self, now, jpegs):
        if set(jpegs) != set(self.roles):
            raise ValueError('one own camera frame per robot (no other input)')
        seg = self.segment()
        hold = {r: True for r in self.roles}
        if seg == 'CARRY_SYNC':
            d = self._report(self.carry_sync, now, {r: True for r in self.roles}, 'READY_CARRY own')
            if d['phase'] == 'GO':
                for a in self.arbiters.values():
                    a.to('CODE_CARRY', now, 'carry_sync GO')
                self._start_code(now)
        elif seg == 'CODE_CARRY':
            self._carry(now, jpegs, hold)
        elif seg == 'PLACE_SYNC':
            d = self._report(self.place_sync, now, {r: True for r in self.roles}, 'READY_PLACE own')
            if d['phase'] == 'GO':
                for a in self.arbiters.values():
                    a.to('STUDENT_PLACE', now, 'place_sync GO (hand-back at set-down start)')
                self.code_t1 = now
        out = {}
        for r in self.roles:
            tr = self.trackers[r]
            if self.planner is not None and not hold[r] and self.segment() == 'CODE_CARRY':
                msg = self.bus.receive(now, self.lim['message_ttl_s']) if r == self.follower else None
                if r == self.follower and msg is None:
                    cmd = tr.command(now, None, None, self.pwm[r], hold=True)
                else:
                    V, vel = (self.planner.V, self.planner.vel) if r == self.leader else (tuple(msg['V']), tuple(msg['vel']))
                    cmd = tr.command(now, V, vel, self.pwm[r])
            else:
                cmd = tr.command(now, None, None, self.pwm[r], hold=True)
            out[r] = cmd
            self.odometry[r].step(cmd)
        self.ticks['code'] += 1
        return out

    def _carry(self, now, jpegs, hold):
        lead, foll = self.leader, self.follower
        for r in self.roles:
            why = self.gate.check(self.odometry[r])
            if why:
                return self._abort(now, why)
        if self.cfg['carry_mode'] == 'nav':
            seen = self.sensor(jpegs[lead])
            self.planner.observe(now, seen, self.trackers[lead].pose_b0())
        outcome = self.planner.step(now, DT)
        if outcome is not None and outcome.startswith('abort:'):
            return self._abort(now, outcome[len('abort:'):])
        # I4: leader broadcasts V; formation consistency from both own beam estimates
        own = self.trackers[lead].beam_estimate()
        self.bus.send(lead, now, dict(V=list(self.planner.V), vel=list(self.planner.vel), phase=self.planner.phase,
                                      beam_estimate=list(own)))
        other = self.trackers[foll].beam_estimate()
        stretch = math.hypot(own[0] - other[0], own[1] - other[1])
        if stretch > self.lim['stretch_fail_m']:
            self.stretch_since = now if self.stretch_since is None else self.stretch_since
            if now - self.stretch_since >= self.lim['stretch_fail_s'] - 1e-9:
                return self._abort(now, 'formation_stretch')
        else:
            self.stretch_since = None
        paused = stretch > self.lim['stretch_pause_m']
        if paused:
            self.planner.vel = (0., 0., 0.)
        if outcome == 'arrived':
            for a in self.arbiters.values():
                a.to('PLACE_SYNC', now, 'arrived (own judgement)')
            return
        for r in self.roles:
            hold[r] = paused

    def shadow_request(self, now, jpegs_b64, applied):
        """I7 worker request (dsh/pairact-p5-student-hybrid 'shadow' op)."""
        self.ticks['shadow'] += 1
        return {'op': 'shadow', 't': float(now), 'predict': self.cfg['shadow_predict'],
                'robots': {r: {'jpeg': jpegs_b64[r], 'applied': applied[r]} for r in self.roles}}

    def student_finished(self, now):
        if self.segment() == 'STUDENT_PLACE':
            for a in self.arbiters.values():
                a.to('DONE', now, 'student finished')

    def summary(self):
        total = sum(self.ticks[k] for k in ('student', 'code'))
        code_s = None if self.code_t0 is None else ((self.code_t1 if self.code_t1 is not None else
                                                     self.code_t0 + .1*self.ticks['code']) - self.code_t0)
        return dict(mode=MODE, carry_mode=self.cfg['carry_mode'], navigator=self.cfg['navigator'],
                    segment=self.segment(), outcome=self.outcome or ('handed_back' if self.code_t1 else None),
                    code_segment_s=code_s, ticks=dict(self.ticks),
                    student_commands_executed_ratio=(self.ticks['student']/total) if total else None,
                    gt_inputs_to_code=self.gt_inputs_to_code, teacher_steps=0,
                    switch_events=[e for a in self.arbiters.values() for e in a.events],
                    planner_events=list(self.planner.events) if self.planner else [],
                    events=list(self.events), messages=len(self.bus.log),
                    sync_events={'carry': list(self.carry_sync.events) if hasattr(self.carry_sync, 'events') else None,
                                 'place': list(self.place_sync.events) if hasattr(self.place_sync, 'events') else None},
                    odometry={r: dict(distance_m=o.distance_m, turn_rad=o.turn_rad, sigma_xy=o.sigma_xy,
                                      sigma_yaw=o.sigma_yaw) for r, o in self.odometry.items()})


def map_route_b0(static_map, start_pose_map, odom_pose, offsets, leader_offset):
    """'map' only: carry_route waypoints (map frame) -> handover beam frame B0.

    The beam pose in the map comes from the leader's episode start pose (case file) composed with
    its own odometry since the start and its formation offset; no GT pose is read."""
    leader_map = compose(start_pose_map, odom_pose)
    beam_map = compose(leader_map, inverse(leader_offset))
    route, _info = carry_route(beam_map, offsets, static_map)
    return [(tag, relative(beam_map, wp)) for tag, wp in route]


def load_config(path, *, approval_root=None, purpose='hybrid_n'):
    return validate_config(json.loads(Path(path).read_text()), approval_root=approval_root, purpose=purpose)
